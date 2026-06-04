# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, get_datetime, nowdate

from healthcare.healthcare.dicom import (
    generate_accession_number,
    get_accession_number_issuer,
    generate_study_instance_uid,
    generate_sop_instance_uid,
)


class ImagingServiceRequest(Document):
    """
    Imaging Service Request DocType
    
    Represents an order for one or more imaging procedures.
    Contains Requested Procedures as child rows.
    On submit, creates Scheduled Procedure Steps for each Requested Procedure.
    """
    
    def before_insert(self):
        """Generate accession number and issuer before inserting."""
        if not self.accession_number:
            self.accession_number = generate_accession_number()
        
        if not self.issuer_of_accession_number:
            self.issuer_of_accession_number = get_accession_number_issuer()
    
    def validate(self):
        """Validate the Imaging Service Request."""
        self.validate_requested_procedures()
        self.set_patient_age()
        self.generate_study_uids()
    
    def validate_requested_procedures(self):
        """Ensure at least one requested procedure is defined."""
        if not self.requested_procedures or len(self.requested_procedures) == 0:
            frappe.throw(_("At least one Requested Procedure is required"))
    
    def set_patient_age(self):
        """Calculate and set patient age from DOB."""
        if self.patient:
            patient_doc = frappe.get_cached_doc("Patient", self.patient)
            if patient_doc.dob:
                from frappe.utils import get_datetime
                from datetime import datetime
                
                dob = getdate(patient_doc.dob)
                today = getdate(nowdate())
                age_years = today.year - dob.year
                if today.month < dob.month or (today.month == dob.month and today.day < dob.day):
                    age_years -= 1
                self.patient_age = f"{age_years} Years"
    
    def generate_study_uids(self):
        """Generate Study Instance UIDs for requested procedures that don't have one."""
        for rp in self.requested_procedures:
            if not rp.study_instance_uid:
                rp.study_instance_uid = generate_study_instance_uid()
    
    def on_submit(self):
        """Create Scheduled Procedure Steps when the request is submitted."""
        self.create_scheduled_procedure_steps()
        self.db_set("status", "Ordered")
    
    def create_scheduled_procedure_steps(self):
        """
        Create a Scheduled Procedure Step for each Requested Procedure.
        
        The SPS is the UPS Workitem that gets pushed to the DICOM server.
        """
        for rp_link in self.requested_procedures:
            # Dereference the Requested Procedure Link to get the actual doc
            rp_doc = frappe.get_doc("Requested Procedure", rp_link.requested_procedure)
            sps = self._create_sps_for_requested_procedure(rp_link, rp_doc)
            
            # Update the Requested Procedure with the SPS reference
            frappe.db.set_value(
                "Requested Procedure",
                rp_link.requested_procedure,
                "scheduled_procedure_step",
                sps.name
            )
    
    def _create_sps_for_requested_procedure(self, rp_link, rp_doc):
        """
        Create a Scheduled Procedure Step for a Requested Procedure.
        
        Args:
            rp_link: The Requested Procedure Link child row
            rp_doc: The actual Requested Procedure document
        
        Returns:
            The created Scheduled Procedure Step document
        """
        # Get procedure type details
        procedure_type = frappe.get_cached_doc("Procedure Type", rp_doc.procedure_type)
        
        # Get default plan for protocol codes
        default_plan = procedure_type.get_default_plan()
        protocol_codes = []
        if default_plan:
            protocol_codes = default_plan.get_protocol_codes()
        
        # Create the Scheduled Procedure Step
        sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "imaging_service_request": self.name,
            "requested_procedure": rp_link.requested_procedure,
            "patient": self.patient,
            "study_instance_uid": rp_link.study_instance_uid,
            "sop_instance_uid": generate_sop_instance_uid(),
            "scheduled_datetime": rp_doc.scheduled_datetime or self.order_datetime,
            "modality": rp_doc.modality or procedure_type.default_modality,
            "procedure_step_label": rp_doc.procedure_description or procedure_type.procedure_name,
            "expected_duration": procedure_type.typical_duration,
            "ups_state": "SCHEDULED",
            "ups_sync_status": "pending"
        })
        
        # Add protocol codes from the plan.
        # Protocol Code Item.code is a Link to Code Value.  We only append rows
        # where a matching Code Value record actually exists; plain local/free-text
        # codes are stored on the Procedure Plan and are visible there.
        for code in protocol_codes:
            cv = code.get("code_value")
            if cv and frappe.db.exists("Code Value", cv):
                sps.append("protocol_codes", {"code": cv})
        
        sps.flags.ignore_mandatory = True   # allow empty protocol_codes table
        sps.insert()
        return sps
    
    def on_cancel(self):
        """Handle cancellation of the Imaging Service Request."""
        self.cancel_scheduled_procedure_steps()
        self.db_set("status", "Cancelled")
    
    def cancel_scheduled_procedure_steps(self):
        """Cancel all Scheduled Procedure Steps that are still SCHEDULED."""
        for rp_link in self.requested_procedures:
            rp_doc = frappe.get_doc("Requested Procedure", rp_link.requested_procedure)
            if rp_doc.scheduled_procedure_step:
                sps = frappe.get_doc("Scheduled Procedure Step", rp_doc.scheduled_procedure_step)
                if sps.ups_state == "SCHEDULED":
                    sps.cancel_procedure("Order cancelled")
    
    def get_dashboard_data(self):
        """Return data for the document dashboard."""
        return {
            "fieldname": "imaging_service_request",
            "transactions": [
                {
                    "label": _("Related Documents"),
                    "items": ["Scheduled Procedure Step"]
                }
            ]
        }
    
    def update_status(self):
        """Update the status based on child Scheduled Procedure Steps."""
        if not self.requested_procedures:
            return
        
        sps_list = []
        for rp_link in self.requested_procedures:
            rp_doc = frappe.get_doc("Requested Procedure", rp_link.requested_procedure)
            if rp_doc.scheduled_procedure_step:
                sps = frappe.get_doc("Scheduled Procedure Step", rp_doc.scheduled_procedure_step)
                sps_list.append(sps.ups_state)
        
        if not sps_list:
            return
        
        # Determine overall status
        if all(state == "COMPLETED" for state in sps_list):
            self.db_set("status", "Completed")
        elif all(state == "CANCELED" for state in sps_list):
            self.db_set("status", "Cancelled")
        elif any(state == "IN PROGRESS" for state in sps_list):
            self.db_set("status", "In Progress")
        elif all(state == "SCHEDULED" for state in sps_list):
            self.db_set("status", "Ordered")
