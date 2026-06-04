# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
UPS Event Handler for Frappe Healthcare

This module handles incoming UPS-RS WebSocket events and updates
the corresponding Scheduled Procedure Step documents.

Event Types:
    - WorkitemCreated: A new workitem was created on the DICOM server
    - WorkitemStateChanged: A workitem's state changed
    - WorkitemCanceled: A workitem was canceled
    - ProgressReport: Progress update on a workitem
    - CancelRequest: A cancellation was requested
"""

import frappe
from frappe import _
from typing import Optional

from healthcare.healthcare.dicom.ups_rs import Tag, ProcedureStepState


class UPSEventHandler:
    """
    Handles UPS-RS events and updates Scheduled Procedure Step documents.
    
    This class processes events received via WebSocket from the DICOM server
    and synchronizes the local Frappe DocTypes with the remote state.
    """
    
    def __init__(self):
        self.event_handlers = {
            "WorkitemCreated": self._handle_workitem_created,
            "WorkitemStateChanged": self._handle_state_changed,
            "WorkitemCanceled": self._handle_workitem_canceled,
            "StateReport": self._handle_state_report,
            "ProgressReport": self._handle_progress_report,
            "CancelRequest": self._handle_cancel_request,
        }
    
    def handle_event(self, event: dict) -> bool:
        """
        Handle an incoming UPS event.
        
        Args:
            event: The event dictionary containing event_type and workitem data
            
        Returns:
            True if event was handled successfully, False otherwise
        """
        event_type = event.get("event_type") or event.get("eventType")
        
        if not event_type:
            frappe.logger().warning("UPS Event: Missing event_type")
            return False
        
        handler = self.event_handlers.get(event_type)
        if not handler:
            frappe.logger().warning(f"UPS Event: Unknown event type '{event_type}'")
            return False
        
        try:
            return handler(event)
        except Exception as e:
            frappe.log_error(f"UPS Event Handler error for {event_type}: {e}")
            return False
    
    def _extract_sop_instance_uid(self, event: dict) -> Optional[str]:
        """Extract SOP Instance UID from event data."""
        workitem = event.get("workitem", event.get("data", {}))
        
        # Try standard tag
        if Tag.SOPInstanceUID in workitem:
            values = workitem[Tag.SOPInstanceUID].get("Value", [])
            if values:
                return values[0]
        
        # Try direct workitem_uid field
        if "workitem_uid" in event:
            return event["workitem_uid"]
        
        return None
    
    def _extract_state(self, event: dict) -> Optional[str]:
        """Extract procedure step state from event data."""
        workitem = event.get("workitem", event.get("data", {}))
        
        if Tag.ProcedureStepState in workitem:
            values = workitem[Tag.ProcedureStepState].get("Value", [])
            if values:
                return values[0]
        
        return None
    
    def _get_sps_by_sop_uid(self, sop_instance_uid: str) -> Optional["frappe._dict"]:
        """Look up Scheduled Procedure Step by SOP Instance UID."""
        sps_list = frappe.get_all(
            "Scheduled Procedure Step",
            filters={"sop_instance_uid": sop_instance_uid},
            fields=["name", "ups_state", "transaction_uid", "ups_sync_status"]
        )
        
        if sps_list:
            return sps_list[0]
        return None
    
    def _handle_workitem_created(self, event: dict) -> bool:
        """
        Handle WorkitemCreated event.
        
        If a workitem is created externally (not by Frappe), we may want to
        create a corresponding SPS. For now, we just log the event.
        """
        sop_uid = self._extract_sop_instance_uid(event)
        
        if not sop_uid:
            frappe.logger().warning("WorkitemCreated: Missing SOP Instance UID")
            return False
        
        # Check if we already have this SPS
        existing = self._get_sps_by_sop_uid(sop_uid)
        
        if existing:
            frappe.logger().debug(f"WorkitemCreated: SPS already exists for {sop_uid}")
            return True
        
        # For now, just log external workitem creation
        # Future: Could create SPS from external workitem
        frappe.logger().info(f"WorkitemCreated: External workitem {sop_uid} - not importing")
        
        # Publish event for any listeners
        frappe.publish_realtime(
            "ups_workitem_created",
            {
                "sop_instance_uid": sop_uid,
                "event": event
            },
            after_commit=False
        )
        
        return True
    
    def _handle_state_changed(self, event: dict) -> bool:
        """
        Handle WorkitemStateChanged event.
        
        Updates the local SPS to match the remote state.
        """
        sop_uid = self._extract_sop_instance_uid(event)
        new_state = self._extract_state(event)
        
        if not sop_uid:
            frappe.logger().warning("StateChanged: Missing SOP Instance UID")
            return False
        
        if not new_state:
            frappe.logger().warning(f"StateChanged: Missing state for {sop_uid}")
            return False
        
        sps = self._get_sps_by_sop_uid(sop_uid)
        
        if not sps:
            frappe.logger().warning(f"StateChanged: No SPS found for {sop_uid}")
            return False
        
        # Check if state actually changed
        if sps.ups_state == new_state:
            frappe.logger().debug(f"StateChanged: SPS {sps.name} already in state {new_state}")
            return True
        
        # Update the SPS state
        try:
            # Use db.set_value to avoid triggering hooks (which would cause infinite sync loop)
            frappe.db.set_value(
                "Scheduled Procedure Step",
                sps.name,
                {
                    "ups_state": new_state,
                    "ups_sync_status": "synced",
                    "ups_sync_at": frappe.utils.now()
                },
                update_modified=True
            )
            frappe.db.commit()
            
            frappe.logger().info(f"StateChanged: Updated SPS {sps.name} to {new_state}")
            
            # Publish realtime update
            self._publish_sps_update(sps.name, new_state)
            
            return True
            
        except Exception as e:
            frappe.log_error(f"StateChanged: Failed to update SPS {sps.name}: {e}")
            return False
    
    def _handle_state_report(self, event: dict) -> bool:
        """Handle StateReport event (alias for state change)."""
        return self._handle_state_changed(event)
    
    def _handle_workitem_canceled(self, event: dict) -> bool:
        """
        Handle WorkitemCanceled event.
        
        Sets the SPS state to CANCELED.
        """
        sop_uid = self._extract_sop_instance_uid(event)
        
        if not sop_uid:
            frappe.logger().warning("WorkitemCanceled: Missing SOP Instance UID")
            return False
        
        sps = self._get_sps_by_sop_uid(sop_uid)
        
        if not sps:
            frappe.logger().warning(f"WorkitemCanceled: No SPS found for {sop_uid}")
            return False
        
        # Extract cancellation reason if available
        workitem = event.get("workitem", event.get("data", {}))
        reason = None
        if "00741238" in workitem:  # ReasonForCancellation
            values = workitem["00741238"].get("Value", [])
            if values:
                reason = values[0]
        
        try:
            update_values = {
                "ups_state": ProcedureStepState.CANCELED.value,
                "ups_sync_status": "synced",
                "ups_sync_at": frappe.utils.now()
            }
            
            frappe.db.set_value(
                "Scheduled Procedure Step",
                sps.name,
                update_values,
                update_modified=True
            )
            frappe.db.commit()
            
            frappe.logger().info(f"WorkitemCanceled: Updated SPS {sps.name} to CANCELED")
            
            # Add comment with reason
            if reason:
                doc = frappe.get_doc("Scheduled Procedure Step", sps.name)
                doc.add_comment("Info", f"Canceled via DICOM: {reason}")
            
            # Publish realtime update
            self._publish_sps_update(sps.name, ProcedureStepState.CANCELED.value, reason=reason)
            
            return True
            
        except Exception as e:
            frappe.log_error(f"WorkitemCanceled: Failed to update SPS {sps.name}: {e}")
            return False
    
    def _handle_progress_report(self, event: dict) -> bool:
        """
        Handle ProgressReport event.
        
        Progress reports contain information about procedure completion percentage.
        """
        sop_uid = self._extract_sop_instance_uid(event)
        
        if not sop_uid:
            return False
        
        sps = self._get_sps_by_sop_uid(sop_uid)
        
        if not sps:
            return False
        
        # Extract progress information
        workitem = event.get("workitem", event.get("data", {}))
        
        # Publish progress update to connected clients
        frappe.publish_realtime(
            "ups_progress_report",
            {
                "sps_name": sps.name,
                "sop_instance_uid": sop_uid,
                "data": workitem
            },
            doctype="Scheduled Procedure Step",
            docname=sps.name
        )
        
        return True
    
    def _handle_cancel_request(self, event: dict) -> bool:
        """
        Handle CancelRequest event.
        
        Someone is requesting cancellation of a procedure in progress.
        This creates a notification for the performing operator.
        """
        sop_uid = self._extract_sop_instance_uid(event)
        
        if not sop_uid:
            return False
        
        sps = self._get_sps_by_sop_uid(sop_uid)
        
        if not sps:
            return False
        
        # Get the full SPS document
        sps_doc = frappe.get_doc("Scheduled Procedure Step", sps.name)
        
        # Extract reason
        workitem = event.get("workitem", event.get("data", {}))
        reason = None
        if "00741238" in workitem:
            values = workitem["00741238"].get("Value", [])
            if values:
                reason = values[0]
        
        # Determine recipient (performing practitioner or claimed_by)
        recipient = sps_doc.performing_practitioner or sps_doc.claimed_by
        
        if recipient:
            # Create notification
            try:
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "subject": _("Cancellation Requested: {0}").format(sps.name),
                    "email_content": _("A cancellation has been requested for {0}. Reason: {1}").format(
                        sps.name,
                        reason or _("Not specified")
                    ),
                    "for_user": recipient,
                    "document_type": "Scheduled Procedure Step",
                    "document_name": sps.name,
                    "type": "Alert",
                }).insert(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(f"CancelRequest: Failed to create notification: {e}")
        
        # Publish realtime event
        frappe.publish_realtime(
            "ups_cancel_request",
            {
                "sps_name": sps.name,
                "sop_instance_uid": sop_uid,
                "reason": reason
            },
            doctype="Scheduled Procedure Step",
            docname=sps.name
        )
        
        return True
    
    def _publish_sps_update(self, sps_name: str, new_state: str, reason: str = None):
        """Publish SPS update to connected clients via Frappe realtime."""
        frappe.publish_realtime(
            "ups_state_changed",
            {
                "sps_name": sps_name,
                "ups_state": new_state,
                "reason": reason
            },
            doctype="Scheduled Procedure Step",
            docname=sps_name
        )
        
        # Also publish to global worklist channel
        frappe.publish_realtime(
            "worklist_updated",
            {
                "sps_name": sps_name,
                "ups_state": new_state
            }
        )


# Convenience function for external use
def handle_ups_event(event: dict) -> bool:
    """
    Handle an incoming UPS event.
    
    This is the main entry point for processing UPS events.
    
    Args:
        event: The event dictionary containing event_type and workitem data
        
    Returns:
        True if event was handled successfully, False otherwise
        
    Example:
        >>> event = {
        ...     "event_type": "WorkitemStateChanged",
        ...     "workitem": {
        ...         "00080018": {"vr": "UI", "Value": ["1.2.3.4.5"]},
        ...         "00741000": {"vr": "CS", "Value": ["COMPLETED"]}
        ...     }
        ... }
        >>> handle_ups_event(event)
        True
    """
    handler = UPSEventHandler()
    return handler.handle_event(event)


def update_sps_from_remote_state(sop_instance_uid: str, new_state: str) -> bool:
    """
    Update a Scheduled Procedure Step from a remote state change.
    
    Args:
        sop_instance_uid: The SOP Instance UID of the workitem
        new_state: The new procedure step state
        
    Returns:
        True if update was successful, False otherwise
    """
    event = {
        "event_type": "WorkitemStateChanged",
        "workitem": {
            Tag.SOPInstanceUID: {"vr": "UI", "Value": [sop_instance_uid]},
            Tag.ProcedureStepState: {"vr": "CS", "Value": [new_state]}
        }
    }
    return handle_ups_event(event)
