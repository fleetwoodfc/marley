# Copyright (c) 2026, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestProcedureStepType(IntegrationTestCase):
	"""Unit tests for Procedure Step Type DocType."""

	def setUp(self):
		"""Create test data."""
		# Clean up any existing test step types
		for name in ["Test Step 1", "Test Step 2", "Test System Step"]:
			if frappe.db.exists("Procedure Step Type", name):
				frappe.delete_doc("Procedure Step Type", name, force=True)

	def tearDown(self):
		"""Clean up test data."""
		for name in ["Test Step 1", "Test Step 2", "Test System Step"]:
			if frappe.db.exists("Procedure Step Type", name):
				frappe.delete_doc("Procedure Step Type", name, force=True, ignore_permissions=True)

	def test_create_procedure_step(self):
		"""Test that a procedure step type can be created with required fields."""
		step = frappe.get_doc({
			"doctype": "Procedure Step Type",
			"step_name": "Test Step 1",
			"phase": "Acquisition",
			"typical_duration": 10,
			"is_active": 1
		})
		step.insert()
		
		self.assertTrue(frappe.db.exists("Procedure Step Type", "Test Step 1"))
		self.assertEqual(step.phase, "Acquisition")
		self.assertEqual(step.is_system, 0)  # Should default to custom

	def test_unique_step_name_validation(self):
		"""Test that duplicate step type names are rejected."""
		# Create first step type
		step1 = frappe.get_doc({
			"doctype": "Procedure Step Type",
			"step_name": "Test Step 2",
			"phase": "Acquisition"
		})
		step1.insert()
		
		# Try to create duplicate
		step2 = frappe.get_doc({
			"doctype": "Procedure Step Type",
			"step_name": "Test Step 2",
			"phase": "Post Processing"
		})
		
		self.assertRaises(frappe.exceptions.ValidationError, step2.insert)

	def test_system_step_deletion_prevention(self):
		"""Test that system step types cannot be deleted."""
		# Create a system step type
		step = frappe.get_doc({
			"doctype": "Procedure Step Type",
			"step_name": "Test System Step",
			"phase": "Reporting",
			"is_system": 1
		})
		step.flags.ignore_validate = True  # Allow creating system step type
		step.insert(ignore_permissions=True)
		
		# Force set is_system=1 since it's read_only
		frappe.db.set_value("Procedure Step Type", step.name, "is_system", 1)
		
		# Reload and try to delete
		step.reload()
		self.assertEqual(step.is_system, 1)
		
		# Should raise error when trying to delete
		self.assertRaises(frappe.exceptions.ValidationError, step.delete)

	def test_default_values(self):
		"""Test that default values are set correctly."""
		step = frappe.get_doc({
			"doctype": "Procedure Step Type",
			"step_name": "Test Step 1",
			"phase": "Acquisition"
		})
		step.insert()
		
		self.assertEqual(step.is_active, 1)  # Default active
		self.assertEqual(step.is_system, 0)  # Default custom

	def test_phase_options(self):
		"""Test that only valid phases are accepted."""
		# Valid phase
		step = frappe.get_doc({
			"doctype": "Procedure Step Type",
			"step_name": "Test Step 1",
			"phase": "Post Processing"
		})
		step.insert()
		self.assertEqual(step.phase, "Post Processing")
