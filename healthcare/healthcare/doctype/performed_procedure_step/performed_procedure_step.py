# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class PerformedProcedureStep(Document):
    """
    Performed Procedure Step - Records actual procedure execution details.
    
    This DocType captures what was actually performed, which may differ
    from what was scheduled. It links back to the Scheduled Procedure Step
    and includes output information (DICOM Series/SOPs created).
    """
    
    def before_insert(self):
        """
        Copy scheduled protocol codes as starting point.
        Set default values from scheduled step.
        """
        if self.scheduled_procedure_step:
            sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
            
            # Copy patient if not set
            if not self.patient:
                self.patient = sps.patient
            
            # Copy protocol codes from scheduled step
            if not self.performed_protocol_codes and sps.protocol_codes:
                for code in sps.protocol_codes:
                    self.append("performed_protocol_codes", {
                        "code_value": code.code_value,
                        "coding_scheme_designator": code.coding_scheme_designator,
                        "code_meaning": code.code_meaning,
                        "coding_scheme_version": code.coding_scheme_version
                    })
        
        # Set default start time
        if not self.start_datetime:
            self.start_datetime = now_datetime()
        
        # Set default performing operator
        if not self.performing_operator:
            self.performing_operator = frappe.session.user
    
    def validate(self):
        """
        Validate the performed procedure step.
        
        - Ensure scheduled procedure step is IN PROGRESS
        - Validate timing (end_datetime >= start_datetime)
        - Require discontinuation reason if status is Discontinued
        """
        self._validate_scheduled_step()
        self._validate_timing()
        self._validate_discontinuation()
    
    def _validate_scheduled_step(self):
        """Ensure the scheduled step is in the correct state."""
        if self.scheduled_procedure_step:
            sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
            
            # For new documents, SPS should be IN PROGRESS
            if self.is_new() and sps.ups_state not in ["IN PROGRESS", "SCHEDULED"]:
                frappe.throw(
                    _("Cannot create Performed Procedure Step for {0} in state {1}. "
                      "Scheduled Procedure Step must be IN PROGRESS.").format(
                        self.scheduled_procedure_step,
                        sps.ups_state
                    )
                )
    
    def _validate_timing(self):
        """Validate start and end datetime."""
        if self.start_datetime and self.end_datetime:
            from frappe.utils import get_datetime
            
            start = get_datetime(self.start_datetime)
            end = get_datetime(self.end_datetime)
            
            if end < start:
                frappe.throw(_("End Date/Time cannot be before Start Date/Time"))
    
    def _validate_discontinuation(self):
        """Require reason if procedure was discontinued."""
        if self.status == "Discontinued" and not self.discontinuation_reason:
            frappe.throw(_("Discontinuation Reason is required when status is Discontinued"))
    
    def on_update(self):
        """
        Handle status changes.
        
        If status changes to Completed or Discontinued, update the
        Scheduled Procedure Step accordingly.
        """
        if self.has_value_changed("status"):
            self._update_scheduled_step()
    
    def _update_scheduled_step(self):
        """Update the scheduled procedure step based on performed step status."""
        if not self.scheduled_procedure_step:
            return
        
        sps = frappe.get_doc("Scheduled Procedure Step", self.scheduled_procedure_step)
        
        if self.status == "Completed":
            # Complete the scheduled step
            if sps.ups_state == "IN PROGRESS":
                sps.complete(sps.transaction_uid)
                
                # Set end datetime
                sps.procedure_end_datetime = self.end_datetime or now_datetime()
                sps.save()
                
        elif self.status == "Discontinued":
            # Cancel the scheduled step
            if sps.ups_state == "IN PROGRESS":
                sps.cancel_procedure(
                    reason=self.discontinuation_reason,
                    transaction_uid=sps.transaction_uid
                )
    
    def get_output_series_count(self):
        """Get count of output series."""
        return len([o for o in self.output_information if o.reference_type == "Series"])
    
    def get_output_instance_count(self):
        """Get count of output instances (SOPs)."""
        return len([o for o in self.output_information if o.reference_type == "Instance"])
