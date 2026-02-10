# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
UPS-RS Synchronization Service

Synchronizes Scheduled Procedure Step state changes with dcm4chee-arc
via the UPS-RS (Unified Procedure Step RESTful Services) API.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from healthcare.healthcare.dicom.ups_rs import UpsRSClient


def get_ups_client():
    """
    Get a configured UPS-RS client from Healthcare Settings.
    
    Returns:
        UpsRSClient instance or None if sync is disabled
    """
    settings = frappe.get_single("Healthcare Settings")
    
    if not settings.enable_ups_sync:
        return None
    
    if not settings.ups_rs_url:
        frappe.log_error(
            "UPS-RS URL not configured in Healthcare Settings",
            "UPS Sync Error"
        )
        return None
    
    return UpsRSClient(settings.ups_rs_url)


def sync_state_change(procedure_step):
    """
    Sync a Scheduled Procedure Step state change to the DICOM server.
    
    This is typically called as a background job after state changes.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step document
    """
    client = get_ups_client()
    if not client:
        return
    
    try:
        sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
        
        if sps.ups_state == "SCHEDULED":
            # Create new workitem
            _create_workitem(client, sps)
        elif sps.ups_state == "IN PROGRESS":
            # Claim workitem
            _claim_workitem(client, sps)
        elif sps.ups_state == "COMPLETED":
            # Complete workitem
            _complete_workitem(client, sps)
        elif sps.ups_state == "CANCELED":
            # Cancel workitem
            _cancel_workitem(client, sps)
        
        # Update sync status on success
        frappe.db.set_value(
            "Scheduled Procedure Step",
            procedure_step,
            {
                "ups_sync_status": "synced",
                "ups_sync_at": now_datetime(),
                "ups_sync_error": None
            }
        )
        frappe.db.commit()
        
    except Exception as e:
        # Log error and update sync status
        frappe.log_error(
            f"UPS Sync failed for {procedure_step}: {str(e)}",
            "UPS Sync Error"
        )
        
        frappe.db.set_value(
            "Scheduled Procedure Step",
            procedure_step,
            {
                "ups_sync_status": "error",
                "ups_sync_error": str(e)[:200]  # Truncate to fit field
            }
        )
        frappe.db.commit()
        
        # Re-queue for retry if retries are enabled
        _schedule_retry(procedure_step)


def _create_workitem(client, sps):
    """
    Create a new UPS workitem on the DICOM server.
    
    Args:
        client: UpsRSClient instance
        sps: Scheduled Procedure Step document
    """
    # Build workitem data from SPS
    workitem_data = _build_workitem_json(sps)
    
    # Create via UPS-RS
    result = client.create_workitem(workitem_data)
    
    # Store any server-assigned values if needed
    if result and "sop_instance_uid" in result:
        # Server may assign a different UID (rare)
        if result["sop_instance_uid"] != sps.sop_instance_uid:
            frappe.db.set_value(
                "Scheduled Procedure Step",
                sps.name,
                "sop_instance_uid",
                result["sop_instance_uid"]
            )


def _claim_workitem(client, sps):
    """
    Claim a UPS workitem (transition to IN PROGRESS).
    
    Args:
        client: UpsRSClient instance
        sps: Scheduled Procedure Step document
    """
    client.change_state(
        sps.sop_instance_uid,
        "IN PROGRESS",
        transaction_uid=sps.transaction_uid
    )


def _complete_workitem(client, sps):
    """
    Complete a UPS workitem.
    
    Args:
        client: UpsRSClient instance
        sps: Scheduled Procedure Step document
    """
    client.change_state(
        sps.sop_instance_uid,
        "COMPLETED",
        transaction_uid=sps.transaction_uid
    )


def _cancel_workitem(client, sps):
    """
    Cancel a UPS workitem.
    
    Args:
        client: UpsRSClient instance
        sps: Scheduled Procedure Step document
    """
    client.change_state(
        sps.sop_instance_uid,
        "CANCELED",
        transaction_uid=sps.transaction_uid
    )


