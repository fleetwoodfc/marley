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

from healthcare.healthcare.dicom.ups_rs import UpsRSClient, ProcedureStepState, Workitem


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
    
    # Extract AET from URL if not separately configured
    # URL format: http://host:port/dcm4chee-arc/aets/{AET}/rs
    aet = getattr(settings, "ups_aet", None)
    if not aet:
        # Try to extract from URL
        import re
        match = re.search(r'/aets/([^/]+)/rs', settings.ups_rs_url)
        if match:
            aet = match.group(1)
        else:
            aet = "DCM4CHEE"  # Default fallback
    
    return UpsRSClient(settings.ups_rs_url, aet=aet)


def sync_state_change(procedure_step, **kwargs):
    """
    Sync a Scheduled Procedure Step state change to the DICOM server.
    
    This is typically called as a background job after state changes.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step document
        **kwargs: Additional arguments passed by the job queue (ignored)
    """
    client = get_ups_client()
    if not client:
        return
    
    try:
        sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
        
        # Check if workitem exists on server
        workitem_exists = _workitem_exists(client, sps.sop_instance_uid)
        
        # If workitem doesn't exist and we're not in SCHEDULED state,
        # we need to create it first (with SCHEDULED state) then transition
        if not workitem_exists:
            # Always create with SCHEDULED state first
            _create_workitem(client, sps)
            workitem_exists = True
        
        # Now apply the state transition if needed
        if sps.ups_state == "SCHEDULED":
            # Already in scheduled state, nothing more to do
            pass
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


def _workitem_exists(client, sop_instance_uid):
    """
    Check if a workitem exists on the DICOM server.
    
    Args:
        client: UpsRSClient instance
        sop_instance_uid: SOP Instance UID to check
    
    Returns:
        True if workitem exists, False otherwise
    """
    try:
        workitem = client.retrieve_workitem(sop_instance_uid)
        return workitem is not None
    except Exception:
        return False


def _create_workitem(client, sps):
    """
    Create a new UPS workitem on the DICOM server.
    
    Args:
        client: UpsRSClient instance
        sps: Scheduled Procedure Step document
        
    Returns:
        The UID of the created workitem (may be server-assigned)
    """
    # Build Workitem object from SPS
    workitem = _build_workitem(sps)
    
    # Create via UPS-RS
    result = client.create_workitem(workitem, uid=sps.sop_instance_uid)
    
    # Store any server-assigned values if needed
    if result and result != sps.sop_instance_uid:
        frappe.db.set_value(
            "Scheduled Procedure Step",
            sps.name,
            "sop_instance_uid",
            result
        )
        # Update the in-memory object too
        sps.sop_instance_uid = result
    
    return result


def _claim_workitem(client, sps):
    """
    Claim a UPS workitem (transition to IN PROGRESS).
    
    Args:
        client: UpsRSClient instance
        sps: Scheduled Procedure Step document
    """
    transaction_uid = client.change_state(
        sps.sop_instance_uid,
        ProcedureStepState.IN_PROGRESS,
        transaction_uid=sps.transaction_uid
    )
    # Store the transaction UID for subsequent state changes
    if transaction_uid and not sps.transaction_uid:
        frappe.db.set_value(
            "Scheduled Procedure Step",
            sps.name,
            "transaction_uid",
            transaction_uid
        )


def _complete_workitem(client, sps):
    """
    Complete a UPS workitem with Final State Requirements.
    
    Args:
        client: UpsRSClient instance
        sps: Scheduled Procedure Step document
    """
    from healthcare.healthcare.dicom.ups_rs import DicomCode
    
    # Get performed station name if available
    performed_station = None
    if hasattr(sps, 'modality') and sps.modality:
        # Use modality as a simple station code
        performed_station = DicomCode(
            code_value=sps.modality,
            code_meaning=sps.modality,
            coding_scheme_designator="DCM"
        )
    
    # Get performed workitem code if available  
    performed_workitem = None
    if hasattr(sps, 'procedure_description') and sps.procedure_description:
        performed_workitem = DicomCode(
            code_value="LOCAL001",
            code_meaning=sps.procedure_description[:64],  # Truncate to fit LO VR
            coding_scheme_designator="LOCAL"
        )
    
    # Complete with Final State Requirements
    client.complete_workitem(
        sps.sop_instance_uid,
        transaction_uid=sps.transaction_uid,
        performed_workitem_code=performed_workitem,
        performed_station_name=performed_station
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
        ProcedureStepState.CANCELED,
        transaction_uid=sps.transaction_uid
    )


