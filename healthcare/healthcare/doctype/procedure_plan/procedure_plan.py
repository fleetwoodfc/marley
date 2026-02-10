# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProcedurePlan(Document):
    """
    Procedure Plan DocType
    
    Defines a plan/template for performing a Procedure Type.
    Contains plan items that specify the protocol steps.
    """
    
    def validate(self):
        """Validate the Procedure Plan document."""
        self.validate_plan_items()
        self.validate_default()
        self.set_item_sequences()
    
    def validate_plan_items(self):
        """Ensure at least one plan item is defined."""
        if not self.plan_items or len(self.plan_items) == 0:
            frappe.throw("At least one Plan Item is required")
    
    def validate_default(self):
        """Ensure only one default plan per procedure type."""
        if self.is_default:
            # Unset other defaults for the same procedure type
            frappe.db.sql("""
                UPDATE `tabProcedure Plan`
                SET is_default = 0
                WHERE procedure_type = %s
                AND name != %s
                AND is_default = 1
            """, (self.procedure_type, self.name or ""))
    
    def set_item_sequences(self):
        """Auto-set sequence numbers if not provided."""
        for idx, item in enumerate(self.plan_items, start=1):
            if not item.sequence:
                item.sequence = idx
    
    def get_protocol_codes(self):
        """
        Get all protocol codes from plan items.
        
        Returns:
            List of dictionaries with code details
        """
        codes = []
        for item in self.plan_items:
            if item.protocol_code:
                codes.append({
                    "code_value": item.protocol_code,
                    "coding_scheme_designator": item.protocol_code_system or "LOCAL",
                    "code_meaning": item.protocol_code_meaning or item.step_label,
                    "sequence": item.sequence
                })
        return codes
    
    def get_total_duration(self):
        """
        Calculate total expected duration from all plan items.
        
        Returns:
            Total duration in minutes
        """
        total = 0
        for item in self.plan_items:
            if item.expected_duration:
                total += item.expected_duration
        return total