def _build_workitem_json(sps):
    """
    Build DICOM JSON workitem data from a Scheduled Procedure Step.
    
    Args:
        sps: Scheduled Procedure Step document
    
    Returns:
        Dictionary in DICOM JSON format
    """
    # Get patient info
    patient = frappe.get_cached_doc("Patient", sps.patient)
    
    # Build DICOM JSON structure
    workitem = {
        # SOP Instance UID
        "00080018": {"vr": "UI", "Value": [sps.sop_instance_uid]},
        # Procedure Step State
        "00741000": {"vr": "CS", "Value": [sps.ups_state]},
        # Scheduled Procedure Step Start DateTime
        "00404010": {"vr": "DT", "Value": [_format_dicom_datetime(sps.scheduled_datetime)]},
        # Patient ID
        "00100020": {"vr": "LO", "Value": [sps.patient]},
        # Patient Name
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": patient.patient_name}]},
        # Modality
        "00080060": {"vr": "CS", "Value": [sps.modality]},
    }
    
    # Add optional fields
    if sps.procedure_step_label:
        # Procedure Step Label
        workitem["00741204"] = {"vr": "LO", "Value": [sps.procedure_step_label]}
    
    if sps.station_aet:
        # Scheduled Station AE Title
        workitem["00404021"] = {
            "vr": "SQ",
            "Value": [{"00400012": {"vr": "LO", "Value": [sps.station_aet]}}]
        }
    
    if sps.station_name:
        # Scheduled Station Name
        workitem["00400010"] = {"vr": "SH", "Value": [sps.station_name]}
    
    if sps.study_instance_uid:
        # Referenced Request Sequence with Study Instance UID
        workitem["0040A370"] = {
            "vr": "SQ",
            "Value": [{
                # Study Instance UID
                "0020000D": {"vr": "UI", "Value": [sps.study_instance_uid]},
                # Accession Number (from parent ISR)
                "00080050": {"vr": "SH", "Value": [
                    frappe.db.get_value(
                        "Imaging Service Request",
                        sps.imaging_service_request,
                        "accession_number"
                    ) or ""
                ]}
            }]
        }
    
    # Add protocol codes if present
    if sps.protocol_codes:
        scheduled_protocol_codes = []
        for code in sps.protocol_codes:
            scheduled_protocol_codes.append({
                "00080100": {"vr": "SH", "Value": [code.code_value]},
                "00080102": {"vr": "SH", "Value": [code.coding_scheme_designator]},
                "00080104": {"vr": "LO", "Value": [code.code_meaning]}
            })
        
        if scheduled_protocol_codes:
            # Scheduled Protocol Code Sequence
            workitem["00404025"] = {"vr": "SQ", "Value": scheduled_protocol_codes}
    
    return workitem


def _format_dicom_datetime(dt):
    """
    Format a datetime to DICOM DT format (YYYYMMDDHHMMSS).
    
    Args:
        dt: Python datetime or Frappe datetime string
    
    Returns:
        DICOM formatted datetime string
    """
    from frappe.utils import get_datetime
    
    if not dt:
        return None
    
    dt_obj = get_datetime(dt)
    return dt_obj.strftime("%Y%m%d%H%M%S")


def _schedule_retry(procedure_step):
    """
    Schedule a retry for failed sync operations.
    
    Uses exponential backoff: 5s, 30s, 120s, 600s
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step
    """
    settings = frappe.get_single("Healthcare Settings")
    
    if not settings.ups_sync_retry_enabled:
        return
    
    # Get current retry count from error log (simplified approach)
    # In production, you might want a dedicated retry counter field
    retry_delays = [5, 30, 120, 600]  # seconds
    
    # For now, just schedule with first delay
    # A more sophisticated implementation would track retry count
    frappe.enqueue(
        "healthcare.healthcare.dicom.ups_sync.sync_state_change",
        procedure_step=procedure_step,
        queue="short",
        enqueue_after=retry_delays[0]
    )


