# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from healthcare.healthcare.dicom import generate_sop_instance_uid, generate_transaction_uid


# Valid state transitions per DICOM UPS specification
VALID_TRANSITIONS = {
    None: ["SCHEDULED"],
    "SCHEDULED": ["IN PROGRESS", "CANCELED"],
    "IN PROGRESS": ["COMPLETED", "CANCELED"],
    "COMPLETED": [],  # Final state
    "CANCELED": [],   # Final state
}


class ScheduledProcedureStep(Document):
    """
    Scheduled Procedure Step DocType
    
    Represents a UPS Workitem - a unit of work scheduled for a specific
    modality/station. This is the core entity for worklist management.
    
    State machine:
        SCHEDULED → IN PROGRESS → COMPLETED
                               ↘ CANCELED
        SCHEDULED → CANCELED (via Request Cancel)
    """
    
    def before_insert(self):
        """Generate SOP Instance UID before inserting."""
        if not self.sop_instance_uid:
            self.sop_instance_uid = generate_sop_instance_uid()
    
    def validate(self):
        """Validate the Scheduled Procedure Step."""
        self.validate_state_transition()
    
    def validate_state_transition(self):
        """
        Validate that the state transition is allowed.
        
        Per DICOM UPS spec, only certain transitions are valid:
        - SCHEDULED → IN PROGRESS (claim)
        - SCHEDULED → CANCELED (request cancel)
        - IN PROGRESS → COMPLETED (complete)
        - IN PROGRESS → CANCELED (cancel)
        - COMPLETED and CANCELED are final states
        """
        if not self.has_value_changed("ups_state"):
            return
        
        old_doc = self.get_doc_before_save()
        old_state = old_doc.ups_state if old_doc else None
        new_state = self.ups_state
        
        valid_next_states = VALID_TRANSITIONS.get(old_state, [])
        
        if new_state not in valid_next_states:
            frappe.throw(
                _("Invalid state transition: {0} → {1}. Allowed: {2}").format(
                    old_state or "New",
                    new_state,
                    ", ".join(valid_next_states) if valid_next_states else "None (final state)"
                )
            )
        
        # Validate Transaction UID for transitions from IN PROGRESS
        if old_state == "IN PROGRESS" and new_state in ["COMPLETED", "CANCELED"]:
            if not self.transaction_uid:
                frappe.throw(_("Transaction UID is required to transition from IN PROGRESS"))
    
    def on_update(self):
        """Handle post-update actions."""
        # Update parent ISR status
        if self.imaging_service_request:
            isr = frappe.get_doc("Imaging Service Request", self.imaging_service_request)
            isr.update_status()
        
        # Queue UPS sync if state changed
        if self.has_value_changed("ups_state"):
            self.queue_ups_sync()
    
    def queue_ups_sync(self):
        """Queue a background job to sync state to DICOM server."""
        if not frappe.db.get_single_value("Healthcare Settings", "enable_ups_sync"):
            return
        
        frappe.enqueue(
            "healthcare.healthcare.dicom.ups_sync.sync_state_change",
            procedure_step=self.name,
            queue="short"
        )
    
    @frappe.whitelist()
    def claim(self):
        """
        Claim this procedure step (transition to IN PROGRESS).
        
        Generates a Transaction UID that locks the workitem.
        Only the holder of the Transaction UID can complete or cancel.
        
        Returns:
            dict: Contains the generated transaction_uid
        """
        if self.ups_state != "SCHEDULED":
            frappe.throw(_("Can only claim SCHEDULED procedure steps"))
        
        # Generate Transaction UID for locking
        self.transaction_uid = generate_transaction_uid()
        self.ups_state = "IN PROGRESS"
        self.claimed_by = frappe.session.user
        self.claimed_at = now_datetime()
        
        self.save()
        
        return {
            "success": True,
            "transaction_uid": self.transaction_uid
        }
    
    @frappe.whitelist()
    def complete(self, transaction_uid):
        """
        Complete this procedure step (transition to COMPLETED).
        
        Requires the correct Transaction UID for authorization.
        
        Args:
            transaction_uid: The Transaction UID received when claiming
        
        Returns:
            dict: Success status
        """
        if self.ups_state != "IN PROGRESS":
            frappe.throw(_("Can only complete IN PROGRESS procedure steps"))
        
        if self.transaction_uid != transaction_uid:
            frappe.throw(_("Invalid Transaction UID"))
        
        self.ups_state = "COMPLETED"
        self.save()
        
        return {"success": True}
    
    @frappe.whitelist()
    def cancel_procedure(self, reason, transaction_uid=None):
        """
        Cancel this procedure step (transition to CANCELED).
        
        For SCHEDULED steps, Transaction UID is optional (auto-generated).
        For IN PROGRESS steps, requires the correct Transaction UID.
        
        Args:
            reason: Reason for cancellation
            transaction_uid: Required if canceling from IN PROGRESS
        
        Returns:
            dict: Success status
        """
        if self.ups_state not in ["SCHEDULED", "IN PROGRESS"]:
            frappe.throw(_("Cannot cancel procedure in {0} state").format(self.ups_state))
        
        if self.ups_state == "IN PROGRESS":
            if not transaction_uid or self.transaction_uid != transaction_uid:
                frappe.throw(_("Invalid Transaction UID for cancellation"))
        else:
            # For SCHEDULED, generate Transaction UID for the cancel action
            if not self.transaction_uid:
                self.transaction_uid = generate_transaction_uid()
        
        self.ups_state = "CANCELED"
        
        # Store cancellation reason - will be used by Performed Procedure Step
        self.add_comment("Info", _("Cancellation reason: {0}").format(reason))
        
        self.save()
        
        return {"success": True}
    
    def get_dashboard_data(self):
        """Return data for the document dashboard."""
        return {
            "fieldname": "scheduled_procedure_step",
            "transactions": [
                {
                    "label": _("Related Documents"),
                    "items": ["Performed Procedure Step", "Imaging Service Request"]
                }
            ]
        }
