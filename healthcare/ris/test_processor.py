# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from healthcare.ris.processor import get_patient_by_pid


class TestGetPatientByPid(IntegrationTestCase):
	"""Test cases for the get_patient_by_pid function."""

	def setUp(self):
		"""Clean up test patients before each test."""
		frappe.db.sql("""DELETE FROM `tabPatient` WHERE uid LIKE '_Test_PID_%'""")
		frappe.db.sql("""DELETE FROM `tabPatient` WHERE patient_name LIKE 'HL7 Patient _Test_%'""")
		frappe.db.sql("""DELETE FROM `tabPatient` WHERE first_name LIKE 'Test_PID_%'""")

	def tearDown(self):
		"""Clean up test patients after each test."""
		frappe.db.sql("""DELETE FROM `tabPatient` WHERE uid LIKE '_Test_PID_%'""")
		frappe.db.sql("""DELETE FROM `tabPatient` WHERE patient_name LIKE 'HL7 Patient _Test_%'""")
		frappe.db.sql("""DELETE FROM `tabPatient` WHERE first_name LIKE 'Test_PID_%'""")

	def test_find_patient_by_pid_3(self):
		"""Test finding an existing patient by PID-3 (identifier/uid)."""
		# Create a test patient with a known uid
		patient = frappe.get_doc({
			"doctype": "Patient",
			"first_name": "Test_PID_Lookup",
			"uid": "_Test_PID_001",
			"sex": "Male",
		})
		patient.insert(ignore_permissions=True)

		# Search for patient by PID-3
		result = get_patient_by_pid(pid_3="_Test_PID_001")

		self.assertIsNotNone(result)
		self.assertEqual(result.uid, "_Test_PID_001")
		self.assertEqual(result.first_name, "Test_PID_Lookup")

	def test_find_patient_by_name_and_dob_fallback(self):
		"""Test finding an existing patient by PID-5 (name) + PID-7 (DOB) when PID-3 doesn't match."""
		# Create a test patient with name and DOB
		patient = frappe.get_doc({
			"doctype": "Patient",
			"first_name": "Test PID Fallback",
			"dob": "1990-01-15",
			"sex": "Female",
		})
		patient.insert(ignore_permissions=True)

		# Search for patient by name and DOB (no matching PID-3)
		result = get_patient_by_pid(
			pid_3="_Test_PID_NONEXISTENT",
			pid_5="Test PID Fallback",
			pid_7="1990-01-15"
		)

		self.assertIsNotNone(result)
		self.assertEqual(result.patient_name, "Test PID Fallback")

	def test_create_patient_when_not_found(self):
		"""Test creating a new patient when PID-3 is provided but no match is found."""
		# Ensure no patient exists with this PID-3
		self.assertFalse(frappe.db.exists("Patient", {"uid": "_Test_PID_NEW_001"}))

		# Call get_patient_by_pid with new identifier
		result = get_patient_by_pid(
			pid_3="_Test_PID_NEW_001",
			pid_5="John Test Doe",
			pid_7="1985-05-20"
		)

		# Verify patient was created
		self.assertIsNotNone(result)
		self.assertEqual(result.uid, "_Test_PID_NEW_001")
		self.assertEqual(result.first_name, "John Test Doe")
		# Handle date comparison - result.dob may be a date object
		if result.dob:
			self.assertEqual(str(result.dob), "1985-05-20")

		# Verify patient exists in database
		self.assertTrue(frappe.db.exists("Patient", {"uid": "_Test_PID_NEW_001"}))

	def test_create_patient_with_default_name(self):
		"""Test creating a patient with default name when PID-5 is not provided."""
		# Call with PID-3 only (no name)
		result = get_patient_by_pid(pid_3="_Test_PID_NONAME_001")

		self.assertIsNotNone(result)
		self.assertEqual(result.uid, "_Test_PID_NONAME_001")
		# Should have default name format
		self.assertEqual(result.first_name, "HL7 Patient _Test_PID_NONAME_001")

	def test_create_patient_without_dob(self):
		"""Test creating a patient when PID-7 (DOB) is not provided."""
		result = get_patient_by_pid(
			pid_3="_Test_PID_NODOB_001",
			pid_5="Patient Without DOB"
		)

		self.assertIsNotNone(result)
		self.assertEqual(result.uid, "_Test_PID_NODOB_001")
		self.assertEqual(result.first_name, "Patient Without DOB")
		self.assertIsNone(result.dob)

	def test_returns_none_without_pid_3(self):
		"""Test that None is returned when PID-3 is not provided and no match found."""
		# Call without PID-3
		result = get_patient_by_pid(pid_5="Unknown Patient", pid_7="2000-01-01")

		# Should return None since we can't create a patient without PID-3
		self.assertIsNone(result)

	def test_returns_none_with_no_params(self):
		"""Test that None is returned when no parameters are provided."""
		result = get_patient_by_pid()
		self.assertIsNone(result)
