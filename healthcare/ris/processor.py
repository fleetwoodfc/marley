# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import logging

import frappe

logger = logging.getLogger(__name__)


def get_patient_by_pid(pid_3=None, pid_5=None, pid_7=None):
	"""
	Get a Patient document by PID fields from HL7 message.

	Args:
		pid_3: Patient identifier (e.g., MRN or unique ID)
		pid_5: Patient name
		pid_7: Date of birth (raw value string)

	Returns:
		Patient document if found or created, None on failure.

	Lookup behavior:
		1. If PID-3 is provided, search for Patient by uid (patient identifier)
		2. If no match and PID-5 + PID-7 are provided, search by patient_name + dob
		3. If no match found, create a new Patient with available data

	Raises:
		No exceptions are raised; all errors are logged and None is returned.
	"""
	try:
		patient = None

		# Step 1: Search by PID-3 (patient identifier)
		if pid_3:
			patient = frappe.db.get_value("Patient", {"uid": pid_3}, "name")
			if patient:
				return frappe.get_doc("Patient", patient)

		# Step 2: Fallback search by PID-5 (name) + PID-7 (DOB)
		if pid_5 and pid_7:
			patient = frappe.db.get_value(
				"Patient", {"patient_name": pid_5, "dob": pid_7}, "name"
			)
			if patient:
				return frappe.get_doc("Patient", patient)

		# Step 3: Create new Patient if no match found
		# Only create if we have at least PID-3 (identifier)
		if pid_3:
			return _create_patient_from_pid(pid_3, pid_5, pid_7)

		# If no PID-3 and no match found, we cannot create a patient
		logger.warning(
			"Cannot create Patient: PID-3 (identifier) is required. "
			"PID-5=%s, PID-7=%s",
			pid_5,
			pid_7,
		)
		return None

	except Exception as e:
		logger.exception(
			"Error in get_patient_by_pid: PID-3=%s, PID-5=%s, PID-7=%s. Error: %s",
			pid_3,
			pid_5,
			pid_7,
			str(e),
		)
		return None


def _create_patient_from_pid(pid_3, pid_5=None, pid_7=None):
	"""
	Create a new Patient document from PID fields.

	Args:
		pid_3: Patient identifier (required)
		pid_5: Patient name (optional)
		pid_7: Date of birth (optional)

	Returns:
		Inserted Patient document, or None on failure.
	"""
	try:
		# Determine patient name
		if pid_5:
			patient_name = pid_5
		else:
			patient_name = f"HL7 Patient {pid_3}" if pid_3 else "HL7 Patient"

		# Create new Patient document
		new_doc = frappe.new_doc("Patient")
		new_doc.uid = pid_3
		new_doc.first_name = patient_name
		# Set dob from PID-7 if present (use raw value string)
		if pid_7:
			new_doc.dob = pid_7

		# Set a default gender if not available from HL7 message
		# Query available genders once and select the most appropriate default
		available_genders = frappe.get_all("Gender", pluck="name")
		default_gender = None
		for preferred in ["Other", "Prefer not to say", "Male"]:
			if preferred in available_genders:
				default_gender = preferred
				break
		if default_gender:
			new_doc.sex = default_gender

		# Insert with ignore_permissions=True as per requirements
		new_doc.insert(ignore_permissions=True, ignore_mandatory=True)

		logger.info(
			"Created new Patient from HL7 message: name=%s, uid=%s, dob=%s",
			new_doc.name,
			pid_3,
			pid_7,
		)

		return new_doc

	except Exception as e:
		logger.exception(
			"Failed to create Patient from HL7 message: PID-3=%s, PID-5=%s, PID-7=%s. Error: %s",
			pid_3,
			pid_5,
			pid_7,
			str(e),
		)
		return None
