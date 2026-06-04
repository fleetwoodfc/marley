# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from healthcare.healthcare.dicom import generate_study_instance_uid


class RequestedProcedure(Document):
    """
    Requested Procedure DocType
    
    Represents a specific imaging procedure requested as part of an
    Imaging Service Request. Each Requested Procedure gets a unique
    Study Instance UID and can have one or more Scheduled Procedure Steps.
    """
    
    def before_insert(self):
        """Generate Study Instance UID before inserting."""
        if not self.study_instance_uid:
            self.study_instance_uid = generate_study_instance_uid()
    
    def after_insert(self):
        """
        Actions after the Requested Procedure is inserted.
        
        Gets the default Procedure Plan from the Procedure Type
        and creates SPS entries based on plan items.
        """
        # Only auto-create SPS if we have a procedure type
        if not self.procedure_type:
            return
        
        # Get the default Procedure Plan for this Procedure Type
        default_plan = self.get_default_plan()
        
        if default_plan and default_plan.plan_items:
            self.create_sps_from_plan(default_plan)
    
    def get_default_plan(self):
        """
        Get the default Procedure Plan for the Procedure Type.
        
        Returns:
            Procedure Plan document or None
        """
        if not self.procedure_type:
            return None
        
        # Find the default plan for this procedure type
        default_plan_name = frappe.db.get_value(
            "Procedure Plan",
            {
                "procedure_type": self.procedure_type,
                "is_default": 1
            },
            "name"
        )
        
        if default_plan_name:
            return frappe.get_doc("Procedure Plan", default_plan_name)
        
        # If no default plan, check if there's only one plan
        plans = frappe.get_all(
            "Procedure Plan",
            filters={"procedure_type": self.procedure_type},
            limit=2
        )
        
        if len(plans) == 1:
            return frappe.get_doc("Procedure Plan", plans[0].name)
        
        return None
    
    def create_sps_from_plan(self, plan):
        """
        Create Scheduled Procedure Steps from a Procedure Plan.
        
        Args:
            plan: Procedure Plan document
        """
        if not plan.plan_items:
            return
        
        # Get the parent ISR
        isr = self.get_parent_isr()
        if not isr:
            frappe.log_error(f"Could not find parent ISR for Requested Procedure {self.name}")
            return
        
        # Get Procedure Type details for defaults
        procedure_type = None
        if self.procedure_type:
            procedure_type = frappe.get_doc("Procedure Type", self.procedure_type)
        
        for item in plan.plan_items:
            try:
                sps = frappe.get_doc({
                    "doctype": "Scheduled Procedure Step",
                    "imaging_service_request": isr.name,
                    "requested_procedure": self.name,
                    "study_instance_uid": self.study_instance_uid,
                    "patient": isr.patient,
                    "modality": procedure_type.modality if procedure_type else None,
                    "procedure_step_label": self._build_step_label(item, procedure_type),
                    "scheduled_datetime": isr.scheduled_datetime if hasattr(isr, 'scheduled_datetime') else frappe.utils.now_datetime(),
                    "expected_duration": item.expected_duration or (procedure_type.default_duration if procedure_type and hasattr(procedure_type, 'default_duration') else None),
                    "ups_state": "SCHEDULED",
                    "ups_sync_status": "pending",
                })
                
                # Add protocol codes from plan item
                if item.code_value:
                    sps.append("protocol_codes", {
                        "code_value": item.code_value
                    })
                
                sps.insert(ignore_permissions=True)
                
                frappe.logger().info(f"Created SPS {sps.name} from plan item for {self.name}")
                
            except Exception as e:
                frappe.log_error(f"Failed to create SPS from plan item: {e}")
    
    def get_parent_isr(self):
        """
        Get the parent Imaging Service Request.
        
        Returns:
            Imaging Service Request document or None
        """
        if hasattr(self, 'parenttype') and self.parenttype == "Imaging Service Request":
            if self.parent:
                return frappe.get_doc("Imaging Service Request", self.parent)
        
        # Try to find ISR by querying
        isr_name = frappe.db.get_value(
            "Requested Procedure",
            {"name": self.name},
            "parent"
        )
        
        if isr_name:
            return frappe.get_doc("Imaging Service Request", isr_name)
        
        return None
    
    def _build_step_label(self, plan_item, procedure_type):
        """
        Build a label for the Scheduled Procedure Step.
        
        Args:
            plan_item: Procedure Plan Item
            procedure_type: Procedure Type document
            
        Returns:
            str: Step label
        """
        parts = []
        
        if procedure_type:
            parts.append(procedure_type.name)
        
        if plan_item.code_value:
            # Get the code meaning
            code_meaning = frappe.db.get_value(
                "Code Value",
                plan_item.code_value,
                "code_meaning"
            )
            if code_meaning:
                parts.append(code_meaning)
            else:
                parts.append(plan_item.code_value)
        
        if plan_item.sequence and len(plan_item.get_parenttype().plan_items if hasattr(plan_item, 'get_parenttype') else []) > 1:
            parts.append(f"Step {plan_item.sequence}")
        
        return " - ".join(parts) if parts else _("Procedure Step")
