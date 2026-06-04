# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
MWL-RS Synchronization Service

Synchronizes Scheduled Procedure Steps with dcm4chee Modality Worklist
via the MWL-RS (Modality Worklist RESTful Services) API.

Unlike UPS-RS which manages workflow state, MWL is a query-only service
that provides scheduled procedure information to imaging modalities.
"""

import re
from typing import Optional, Dict, Any, List

import frappe
from frappe import _
from frappe.utils import now_datetime

from healthcare.healthcare.dicom.mwl_rs import MwlRSClient, MwlItem, MwlRSError


# ==============================================================================
# Client Factory (T029)
# ==============================================================================

def get_mwl_client() -> Optional[MwlRSClient]:
    """
    Get a configured MWL-RS client from Healthcare Settings.
    
    Returns:
        MwlRSClient instance or None if MWL sync is disabled
        
    Notes:
        - Returns None if enable_mwl_sync is False
        - Falls back to ups_rs_url if mwl_rs_url not set
        - Logs error if neither URL is configured
    """
    settings = frappe.get_single("Healthcare Settings")
    
    if not settings.enable_mwl_sync:
        return None
    
    # Use MWL-RS URL or fall back to UPS-RS URL
    base_url = settings.mwl_rs_url or settings.ups_rs_url
    
    if not base_url:
        frappe.log_error(
            "MWL-RS URL not configured in Healthcare Settings",
            "MWL Sync Error"
        )
        return None
    
    # Extract AET from URL if not separately configured
    # URL format: http://host:port/dcm4chee-arc/aets/{AET}/rs
    aet = getattr(settings, "dicom_aet", None)
    if not aet:
        match = re.search(r'/aets/([^/]+)/rs', base_url)
        if match:
            aet = match.group(1)
        else:
            aet = "DCM4CHEE"  # Default fallback
    
    # Get optional authentication credentials
    username = getattr(settings, "mwl_rs_username", None)
    password = getattr(settings, "mwl_rs_password", None)
    
    # Get actual password value if it's a password field
    if password:
        password = frappe.utils.password.get_decrypted_password(
            "Healthcare Settings",
            settings.name,
            "mwl_rs_password"
        )
    
    return MwlRSClient(
        base_url=base_url,
        aet=aet,
        username=username or None,
        password=password or None
    )


# ==============================================================================
# Core Sync Functions (T030-T032)
# ==============================================================================

def sync_to_mwl(procedure_step: str, **kwargs) -> bool:
    """
    Sync a Scheduled Procedure Step to dcm4chee MWL.
    
    Creates or updates the MWL item based on current SPS state.
    
    Args:
        procedure_step: Name (ID) of the Scheduled Procedure Step document
        **kwargs: Additional arguments passed by job queue (ignored)
        
    Returns:
        True if sync successful, False otherwise
        
    Side Effects:
        - Updates mwl_sync_status, mwl_sync_at, mwl_sync_error on SPS document
        - Logs sync activity
    """
    client = get_mwl_client()
    if not client:
        frappe.logger().debug(f"MWL sync disabled, skipping {procedure_step}")
        return False
    
    try:
        sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
        
        # Only sync if in a state that should be on MWL
        if sps.ups_state and sps.ups_state != "SCHEDULED":
            frappe.logger().debug(
                f"SPS {procedure_step} not in SCHEDULED state, skipping MWL sync"
            )
            return False
        
        # Check if SPS has required fields for MWL
        if not sps.study_instance_uid:
            frappe.log_error(
                f"SPS {procedure_step} missing study_instance_uid",
                "MWL Sync Error"
            )
            _update_mwl_sync_status(procedure_step, "error", "Missing study_instance_uid")
            return False
        
        # Patient is required by dcm4chee MWL
        if not sps.patient:
            frappe.log_error(
                f"SPS {procedure_step} missing patient",
                "MWL Sync Error"
            )
            _update_mwl_sync_status(procedure_step, "error", "Missing patient - required for MWL")
            return False
        
        # Create MWL item from SPS document
        mwl_item = MwlItem.from_scheduled_procedure_step(sps)
        
        # Create/update on dcm4chee
        client.create_mwl_item(mwl_item)
        
        # Update sync status on success
        _update_mwl_sync_status(procedure_step, "synced")
        
        frappe.logger().info(
            f"MWL sync successful: {procedure_step} → StudyUID={sps.study_instance_uid}"
        )
        return True
        
    except MwlRSError as e:
        error_msg = str(e)
        frappe.log_error(
            f"MWL sync failed for {procedure_step}: {error_msg}",
            "MWL Sync Error"
        )
        _update_mwl_sync_status(procedure_step, "error", error_msg)
        return False
        
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(
            f"MWL sync unexpected error for {procedure_step}: {error_msg}",
            "MWL Sync Error"
        )
        _update_mwl_sync_status(procedure_step, "error", error_msg)
        return False


def remove_from_mwl(procedure_step: str, **kwargs) -> bool:
    """
    Remove a Scheduled Procedure Step from dcm4chee MWL.
    
    Called when SPS transitions to IN PROGRESS, COMPLETED, or CANCELED.
    
    Args:
        procedure_step: Name (ID) of the Scheduled Procedure Step document
        **kwargs: Additional arguments passed by job queue (ignored)
        
    Returns:
        True if removed (or didn't exist), False on error
        
    Side Effects:
        - Updates mwl_sync_status to "not_applicable" on success
        - Logs removal activity
    """
    client = get_mwl_client()
    if not client:
        frappe.logger().debug(f"MWL sync disabled, skipping removal for {procedure_step}")
        return False
    
    try:
        sps = frappe.get_doc("Scheduled Procedure Step", procedure_step)
        
        # Need study_instance_uid and sps_id for deletion
        if not sps.study_instance_uid:
            frappe.logger().debug(
                f"SPS {procedure_step} has no study_instance_uid, nothing to remove"
            )
            _update_mwl_sync_status(procedure_step, "not_applicable")
            return True
        
        # Use SPS document name as the SPS ID
        sps_id = sps.name
        
        # Delete from dcm4chee
        deleted = client.delete_mwl_item(sps.study_instance_uid, sps_id)
        
        # Update sync status
        _update_mwl_sync_status(procedure_step, "not_applicable")
        
        if deleted:
            frappe.logger().info(
                f"MWL item removed: {procedure_step} (StudyUID={sps.study_instance_uid})"
            )
        else:
            frappe.logger().debug(
                f"MWL item not found for removal: {procedure_step}"
            )
        
        return True
        
    except MwlRSError as e:
        error_msg = str(e)
        frappe.log_error(
            f"MWL removal failed for {procedure_step}: {error_msg}",
            "MWL Sync Error"
        )
        _update_mwl_sync_status(procedure_step, "error", error_msg)
        return False
        
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(
            f"MWL removal unexpected error for {procedure_step}: {error_msg}",
            "MWL Sync Error"
        )
        _update_mwl_sync_status(procedure_step, "error", error_msg)
        return False


def update_mwl_attributes(procedure_step: str, **kwargs) -> bool:
    """
    Update MWL item attributes after SPS modification.
    
    Called when SPS attributes change (patient, time, station, etc.)
    while still in SCHEDULED state.
    
    Args:
        procedure_step: Name (ID) of the Scheduled Procedure Step document
        **kwargs: Additional arguments passed by job queue (ignored)
        
    Returns:
        True if update successful, False otherwise
        
    Side Effects:
        - Updates mwl_sync_at on success
        - Logs update activity
    """
    # For MWL-RS, update is same as create (idempotent)
    return sync_to_mwl(procedure_step, **kwargs)


# ==============================================================================
# Bulk Sync (for User Story 5 - T051-T052)
# ==============================================================================

def bulk_sync_to_mwl(
    filters: Optional[Dict[str, Any]] = None,
    batch_size: int = 50
) -> Dict[str, Any]:
    """
    Bulk synchronize SCHEDULED procedure steps to MWL.
    
    Creates MWL items for all SCHEDULED SPSs that aren't already synced.
    
    Args:
        filters: Additional filters for SPS selection
        batch_size: Number of SPSs to process in each batch
        
    Returns:
        {
            "total": int,        # Total SPSs found
            "synced": int,       # Successfully synced
            "skipped": int,      # Already synced
            "failed": int,       # Failed to sync
            "errors": List[str]  # Error messages
        }
    """
    client = get_mwl_client()
    if not client:
        return {
            "total": 0,
            "synced": 0,
            "skipped": 0,
            "failed": 0,
            "errors": ["MWL sync is not enabled in Healthcare Settings"]
        }
    
    # Build filters for SCHEDULED SPSs
    sps_filters = {
        "ups_state": "SCHEDULED"
    }
    if filters:
        sps_filters.update(filters)
    
    # Get all matching SPSs
    sps_list = frappe.get_all(
        "Scheduled Procedure Step",
        filters=sps_filters,
        fields=["name", "mwl_sync_status", "study_instance_uid"],
        order_by="creation"
    )
    
    result = {
        "total": len(sps_list),
        "synced": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    for i, sps in enumerate(sps_list):
        # Skip already synced
        if sps.mwl_sync_status == "synced":
            result["skipped"] += 1
            continue
        
        # Skip if missing study_instance_uid
        if not sps.study_instance_uid:
            result["skipped"] += 1
            continue
        
        try:
            if sync_to_mwl(sps.name):
                result["synced"] += 1
            else:
                result["failed"] += 1
        except Exception as e:
            result["failed"] += 1
            result["errors"].append(f"{sps.name}: {str(e)}")
        
        # Log progress every batch_size items
        if (i + 1) % batch_size == 0:
            frappe.logger().info(
                f"MWL bulk sync progress: {i + 1}/{result['total']} processed"
            )
        
        # Commit after each batch to prevent transaction timeout
        if (i + 1) % batch_size == 0:
            frappe.db.commit()
    
    frappe.logger().info(
        f"MWL bulk sync complete: "
        f"total={result['total']}, synced={result['synced']}, "
        f"skipped={result['skipped']}, failed={result['failed']}"
    )
    
    return result


# ==============================================================================
# Reconciliation (for Polish phase - T057)
# ==============================================================================

def reconcile_mwl() -> Dict[str, Any]:
    """
    Reconcile local SPS state with dcm4chee MWL.
    
    Identifies orphaned MWL items and missing sync records.
    Does NOT automatically fix - returns report for admin review.
    
    Returns:
        {
            "orphaned_mwl_items": List[str],      # Study UIDs in MWL but not local
            "missing_mwl_items": List[str],       # SPS names that should be on MWL
            "status_mismatches": List[Dict]       # Items with conflicting status
        }
    """
    client = get_mwl_client()
    if not client:
        return {
            "orphaned_mwl_items": [],
            "missing_mwl_items": [],
            "status_mismatches": [],
            "error": "MWL sync is not enabled"
        }
    
    result = {
        "orphaned_mwl_items": [],
        "missing_mwl_items": [],
        "status_mismatches": []
    }
    
    try:
        # Get all MWL items from dcm4chee
        mwl_items = client.search_mwl_items(limit=10000)
        mwl_study_uids = {item.study_instance_uid for item in mwl_items}
        
        # Get all SCHEDULED SPSs from local
        scheduled_sps = frappe.get_all(
            "Scheduled Procedure Step",
            filters={
                "ups_state": "SCHEDULED",
                "study_instance_uid": ["is", "set"]
            },
            fields=["name", "study_instance_uid", "mwl_sync_status"]
        )
        local_study_uids = {sps.study_instance_uid for sps in scheduled_sps}
        
        # Find orphaned MWL items (in dcm4chee but not in local SCHEDULED state)
        result["orphaned_mwl_items"] = list(mwl_study_uids - local_study_uids)
        
        # Find missing MWL items (SCHEDULED locally but not in dcm4chee)
        for sps in scheduled_sps:
            if sps.study_instance_uid not in mwl_study_uids:
                result["missing_mwl_items"].append(sps.name)
            elif sps.mwl_sync_status != "synced":
                result["status_mismatches"].append({
                    "sps_name": sps.name,
                    "study_instance_uid": sps.study_instance_uid,
                    "local_status": sps.mwl_sync_status,
                    "issue": "In MWL but local status not 'synced'"
                })
        
    except MwlRSError as e:
        result["error"] = str(e)
    
    return result


# ==============================================================================
# Helper Functions
# ==============================================================================

def _update_mwl_sync_status(
    procedure_step: str,
    status: str,
    error_msg: Optional[str] = None
) -> None:
    """Update MWL sync status fields on SPS document."""
    values = {
        "mwl_sync_status": status,
    }
    
    if status == "synced":
        values["mwl_sync_at"] = now_datetime()
        values["mwl_sync_error"] = None
    elif status == "error":
        values["mwl_sync_error"] = error_msg
    elif status == "not_applicable":
        values["mwl_sync_error"] = None
    
    frappe.db.set_value(
        "Scheduled Procedure Step",
        procedure_step,
        values,
        update_modified=False
    )


# ==============================================================================
# Whitelisted API Endpoints (for UI actions - T036, T045, T052)
# ==============================================================================

@frappe.whitelist()
def sync_sps_to_mwl(procedure_step: str) -> Dict[str, Any]:
    """
    Whitelisted API to manually sync an SPS to MWL.
    
    Called from SPS form "Sync to MWL" button.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step
        
    Returns:
        {"success": bool, "message": str}
    """
    try:
        success = sync_to_mwl(procedure_step)
        if success:
            return {
                "success": True,
                "message": _("Successfully synced to Modality Worklist")
            }
        else:
            return {
                "success": False,
                "message": _("Failed to sync to MWL. Check error log for details.")
            }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def remove_sps_from_mwl(procedure_step: str) -> Dict[str, Any]:
    """
    Whitelisted API to manually remove an SPS from MWL.
    
    Called from SPS form "Remove from MWL" button.
    
    Args:
        procedure_step: Name of the Scheduled Procedure Step
        
    Returns:
        {"success": bool, "message": str}
    """
    try:
        success = remove_from_mwl(procedure_step)
        if success:
            return {
                "success": True,
                "message": _("Successfully removed from Modality Worklist")
            }
        else:
            return {
                "success": False,
                "message": _("Failed to remove from MWL. Check error log for details.")
            }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def bulk_sync_scheduled_to_mwl() -> Dict[str, Any]:
    """
    Whitelisted API for bulk MWL synchronization.
    
    Called from Healthcare Settings "Bulk Sync to MWL" button.
    
    Returns:
        Bulk sync result dictionary
    """
    return bulk_sync_to_mwl()
