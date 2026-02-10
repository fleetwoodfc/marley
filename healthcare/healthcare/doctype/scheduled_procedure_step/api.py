# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
API endpoints for Scheduled Procedure Step (UPS Worklist).

Provides worklist query, claim, complete, and cancel operations.
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_worklist(
    modality=None,
    station_aet=None,
    scheduled_date=None,
    ups_state=None,
    patient=None,
    limit=50
):
    """
    Query the worklist with optional filters.
    
    Args:
        modality: Filter by modality (e.g., "CT", "MR", "US")
        station_aet: Filter by scheduled station AE title
        scheduled_date: Filter by scheduled date (YYYY-MM-DD)
        ups_state: Filter by UPS state (SCHEDULED, IN PROGRESS)
        patient: Filter by patient name
        limit: Maximum number of results (default 50)
    
    Returns:
        List of Scheduled Procedure Step documents
    """
    filters = {}
    
    if modality:
        filters["modality"] = modality
    
    if station_aet:
        filters["station_aet"] = station_aet
    
    if scheduled_date:
        from frappe.utils import getdate, add_days
        date = getdate(scheduled_date)
        filters["scheduled_datetime"] = ["between", [date, add_days(date, 1)]]
    
    if ups_state:
        filters["ups_state"] = ups_state
    else:
        # Default to active states only
        filters["ups_state"] = ["in", ["SCHEDULED", "IN PROGRESS"]]
    
    if patient:
        filters["patient"] = patient
    
    worklist = frappe.get_all(
        "Scheduled Procedure Step",
        filters=filters,
        fields=[
            "name",
            "sop_instance_uid",
            "ups_state",
            "modality",
            "procedure_step_label",
            "patient",
            "scheduled_datetime",
            "station_name",
            "station_aet",
            "imaging_service_request",
            "study_instance_uid",
            "performing_physician",
            "priority",
            "transaction_uid"
        ],
        order_by="scheduled_datetime asc",
        limit_page_length=limit
    )
    
    # Enrich with patient name
    for item in worklist:
        if item.patient:
            item["patient_name"] = frappe.db.get_value("Patient", item.patient, "patient_name")
        if item.imaging_service_request:
            item["accession_number"] = frappe.db.get_value(
                "Imaging Service Request",
                item.imaging_service_request,
                "accession_number"
            )
    
    return worklist


@frappe.whitelist()
def claim_procedure(procedure_step):
    """
    Claim a Scheduled Procedure Step (transition to IN PROGRESS).
    
    This locks the workitem for the current user/station to perform.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step
    
    Returns:
        Dictionary with transaction_uid on success
    
    Raises:
        frappe.ValidationError: If procedure cannot be claimed
    """
    sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
    
    # Validate current state
    if sps.ups_state != "SCHEDULED":
        frappe.throw(
            _("Cannot claim procedure in state {0}. Only SCHEDULED procedures can be claimed.").format(
                sps.ups_state
            )
        )
    
    # Call the claim method on the document
    transaction_uid = sps.claim()
    
    return {
        "success": True,
        "transaction_uid": transaction_uid,
        "ups_state": sps.ups_state,
        "message": _("Procedure claimed successfully")
    }


@frappe.whitelist()
def complete_procedure(procedure_step, transaction_uid, output_information=None):
    """
    Complete a Scheduled Procedure Step.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step
        transaction_uid: Transaction UID from claim operation
        output_information: Optional list of output information items
    
    Returns:
        Dictionary with success status
    
    Raises:
        frappe.ValidationError: If procedure cannot be completed
    """
    sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
    
    # Complete the procedure
    sps.complete(transaction_uid)
    
    # Add output information if provided
    if output_information:
        import json
        if isinstance(output_information, str):
            output_information = json.loads(output_information)
        
        for output in output_information:
            sps.append("output_information", output)
        sps.save()
    
    return {
        "success": True,
        "ups_state": sps.ups_state,
        "message": _("Procedure completed successfully")
    }


@frappe.whitelist()
def cancel_procedure(procedure_step, reason, transaction_uid=None):
    """
    Cancel a Scheduled Procedure Step.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step
        reason: Reason for cancellation
        transaction_uid: Transaction UID (required if IN PROGRESS)
    
    Returns:
        Dictionary with success status
    
    Raises:
        frappe.ValidationError: If procedure cannot be canceled
    """
    sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
    
    # Cancel the procedure
    sps.cancel_procedure(reason, transaction_uid)
    
    return {
        "success": True,
        "ups_state": sps.ups_state,
        "message": _("Procedure canceled successfully")
    }


@frappe.whitelist()
def get_modality_list():
    """
    Get list of distinct modalities from scheduled procedures.
    
    Returns:
        List of modality codes
    """
    modalities = frappe.db.get_all(
        "Scheduled Procedure Step",
        filters={"ups_state": ["in", ["SCHEDULED", "IN PROGRESS"]]},
        fields=["modality"],
        distinct=True
    )
    return [m.modality for m in modalities if m.modality]


@frappe.whitelist()
def get_station_list():
    """
    Get list of distinct station AE titles from scheduled procedures.
    
    Returns:
        List of station AE titles
    """
    stations = frappe.db.get_all(
        "Scheduled Procedure Step",
        filters={"ups_state": ["in", ["SCHEDULED", "IN PROGRESS"]]},
        fields=["station_aet"],
        distinct=True
    )
    return [s.station_aet for s in stations if s.station_aet]


@frappe.whitelist()
def get_worklist_counts():
    """
    Get counts of worklist items by state.
    
    Returns:
        Dictionary with counts by state
    """
    from frappe.utils import today
    
    counts = {
        "scheduled": frappe.db.count(
            "Scheduled Procedure Step",
            {"ups_state": "SCHEDULED"}
        ),
        "in_progress": frappe.db.count(
            "Scheduled Procedure Step",
            {"ups_state": "IN PROGRESS"}
        ),
        "completed_today": frappe.db.count(
            "Scheduled Procedure Step",
            {
                "ups_state": "COMPLETED",
                "procedure_end_datetime": [">=", today()]
            }
        ),
        "canceled_today": frappe.db.count(
            "Scheduled Procedure Step",
            {
                "ups_state": "CANCELED",
                "modified": [">=", today()]
            }
        )
    }
    
    return counts
