# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
Cancellation Request DocType Controller

This DocType handles requests to cancel a Scheduled Procedure Step
that is currently being performed by another operator.

Workflow:
1. Clinician requests cancellation of an IN PROGRESS procedure
2. Notification is sent to the performing operator
3. Operator can accept (cancels the procedure) or decline (continues)
4. Requester is notified of the decision

DICOM Integration:
- Cancel requests are sent via UPS-RS Request Cancel endpoint
- dcm4chee-arc notifies the operator via WebSocket
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class CancellationRequest(Document):
    """Cancellation Request DocType controller."""
    
    def validate(self):
        """Validate the cancellation request."""
        self.validate_sps_state()
        self.validate_not_self_cancel()
    
    def validate_sps_state(self):
        """Validate that the SPS is in a cancellable state."""
        if not self.scheduled_procedure_step:
            return
        
        sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
        
        # Can only request cancellation for IN PROGRESS procedures
        if sps.ups_state not in ["IN PROGRESS"]:
            frappe.throw(
                _("Can only request cancellation for procedures in progress. Current state: {0}").format(
                    sps.ups_state
                )
            )
    
    def validate_not_self_cancel(self):
        """Validate that the requester is not the operator."""
        if not self.scheduled_procedure_step:
            return
        
        sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
        
        # Check if requester is the one performing the procedure
        if sps.claimed_by == self.requester:
            frappe.throw(
                _("You cannot request cancellation of a procedure you are performing. "
                  "Use the Cancel button directly on the Scheduled Procedure Step.")
            )
    
    def after_insert(self):
        """Actions after the cancellation request is created."""
        self.send_notification_to_operator()
        self.send_ups_cancel_request()
    
    def send_notification_to_operator(self):
        """Send notification to the performing operator."""
        sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
        
        # Determine the operator
        operator = sps.claimed_by or sps.performing_practitioner
        
        if not operator:
            frappe.log_error(f"No operator found for SPS {sps.name}")
            return
        
        try:
            # Create notification
            notification = frappe.get_doc({
                "doctype": "Notification Log",
                "subject": _("Cancellation Requested: {0}").format(sps.name),
                "email_content": _("A cancellation has been requested for {0}. Reason: {1}").format(
                    sps.procedure_step_label or sps.name,
                    self.reason
                ),
                "for_user": operator,
                "document_type": "Cancellation Request",
                "document_name": self.name,
                "type": "Alert",
            })
            notification.insert(ignore_permissions=True)
            
            # Also publish realtime event for immediate notification
            frappe.publish_realtime(
                "ups_cancel_request_received",
                {
                    "cancellation_request": self.name,
                    "sps_name": sps.name,
                    "sps_label": sps.procedure_step_label,
                    "patient": sps.patient,
                    "patient_name": sps.patient_name,
                    "requester": self.requester,
                    "reason": self.reason
                },
                user=operator
            )
            
        except Exception as e:
            frappe.log_error(f"Failed to send cancellation notification: {e}")
    
    def send_ups_cancel_request(self):
        """Send cancel request via UPS-RS to the DICOM server."""
        from healthcare.healthcare.dicom.ups_sync import send_cancel_request
        
        try:
            sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
            
            if sps.sop_instance_uid:
                # Get requester display name
                requester_name = None
                if self.requester:
                    requester_name = frappe.db.get_value("User", self.requester, "full_name")
                
                send_cancel_request(
                    procedure_step=sps.name,
                    reason=self.reason,
                    contact_name=requester_name
                )
        except Exception as e:
            frappe.log_error(f"Failed to send UPS cancel request: {e}")
    
    @frappe.whitelist()
    def accept(self, decision_reason: str = None):
        """
        Accept the cancellation request and cancel the procedure.
        
        Args:
            decision_reason: Optional reason for accepting
        """
        if self.status != "Pending":
            frappe.throw(_("This request has already been processed"))
        
        # Update request status
        self.status = "Accepted"
        self.decision_by = frappe.session.user
        self.decision_at = now_datetime()
        self.decision_reason = decision_reason
        self.save(ignore_permissions=True)
        
        # Cancel the SPS
        sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
        
        try:
            # Use the SPS cancel method
            if hasattr(sps, 'cancel_procedure'):
                sps.cancel_procedure(reason=self.reason)
            else:
                # Direct state update if method doesn't exist
                sps.ups_state = "CANCELED"
                sps.save(ignore_permissions=True)
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(f"Failed to cancel SPS: {e}")
            frappe.throw(_("Failed to cancel the procedure: {0}").format(str(e)))
        
        # Notify the requester
        self.notify_requester("accepted")
        
        frappe.msgprint(_("Cancellation request accepted. The procedure has been canceled."))
    
    @frappe.whitelist()
    def decline(self, decision_reason: str = None):
        """
        Decline the cancellation request.
        
        Args:
            decision_reason: Optional reason for declining
        """
        if self.status != "Pending":
            frappe.throw(_("This request has already been processed"))
        
        if not decision_reason:
            frappe.throw(_("Please provide a reason for declining the cancellation request"))
        
        # Update request status
        self.status = "Declined"
        self.decision_by = frappe.session.user
        self.decision_at = now_datetime()
        self.decision_reason = decision_reason
        self.save(ignore_permissions=True)
        
        # Notify the requester
        self.notify_requester("declined")
        
        frappe.msgprint(_("Cancellation request declined."))
    
    @frappe.whitelist()
    def withdraw(self):
        """Withdraw the cancellation request (by the requester)."""
        if self.status != "Pending":
            frappe.throw(_("This request has already been processed"))
        
        if self.requester != frappe.session.user:
            frappe.throw(_("Only the requester can withdraw this request"))
        
        self.status = "Withdrawn"
        self.decision_at = now_datetime()
        self.save(ignore_permissions=True)
        
        frappe.msgprint(_("Cancellation request withdrawn."))
    
    def notify_requester(self, decision: str):
        """
        Notify the requester about the decision.
        
        Args:
            decision: "accepted" or "declined"
        """
        try:
            sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
            
            if decision == "accepted":
                subject = _("Cancellation Accepted: {0}").format(sps.name)
                message = _("Your cancellation request for {0} has been accepted. The procedure has been canceled.").format(
                    sps.procedure_step_label or sps.name
                )
                indicator = "green"
            else:
                subject = _("Cancellation Declined: {0}").format(sps.name)
                message = _("Your cancellation request for {0} has been declined. Reason: {1}").format(
                    sps.procedure_step_label or sps.name,
                    self.decision_reason or _("Not specified")
                )
                indicator = "red"
            
            # Create notification
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": subject,
                "email_content": message,
                "for_user": self.requester,
                "document_type": "Cancellation Request",
                "document_name": self.name,
                "type": "Alert",
            }).insert(ignore_permissions=True)
            
            # Publish realtime event
            frappe.publish_realtime(
                "ups_cancel_request_decision",
                {
                    "cancellation_request": self.name,
                    "sps_name": sps.name,
                    "decision": decision,
                    "reason": self.decision_reason
                },
                user=self.requester
            )
            
        except Exception as e:
            frappe.log_error(f"Failed to notify requester: {e}")


# Whitelisted methods for the form
@frappe.whitelist()
def accept_cancellation(name: str, decision_reason: str = None):
    """Accept a cancellation request."""
    doc = frappe.get_doc("Cancellation Request", name)
    doc.accept(decision_reason)
    return {"status": "accepted"}


@frappe.whitelist()
def decline_cancellation(name: str, decision_reason: str):
    """Decline a cancellation request."""
    doc = frappe.get_doc("Cancellation Request", name)
    doc.decline(decision_reason)
    return {"status": "declined"}


@frappe.whitelist()
def withdraw_cancellation(name: str):
    """Withdraw a cancellation request."""
    doc = frappe.get_doc("Cancellation Request", name)
    doc.withdraw()
    return {"status": "withdrawn"}
