# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProcedureType(Document):
    """
    Procedure Type DocType
    
    Represents a catalog entry for a type of imaging procedure.
    Used as a template when creating Requested Procedures.
    """
    
    def validate(self):
        """Validate the Procedure Type document."""
        self.validate_codes()
        self.validate_duration()
    
    def validate_codes(self):
        """Ensure at least one code is defined if codification_table exists."""
        # Note: codification_table uses existing Codification Table Row child table
        # We don't require codes as some facilities may not use standard coding
        pass
    
    def validate_duration(self):
        """Ensure typical duration is non-negative if provided."""
        if self.typical_duration and self.typical_duration < 0:
            frappe.throw("Typical Duration cannot be negative")
    
    def get_default_plan(self):
        """
        Get the default Procedure Plan for this Procedure Type.
        
        Returns:
            The default Procedure Plan document, or None if not found
        """
        default_plan = frappe.db.get_value(
            "Procedure Plan",
            {"procedure_type": self.name, "is_default": 1},
            "name"
        )
        
        if default_plan:
            return frappe.get_doc("Procedure Plan", default_plan)
        
        # If no default, try to get any plan
        any_plan = frappe.db.get_value(
            "Procedure Plan",
            {"procedure_type": self.name},
            "name"
        )
        
        if any_plan:
            return frappe.get_doc("Procedure Plan", any_plan)
        
        return None
    
    def get_all_plans(self):
        """
        Get all Procedure Plans for this Procedure Type.
        
        Returns:
            List of Procedure Plan documents
        """
        plans = frappe.get_all(
            "Procedure Plan",
            filters={"procedure_type": self.name},
            order_by="is_default desc, plan_name asc"
        )
        return [frappe.get_doc("Procedure Plan", p.name) for p in plans]
    
    def get_primary_code(self, code_system="CPT"):
        """
        Get the primary code for this procedure from the specified code system.
        
        Args:
            code_system: The coding system to look for (CPT, LOINC, SNOMED-CT, etc.)
        
        Returns:
            Dictionary with code_value, code_meaning, or None if not found
        """
        if not self.codification_table:
            return None
        
        for code in self.codification_table:
            if hasattr(code, 'code_system') and code.code_system == code_system:
                return {
                    "code_value": code.code if hasattr(code, 'code') else None,
                    "code_meaning": code.description if hasattr(code, 'description') else None,
                    "code_system": code_system
                }
        
        return None