def sync_pending_workitems():
    """
    Background job to retry syncing all pending workitems.
    
    Called by scheduler to ensure eventual consistency.
    """
    pending = frappe.get_all(
        "Scheduled Procedure Step",
        filters={"ups_sync_status": ["in", ["pending", "error"]]},
        pluck="name",
        limit=50  # Process in batches
    )
    
    for sps_name in pending:
        try:
            sync_state_change(sps_name)
        except Exception:
            # Errors are logged in sync_state_change
            pass


def reconcile_ups_states():
    """
    Background job to reconcile local state with DICOM server.
    
    Fetches current state from DICOM server and updates local records
    if they differ (handles cases where DICOM server was updated externally).
    """
    client = get_ups_client()
    if not client:
        return
    
    # Get all non-final state workitems
    active_sps = frappe.get_all(
        "Scheduled Procedure Step",
        filters={"ups_state": ["in", ["SCHEDULED", "IN PROGRESS"]]},
        fields=["name", "sop_instance_uid", "ups_state"]
    )
    
    for sps in active_sps:
        try:
            # Query DICOM server for current state
            remote_state = client.get_workitem_state(sps.sop_instance_uid)
            
            if remote_state and remote_state != sps.ups_state:
                # Update local state to match remote
                frappe.db.set_value(
                    "Scheduled Procedure Step",
                    sps.name,
                    {
                        "ups_state": remote_state,
                        "ups_sync_status": "synced",
                        "ups_sync_at": now_datetime()
                    }
                )
                
                frappe.log_error(
                    f"State reconciled for {sps.name}: {sps.ups_state} → {remote_state}",
                    "UPS State Reconciliation"
                )
                
        except Exception as e:
            frappe.log_error(
                f"Reconciliation failed for {sps.name}: {str(e)}",
                "UPS Reconciliation Error"
            )
    
    frappe.db.commit()


# Hook Functions for doc_events
# Called automatically by Frappe when documents are updated

def on_scheduled_procedure_step_update(doc, method):
    """
    Hook called when a Scheduled Procedure Step is updated.
    
    Enqueues a background job to sync state change to dcm4chee-arc.
    
    Args:
        doc: The Scheduled Procedure Step document
        method: The hook method name ("on_update")
    """
    settings = frappe.get_single("Healthcare Settings")
    
    if not settings.enable_ups_sync:
        return
    
    # Check if state changed
    if doc.has_value_changed("ups_state"):
        # Mark as pending sync
        frappe.db.set_value(
            "Scheduled Procedure Step",
            doc.name,
            "ups_sync_status",
            "pending",
            update_modified=False
        )
        
        # Enqueue background sync job
        frappe.enqueue(
            "healthcare.healthcare.dicom.ups_sync.sync_state_change",
            procedure_step=doc.name,
            queue="short",
            enqueue_after_commit=True
        )


def on_scheduled_procedure_step_insert(doc, method):
    """
    Hook called when a new Scheduled Procedure Step is created.
    
    Enqueues a background job to create workitem on dcm4chee-arc.
    
    Args:
        doc: The Scheduled Procedure Step document
        method: The hook method name ("after_insert")
    """
    settings = frappe.get_single("Healthcare Settings")
    
    if not settings.enable_ups_sync:
        return
    
    # Mark as pending sync
    frappe.db.set_value(
        "Scheduled Procedure Step",
        doc.name,
        "ups_sync_status",
        "pending",
        update_modified=False
    )
    
    # Enqueue background sync job
    frappe.enqueue(
        "healthcare.healthcare.dicom.ups_sync.sync_state_change",
        procedure_step=doc.name,
        queue="short",
        enqueue_after_commit=True
    )
