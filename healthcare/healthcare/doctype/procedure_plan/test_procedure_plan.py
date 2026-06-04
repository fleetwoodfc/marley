# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
Unit tests for Procedure Plan DocType.

To run:
    bench --site development.localhost run-tests \
        --app healthcare \
        --module healthcare.healthcare.doctype.procedure_plan.test_procedure_plan
"""

import unittest
import frappe
from frappe.tests import IntegrationTestCase


class TestProcedurePlan(IntegrationTestCase):
    """Tests for Procedure Plan DocType."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a test procedure type
        if not frappe.db.exists("Procedure Type", "_Test Plan Procedure Type"):
            cls.procedure_type = frappe.get_doc({
                "doctype": "Procedure Type",
                "procedure_type_name": "_Test Plan Procedure Type",
                "modality": "CT",
                "description": "Test procedure type for plan tests",
            })
            cls.procedure_type.insert(ignore_permissions=True)
            frappe.db.commit()
        else:
            cls.procedure_type = frappe.get_doc("Procedure Type", "_Test Plan Procedure Type")
    
    @classmethod
    def tearDownClass(cls):
        # Delete test plans first
        plans = frappe.get_all(
            "Procedure Plan",
            filters={"procedure_type": "_Test Plan Procedure Type"}
        )
        for plan in plans:
            frappe.delete_doc("Procedure Plan", plan.name, force=True)
        
        # Delete test procedure type
        if frappe.db.exists("Procedure Type", "_Test Plan Procedure Type"):
            frappe.delete_doc("Procedure Type", "_Test Plan Procedure Type", force=True)
        
        frappe.db.commit()
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data."""
        self.test_plan = None
    
    def tearDown(self):
        """Clean up test data."""
        if self.test_plan and frappe.db.exists("Procedure Plan", self.test_plan):
            frappe.delete_doc("Procedure Plan", self.test_plan, force=True)
            frappe.db.commit()
    
    def test_create_procedure_plan(self):
        """Test creating a basic Procedure Plan."""
        plan = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": self.procedure_type.name,
            "plan_name": "_Test Basic Plan",
            "is_default": 0,
        })
        plan.insert(ignore_permissions=True)
        self.test_plan = plan.name
        
        self.assertTrue(frappe.db.exists("Procedure Plan", plan.name))
        self.assertEqual(plan.procedure_type, self.procedure_type.name)
    
    def test_only_one_default_per_procedure_type(self):
        """Test that only one plan can be default per procedure type."""
        # Create first default plan
        plan1 = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": self.procedure_type.name,
            "plan_name": "_Test Default Plan 1",
            "is_default": 1,
        })
        plan1.insert(ignore_permissions=True)
        
        # Create second default plan
        plan2 = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": self.procedure_type.name,
            "plan_name": "_Test Default Plan 2",
            "is_default": 1,
        })
        plan2.insert(ignore_permissions=True)
        
        # Reload plan1 - it should no longer be default
        plan1.reload()
        
        # The controller should ensure only one default
        # Check how many defaults exist
        default_count = frappe.db.count(
            "Procedure Plan",
            filters={
                "procedure_type": self.procedure_type.name,
                "is_default": 1
            }
        )
        
        # Should be exactly one default
        self.assertEqual(default_count, 1)
        
        # Plan2 should be the default (last one set)
        plan2.reload()
        self.assertEqual(plan2.is_default, 1)
        
        # Clean up
        frappe.delete_doc("Procedure Plan", plan1.name, force=True)
        frappe.delete_doc("Procedure Plan", plan2.name, force=True)
    
    def test_plan_with_items(self):
        """Test creating a plan with plan items."""
        # First create a code value if needed
        code_name = "_Test Plan Item Code"
        if not frappe.db.exists("Code Value", code_name):
            code_value = frappe.get_doc({
                "doctype": "Code Value",
                "code_value": "TESTCODE",
                "code_meaning": "Test Protocol Code",
                "code_system": "99LOCAL",
            })
            code_value.insert(ignore_permissions=True)
            code_name = code_value.name
        
        plan = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": self.procedure_type.name,
            "plan_name": "_Test Plan With Items",
            "is_default": 0,
            "plan_items": [
                {
                    "code_value": code_name,
                    "sequence": 1,
                    "expected_duration": 15,
                }
            ]
        })
        plan.insert(ignore_permissions=True)
        self.test_plan = plan.name
        
        # Reload and check items
        plan.reload()
        self.assertEqual(len(plan.plan_items), 1)
        self.assertEqual(plan.plan_items[0].sequence, 1)
    
    def test_plan_items_required_validation(self):
        """Test that plan items may be required (depending on config)."""
        # Create plan without items
        plan = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": self.procedure_type.name,
            "plan_name": "_Test Plan No Items",
            "is_default": 0,
            # No plan_items
        })
        
        # Should still be insertable (items may not be required)
        plan.insert(ignore_permissions=True)
        self.test_plan = plan.name
        
        self.assertTrue(frappe.db.exists("Procedure Plan", plan.name))
    
    def test_procedure_type_required(self):
        """Test that procedure type is required."""
        plan = frappe.get_doc({
            "doctype": "Procedure Plan",
            "plan_name": "_Test Plan No Type",
            # No procedure_type
        })
        
        # Should raise validation error
        with self.assertRaises(frappe.exceptions.MandatoryError):
            plan.insert(ignore_permissions=True)
    
    def test_duplicate_plan_name(self):
        """Test handling of duplicate plan names."""
        # Create first plan
        plan1 = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": self.procedure_type.name,
            "plan_name": "_Test Duplicate Name Plan",
            "is_default": 0,
        })
        plan1.insert(ignore_permissions=True)
        
        # Create second plan with same name
        plan2 = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": self.procedure_type.name,
            "plan_name": "_Test Duplicate Name Plan",  # Same name
            "is_default": 0,
        })
        
        # Depending on setup, this might raise an error or be allowed
        # since plan names don't have to be unique
        try:
            plan2.insert(ignore_permissions=True)
            # If successful, both exist
            self.assertTrue(frappe.db.exists("Procedure Plan", plan2.name))
            frappe.delete_doc("Procedure Plan", plan2.name, force=True)
        except frappe.DuplicateEntryError:
            # If names must be unique, this is expected
            pass
        
        # Clean up
        frappe.delete_doc("Procedure Plan", plan1.name, force=True)


class TestProcedurePlanDefaults(IntegrationTestCase):
    """Tests for default plan behavior."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test procedure types
        for name in ["_Test Defaults Type A", "_Test Defaults Type B"]:
            if not frappe.db.exists("Procedure Type", name):
                frappe.get_doc({
                    "doctype": "Procedure Type",
                    "procedure_type_name": name,
                    "modality": "CT",
                }).insert(ignore_permissions=True)
        frappe.db.commit()
    
    @classmethod
    def tearDownClass(cls):
        # Clean up plans and types
        for name in ["_Test Defaults Type A", "_Test Defaults Type B"]:
            plans = frappe.get_all("Procedure Plan", filters={"procedure_type": name})
            for plan in plans:
                frappe.delete_doc("Procedure Plan", plan.name, force=True)
            if frappe.db.exists("Procedure Type", name):
                frappe.delete_doc("Procedure Type", name, force=True)
        frappe.db.commit()
        super().tearDownClass()
    
    def test_default_plan_per_procedure_type(self):
        """Test that different procedure types can have their own defaults."""
        # Create default plan for Type A
        plan_a = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": "_Test Defaults Type A",
            "plan_name": "Default A",
            "is_default": 1,
        })
        plan_a.insert(ignore_permissions=True)
        
        # Create default plan for Type B
        plan_b = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": "_Test Defaults Type B",
            "plan_name": "Default B",
            "is_default": 1,
        })
        plan_b.insert(ignore_permissions=True)
        
        # Both should be default for their respective types
        plan_a.reload()
        plan_b.reload()
        
        self.assertEqual(plan_a.is_default, 1)
        self.assertEqual(plan_b.is_default, 1)
    
    def test_setting_new_default_unsets_old(self):
        """Test that setting a new default unsets the old one."""
        # Create first default
        old_default = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": "_Test Defaults Type A",
            "plan_name": "Old Default",
            "is_default": 1,
        })
        old_default.insert(ignore_permissions=True)
        
        # Verify it's default
        self.assertEqual(old_default.is_default, 1)
        
        # Create new default
        new_default = frappe.get_doc({
            "doctype": "Procedure Plan",
            "procedure_type": "_Test Defaults Type A",
            "plan_name": "New Default",
            "is_default": 1,
        })
        new_default.insert(ignore_permissions=True)
        
        # Reload old default
        old_default.reload()
        
        # Old should no longer be default
        self.assertEqual(old_default.is_default, 0)
        self.assertEqual(new_default.is_default, 1)


if __name__ == "__main__":
    unittest.main()
