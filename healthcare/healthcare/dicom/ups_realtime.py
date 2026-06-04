# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
UPS Realtime Integration for Frappe

This module provides functions to push UPS events to connected browsers
via Frappe's realtime (Socket.IO) system.

Events Published:
    - ups_state_changed: When a workitem state changes
    - ups_workitem_created: When a new workitem is created
    - ups_cancel_request: When a cancellation is requested
    - ups_progress_report: When progress is reported
    - worklist_updated: General worklist update notification

Usage:
    # In your Python code:
    from healthcare.healthcare.dicom.ups_realtime import publish_state_change
    publish_state_change("SPS-00001", "COMPLETED")
    
    # In your JavaScript:
    frappe.realtime.on("ups_state_changed", (data) => {
        console.log("State changed:", data.sps_name, data.ups_state);
    });
"""

import frappe
from frappe import _
from typing import Optional


def publish_state_change(
    sps_name: str,
    new_state: str,
    old_state: str = None,
    reason: str = None,
    doctype_specific: bool = True
):
    """
    Publish a state change event to connected browsers.
    
    Args:
        sps_name: The Scheduled Procedure Step document name
        new_state: The new UPS state
        old_state: Optional previous state
        reason: Optional reason (for cancellation)
        doctype_specific: If True, also publish to doctype-specific channel
    """
    event_data = {
        "sps_name": sps_name,
        "ups_state": new_state,
        "old_state": old_state,
        "reason": reason,
        "timestamp": frappe.utils.now()
    }
    
    # Publish to global UPS channel
    frappe.publish_realtime(
        "ups_state_changed",
        event_data,
        after_commit=False
    )
    
    # Also publish to doctype-specific channel for form updates
    if doctype_specific:
        frappe.publish_realtime(
            "ups_state_changed",
            event_data,
            doctype="Scheduled Procedure Step",
            docname=sps_name,
            after_commit=False
        )
    
    # Publish generic worklist update
    frappe.publish_realtime(
        "worklist_updated",
        {
            "sps_name": sps_name,
            "action": "state_changed",
            "ups_state": new_state
        },
        after_commit=False
    )


def publish_workitem_created(
    sps_name: str,
    sop_instance_uid: str,
    patient: str = None,
    modality: str = None
):
    """
    Publish a workitem created event.
    
    Args:
        sps_name: The Scheduled Procedure Step document name
        sop_instance_uid: The DICOM SOP Instance UID
        patient: Optional patient name
        modality: Optional modality
    """
    event_data = {
        "sps_name": sps_name,
        "sop_instance_uid": sop_instance_uid,
        "patient": patient,
        "modality": modality,
        "timestamp": frappe.utils.now()
    }
    
    frappe.publish_realtime(
        "ups_workitem_created",
        event_data,
        after_commit=False
    )
    
    frappe.publish_realtime(
        "worklist_updated",
        {
            "sps_name": sps_name,
            "action": "created"
        },
        after_commit=False
    )


def publish_cancel_request(
    sps_name: str,
    requester: str = None,
    reason: str = None
):
    """
    Publish a cancellation request event.
    
    This notifies the performing operator that someone has requested
    cancellation of their procedure.
    
    Args:
        sps_name: The Scheduled Procedure Step document name
        requester: Who requested the cancellation
        reason: Reason for cancellation request
    """
    event_data = {
        "sps_name": sps_name,
        "requester": requester,
        "reason": reason,
        "timestamp": frappe.utils.now()
    }
    
    # Publish to the specific SPS document channel
    frappe.publish_realtime(
        "ups_cancel_request",
        event_data,
        doctype="Scheduled Procedure Step",
        docname=sps_name,
        after_commit=False
    )
    
    # Also publish to global channel for monitoring dashboards
    frappe.publish_realtime(
        "ups_cancel_request",
        event_data,
        after_commit=False
    )


def publish_progress_report(
    sps_name: str,
    progress_percent: int = None,
    status_message: str = None,
    data: dict = None
):
    """
    Publish a progress report event.
    
    Args:
        sps_name: The Scheduled Procedure Step document name
        progress_percent: Optional completion percentage (0-100)
        status_message: Optional status message
        data: Optional additional DICOM data
    """
    event_data = {
        "sps_name": sps_name,
        "progress_percent": progress_percent,
        "status_message": status_message,
        "data": data,
        "timestamp": frappe.utils.now()
    }
    
    frappe.publish_realtime(
        "ups_progress_report",
        event_data,
        doctype="Scheduled Procedure Step",
        docname=sps_name,
        after_commit=False
    )


def publish_sync_status(
    sps_name: str,
    sync_status: str,
    error: str = None
):
    """
    Publish a sync status update.
    
    Args:
        sps_name: The Scheduled Procedure Step document name
        sync_status: The new sync status (synced, pending, error, etc.)
        error: Optional error message
    """
    event_data = {
        "sps_name": sps_name,
        "sync_status": sync_status,
        "error": error,
        "timestamp": frappe.utils.now()
    }
    
    frappe.publish_realtime(
        "ups_sync_status",
        event_data,
        doctype="Scheduled Procedure Step",
        docname=sps_name,
        after_commit=False
    )


def publish_worklist_refresh():
    """
    Request all connected clients to refresh their worklist views.
    
    This is useful after bulk operations or reconciliation.
    """
    frappe.publish_realtime(
        "worklist_refresh_required",
        {
            "timestamp": frappe.utils.now()
        },
        after_commit=False
    )


# ============================================================
# Subscription Notifications
# ============================================================

def notify_subscription_connected(aet: str):
    """Notify that WebSocket subscription is connected."""
    frappe.publish_realtime(
        "ups_subscription_status",
        {
            "status": "connected",
            "aet": aet,
            "timestamp": frappe.utils.now()
        },
        after_commit=False
    )


def notify_subscription_disconnected(aet: str, reason: str = None):
    """Notify that WebSocket subscription is disconnected."""
    frappe.publish_realtime(
        "ups_subscription_status",
        {
            "status": "disconnected",
            "aet": aet,
            "reason": reason,
            "timestamp": frappe.utils.now()
        },
        after_commit=False
    )


def notify_subscription_error(error: str):
    """Notify about a subscription error."""
    frappe.publish_realtime(
        "ups_subscription_status",
        {
            "status": "error",
            "error": error,
            "timestamp": frappe.utils.now()
        },
        after_commit=False
    )


# ============================================================
# User-Specific Notifications
# ============================================================

def notify_user_workitem_assigned(user: str, sps_name: str, patient: str = None):
    """
    Notify a specific user that a workitem has been assigned to them.
    
    Args:
        user: The user to notify
        sps_name: The Scheduled Procedure Step document name
        patient: Optional patient name for context
    """
    frappe.publish_realtime(
        "ups_workitem_assigned",
        {
            "sps_name": sps_name,
            "patient": patient,
            "timestamp": frappe.utils.now()
        },
        user=user,
        after_commit=False
    )


def notify_user_cancel_request_decision(
    user: str,
    sps_name: str,
    decision: str,
    reason: str = None
):
    """
    Notify a user about their cancellation request decision.
    
    Args:
        user: The user who requested cancellation
        sps_name: The Scheduled Procedure Step document name
        decision: "accepted" or "declined"
        reason: Optional reason for the decision
    """
    frappe.publish_realtime(
        "ups_cancel_request_decision",
        {
            "sps_name": sps_name,
            "decision": decision,
            "reason": reason,
            "timestamp": frappe.utils.now()
        },
        user=user,
        after_commit=False
    )
