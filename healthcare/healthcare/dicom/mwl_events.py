# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
MWL Event Handlers for Frappe Healthcare

This module handles Scheduled Procedure Step document events
and triggers MWL synchronization with dcm4chee.

Unlike UPS which manages workflow state bidirectionally, MWL sync is
one-way: Frappe → dcm4chee. MWL items are created when SPSs are
scheduled and removed when they start, complete, or cancel.
"""

import frappe
from frappe.utils import cint

from healthcare.healthcare.dicom.mwl_sync import (
    sync_to_mwl,
    remove_from_mwl,
    update_mwl_attributes
)


# Fields that trigger MWL update when changed
MWL_TRACKED_FIELDS = [
    "patient",
    "patient_name",
    "scheduled_datetime",
    "modality",
    "station_aet",
    "station_name",
    "worklist_label",
    "radiology_procedure",
    "study_instance_uid",
]


def on_sps_state_change(doc, method):
    """
    Handle Scheduled Procedure Step state changes.
    
    Triggered by doc_events in hooks.py.
    
    Args:
        doc: Scheduled Procedure Step document
        method: Event method name (on_update, after_insert, etc.)
        
    Behavior:
        - If state → SCHEDULED: Enqueue sync_to_mwl
        - If state → IN PROGRESS: Enqueue remove_from_mwl
        - If state → CANCELED: Enqueue remove_from_mwl
        - If state → COMPLETED: Enqueue remove_from_mwl (cleanup)
    """
    # Check if MWL sync is enabled
    if not _is_mwl_sync_enabled():
        return
    
    # Only process if this is a modality-based SPS
    if not doc.modality:
        return
    
    # Get the current UPS state
    ups_state = doc.ups_state or "SCHEDULED"
    
    # Determine action based on state
    if ups_state == "SCHEDULED":
        # Check if auto-create is enabled
        settings = frappe.get_single("Healthcare Settings")
        if cint(settings.auto_create_mwl_on_schedule):
            _enqueue_mwl_sync(doc.name, sync_to_mwl)
    
    elif ups_state == "IN PROGRESS":
        # Check if auto-remove on start is enabled
        settings = frappe.get_single("Healthcare Settings")
        if cint(settings.auto_delete_mwl_on_start):
            _enqueue_mwl_sync(doc.name, remove_from_mwl)
    
    elif ups_state == "CANCELED":
        # Check if auto-remove on cancel is enabled
        settings = frappe.get_single("Healthcare Settings")
        if cint(settings.auto_delete_mwl_on_cancel):
            _enqueue_mwl_sync(doc.name, remove_from_mwl)
    
    elif ups_state == "COMPLETED":
        # Always remove from MWL when completed
        _enqueue_mwl_sync(doc.name, remove_from_mwl)


def on_sps_attributes_change(doc, method):
    """
    Handle Scheduled Procedure Step attribute modifications.
    
    Triggered when SPS in SCHEDULED state has relevant fields modified.
    
    Args:
        doc: Scheduled Procedure Step document
        method: Event method name
    """
    # Check if MWL sync is enabled
    if not _is_mwl_sync_enabled():
        return
    
    # Only update MWL if in SCHEDULED state and already synced
    ups_state = doc.ups_state or "SCHEDULED"
    if ups_state != "SCHEDULED":
        return
    
    # Only update if already synced
    if doc.mwl_sync_status != "synced":
        return
    
    # Only process if this is a modality-based SPS
    if not doc.modality:
        return
    
    # Check if any tracked field changed
    if _has_tracked_field_changed(doc):
        _enqueue_mwl_sync(doc.name, update_mwl_attributes)


def on_sps_insert(doc, method):
    """
    Handle new Scheduled Procedure Step insertion.
    
    Args:
        doc: Scheduled Procedure Step document
        method: Event method name (after_insert)
    """
    # Check if MWL sync is enabled
    if not _is_mwl_sync_enabled():
        return
    
    # Only process if this is a modality-based SPS in SCHEDULED state
    if not doc.modality:
        return
    
    ups_state = doc.ups_state or "SCHEDULED"
    if ups_state != "SCHEDULED":
        return
    
    # Check if auto-create is enabled
    settings = frappe.get_single("Healthcare Settings")
    if cint(settings.auto_create_mwl_on_schedule):
        _enqueue_mwl_sync(doc.name, sync_to_mwl)


def on_sps_update(doc, method):
    """
    Handle Scheduled Procedure Step update.
    
    Combines state change and attribute change handling.
    
    Args:
        doc: Scheduled Procedure Step document
        method: Event method name (on_update)
    """
    # Check if state changed
    if _has_state_changed(doc):
        on_sps_state_change(doc, method)
    else:
        # State didn't change, check for attribute changes
        on_sps_attributes_change(doc, method)


# ==============================================================================
# Helper Functions
# ==============================================================================

def _is_mwl_sync_enabled() -> bool:
    """Check if MWL sync is enabled in Healthcare Settings."""
    try:
        settings = frappe.get_single("Healthcare Settings")
        return cint(settings.enable_mwl_sync)
    except Exception:
        return False


def _enqueue_mwl_sync(procedure_step: str, sync_func):
    """
    Enqueue MWL sync operation as background job.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step
        sync_func: The sync function to call (sync_to_mwl or remove_from_mwl)
    """
    frappe.enqueue(
        sync_func,
        procedure_step=procedure_step,
        queue="short",
        timeout=120,
        enqueue_after_commit=True
    )


def _has_state_changed(doc) -> bool:
    """Check if UPS state has changed since last save."""
    if doc.is_new():
        return False
    
    previous_doc = doc.get_doc_before_save()
    if not previous_doc:
        return False
    
    return doc.ups_state != previous_doc.ups_state


def _has_tracked_field_changed(doc) -> bool:
    """Check if any MWL-tracked field has changed since last save."""
    if doc.is_new():
        return True  # Treat new docs as having all fields changed
    
    previous_doc = doc.get_doc_before_save()
    if not previous_doc:
        return False
    
    for field in MWL_TRACKED_FIELDS:
        old_value = getattr(previous_doc, field, None)
        new_value = getattr(doc, field, None)
        if old_value != new_value:
            return True
    
    return False
