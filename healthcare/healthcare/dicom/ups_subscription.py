# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
UPS Subscription Management API

This module provides functions to manage UPS-RS worklist subscriptions.
Subscriptions allow receiving real-time events when workitems are created,
updated, or canceled on the DICOM server.

Usage:
    # Subscribe to all worklist events
    subscribe_global()
    
    # Subscribe to filtered events (e.g., only CT modality)
    subscribe_filtered({"modality": "CT"})
    
    # List active subscriptions
    list_subscriptions()
    
    # Unsubscribe
    unsubscribe()
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cint
from frappe.utils.background_jobs import enqueue
from typing import Optional, List


@frappe.whitelist()
def subscribe_global() -> dict:
    """
    Subscribe to global worklist events.
    
    This subscribes to ALL workitems on the configured DICOM server.
    Events will be received for any state changes.
    
    Returns:
        dict: Subscription details including subscription_uid
        
    Example:
        >>> result = subscribe_global()
        >>> print(result)
        {"success": True, "subscription_uid": "...", "aet": "WORKLIST"}
    """
    from healthcare.healthcare.dicom.ups_rs import get_ups_client
    
    hs = frappe.get_single("Healthcare Settings")
    
    if not hs.get("ups_rs_url"):
        frappe.throw(_("UPS-RS URL not configured in Healthcare Settings"))
    
    if not hs.get("enable_ups_sync"):
        frappe.throw(_("UPS sync is not enabled in Healthcare Settings"))
    
    try:
        client = get_ups_client()
        result = client.subscribe_worklist()
        
        # Store subscription info
        _save_subscription(
            subscription_type="global",
            subscription_uid=result.get("subscription_uid"),
            aet=result.get("aet")
        )
        
        # Start the worker if not running
        _ensure_worker_running()
        
        return {
            "success": True,
            "subscription_uid": result.get("subscription_uid"),
            "aet": result.get("aet"),
            "message": _("Subscribed to global worklist")
        }
        
    except Exception as e:
        frappe.log_error(f"Failed to subscribe to global worklist: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def subscribe_filtered(filter_criteria: dict = None) -> dict:
    """
    Subscribe to filtered worklist events.
    
    Only receive events for workitems matching the specified criteria.
    
    Args:
        filter_criteria: Dictionary with filter fields:
            - modality: Filter by modality (e.g., "CT", "MR")
            - station_aet: Filter by station AE Title
            - scheduled_date: Filter by scheduled date
            
    Returns:
        dict: Subscription details including subscription_uid
        
    Example:
        >>> result = subscribe_filtered({"modality": "CT"})
        >>> print(result)
        {"success": True, "subscription_uid": "...", "filter": {"modality": "CT"}}
    """
    from healthcare.healthcare.dicom.ups_rs import get_ups_client
    
    if not filter_criteria:
        frappe.throw(_("Filter criteria is required for filtered subscription"))
    
    hs = frappe.get_single("Healthcare Settings")
    
    if not hs.get("ups_rs_url"):
        frappe.throw(_("UPS-RS URL not configured in Healthcare Settings"))
    
    try:
        client = get_ups_client()
        
        # Build filter key from criteria
        filter_key = _build_filter_key(filter_criteria)
        
        result = client.subscribe_filtered_worklist(filter_criteria)
        
        # Store subscription info
        _save_subscription(
            subscription_type="filtered",
            subscription_uid=result.get("subscription_uid"),
            aet=result.get("aet"),
            filter_criteria=filter_criteria,
            filter_key=filter_key
        )
        
        return {
            "success": True,
            "subscription_uid": result.get("subscription_uid"),
            "filter": filter_criteria,
            "message": _("Subscribed to filtered worklist")
        }
        
    except Exception as e:
        frappe.log_error(f"Failed to subscribe to filtered worklist: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def unsubscribe(subscription_uid: str = None) -> dict:
    """
    Unsubscribe from worklist events.
    
    Args:
        subscription_uid: Optional specific subscription to remove.
                         If not provided, removes all subscriptions.
                         
    Returns:
        dict: Result of unsubscribe operation
        
    Example:
        >>> unsubscribe()
        {"success": True, "message": "Unsubscribed from all worklists"}
    """
    from healthcare.healthcare.dicom.ups_rs import get_ups_client
    
    try:
        client = get_ups_client()
        
        if subscription_uid:
            # Unsubscribe specific
            client.unsubscribe_worklist(subscription_uid=subscription_uid)
            _remove_subscription(subscription_uid=subscription_uid)
            message = _("Unsubscribed from subscription {0}").format(subscription_uid)
        else:
            # Unsubscribe all
            client.unsubscribe_worklist()
            _remove_subscription(all_subscriptions=True)
            message = _("Unsubscribed from all worklists")
        
        return {
            "success": True,
            "message": message
        }
        
    except Exception as e:
        frappe.log_error(f"Failed to unsubscribe: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def list_subscriptions() -> List[dict]:
    """
    List all active subscriptions.
    
    Returns:
        list: List of subscription dictionaries with details
        
    Example:
        >>> subs = list_subscriptions()
        >>> for sub in subs:
        ...     print(f"{sub['type']}: {sub['subscription_uid']}")
    """
    subscriptions = frappe.cache().get_value("ups_subscriptions") or []
    
    return [{
        "subscription_uid": sub.get("subscription_uid"),
        "type": sub.get("subscription_type"),
        "aet": sub.get("aet"),
        "filter": sub.get("filter_criteria"),
        "created_at": sub.get("created_at"),
        "filter_key": sub.get("filter_key")
    } for sub in subscriptions]


@frappe.whitelist()
def get_subscription_status() -> dict:
    """
    Get the current subscription and worker status.
    
    Returns:
        dict: Status information including worker state and subscriptions
    """
    from frappe.utils.background_jobs import get_jobs
    
    subscriptions = list_subscriptions()
    
    # Check if worker is running
    jobs = get_jobs(site=frappe.local.site, queue="long")
    worker_running = any(
        "ups_worker.start_worker" in str(job.get("job_name", ""))
        for job in jobs
    )
    
    # Get healthcare settings
    hs = frappe.get_single("Healthcare Settings")
    
    return {
        "ups_configured": bool(hs.get("ups_rs_url")),
        "ups_sync_enabled": bool(hs.get("enable_ups_sync")),
        "ups_rs_url": hs.get("ups_rs_url"),
        "worker_running": worker_running,
        "subscription_count": len(subscriptions),
        "subscriptions": subscriptions
    }


# ============================================================
# Internal Helper Functions
# ============================================================

def _save_subscription(
    subscription_type: str,
    subscription_uid: str,
    aet: str,
    filter_criteria: dict = None,
    filter_key: str = None
):
    """Save subscription info to cache."""
    subscriptions = frappe.cache().get_value("ups_subscriptions") or []
    
    # Check if already exists
    existing = next(
        (s for s in subscriptions if s.get("subscription_uid") == subscription_uid),
        None
    )
    
    if not existing:
        subscriptions.append({
            "subscription_type": subscription_type,
            "subscription_uid": subscription_uid,
            "aet": aet,
            "filter_criteria": filter_criteria,
            "filter_key": filter_key,
            "created_at": str(now_datetime())
        })
        frappe.cache().set_value("ups_subscriptions", subscriptions)


def _remove_subscription(subscription_uid: str = None, all_subscriptions: bool = False):
    """Remove subscription(s) from cache."""
    if all_subscriptions:
        frappe.cache().delete_value("ups_subscriptions")
    else:
        subscriptions = frappe.cache().get_value("ups_subscriptions") or []
        subscriptions = [
            s for s in subscriptions 
            if s.get("subscription_uid") != subscription_uid
        ]
        frappe.cache().set_value("ups_subscriptions", subscriptions)


def _build_filter_key(filter_criteria: dict) -> str:
    """Build a unique key from filter criteria."""
    parts = []
    for key in sorted(filter_criteria.keys()):
        parts.append(f"{key}={filter_criteria[key]}")
    return "|".join(parts)


def _ensure_worker_running():
    """Ensure the UPS event worker is running."""
    from healthcare.healthcare.dicom.ups_worker import enqueue_worker
    
    hs = frappe.get_single("Healthcare Settings")
    
    if not hs.get("enable_ups_sync"):
        return
    
    # Check if worker is already running
    from frappe.utils.background_jobs import get_jobs
    jobs = get_jobs(site=frappe.local.site, queue="long")
    worker_running = any(
        "ups_worker.start_worker" in str(job.get("job_name", ""))
        for job in jobs
    )
    
    if not worker_running:
        enqueue_worker()


@frappe.whitelist()
def start_subscription_worker():
    """
    Start the subscription worker as a background job.
    
    This is the main entry point for starting event reception.
    """
    from healthcare.healthcare.dicom.ups_worker import enqueue_worker
    
    hs = frappe.get_single("Healthcare Settings")
    
    if not hs.get("ups_rs_url"):
        return {"success": False, "error": _("UPS-RS URL not configured")}
    
    if not hs.get("enable_ups_sync"):
        return {"success": False, "error": _("UPS sync not enabled")}
    
    enqueue_worker()
    
    return {
        "success": True,
        "message": _("Subscription worker started")
    }


@frappe.whitelist()
def stop_subscription_worker():
    """
    Stop the subscription worker.
    
    This cancels any running worker jobs and unsubscribes from worklists.
    """
    # Unsubscribe from all worklists
    unsubscribe()
    
    # Note: Can't directly cancel background jobs, they will exit on next iteration
    # The worker checks self._running flag
    
    return {
        "success": True,
        "message": _("Subscription worker stop requested")
    }