def send_cancel_request(procedure_step, reason=None, contact_name=None, contact_uri=None):
    """
    Send a cancellation request for a workitem being performed by another station.
    
    This implements the UPS-RS Request Cancellation operation for third-party
    cancellation workflow. The performing station will receive an event and
    can choose to accept or decline the request.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step document
        reason: Optional reason for the cancellation request
        contact_name: Optional name of the requester for callback
        contact_uri: Optional URI for callback (e.g., email, tel)
    
    Returns:
        dict with success status and message
    
    Raises:
        frappe.ValidationError: If the procedure cannot be canceled
    """
    from healthcare.healthcare.dicom.ups_rs import CancellationRequest
    
    client = get_ups_client()
    if not client:
        frappe.throw(_("UPS sync is not enabled or configured"))
    
    sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
    
    # Can only request cancellation for IN PROGRESS workitems
    if sps.ups_state != "IN PROGRESS":
        frappe.throw(
            _("Can only request cancellation for procedures IN PROGRESS. Current state: {0}").format(sps.ups_state)
        )
    
    # Cannot request cancellation of own procedure
    if sps.claimed_by == frappe.session.user:
        frappe.throw(
            _("Cannot request cancellation of your own procedure. Use Cancel Procedure instead.")
        )
    
    try:
        # Build cancellation request
        cancel_request = CancellationRequest(
            reason=reason or _("Cancellation requested"),
            contact_name=contact_name,
            contact_uri=contact_uri
        )
        
        # Send via UPS-RS
        client.request_cancellation(sps.sop_instance_uid, cancel_request)
        
        frappe.log_error(
            f"Cancellation requested for {procedure_step} by {frappe.session.user}",
            "UPS Cancel Request Sent"
        )
        
        return {
            "success": True,
            "message": _("Cancellation request sent to performing station")
        }
        
    except Exception as e:
        frappe.log_error(
            f"Cancel request failed for {procedure_step}: {str(e)}",
            "UPS Cancel Request Error"
        )
        raise


def _build_workitem(sps):
    """
    Build a Workitem object from a Scheduled Procedure Step.
    
    Args:
        sps: Scheduled Procedure Step document
    
    Returns:
        Workitem object for UPS-RS API
    """
    from datetime import datetime
    
    # Get patient info
    patient = frappe.get_cached_doc("Patient", sps.patient)
    
    # Parse scheduled_datetime
    scheduled_dt = None
    if sps.scheduled_datetime:
        if isinstance(sps.scheduled_datetime, str):
            scheduled_dt = datetime.fromisoformat(sps.scheduled_datetime.replace(" ", "T"))
        else:
            scheduled_dt = sps.scheduled_datetime
    
    # Always create workitems with SCHEDULED state (required by UPS-RS)
    # State transitions happen via change_state() calls
    state = ProcedureStepState.SCHEDULED
    
    # Get accession number from parent ISR if available
    accession_number = None
    if sps.imaging_service_request:
        accession_number = frappe.db.get_value(
            "Imaging Service Request",
            sps.imaging_service_request,
            "accession_number"
        )
    
    return Workitem(
        uid=sps.sop_instance_uid,
        procedure_step_state=state,
        scheduled_start_datetime=scheduled_dt,
        procedure_step_label=sps.procedure_step_label or sps.name,
        patient_id=sps.patient,
        patient_name=patient.patient_name if patient else None,
        study_instance_uid=sps.study_instance_uid,
        accession_number=accession_number,
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
