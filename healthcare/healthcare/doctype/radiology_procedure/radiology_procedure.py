# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, get_link_to_form


class RadiologyProcedure(Document):
	def validate(self):
		self.set_title()
		self.set_patient_details()

	def set_title(self):
		self.title = f"{self.patient_name or self.patient} - {self.radiology_template}"

	def set_patient_details(self):
		if self.patient:
			patient = frappe.get_doc("Patient", self.patient)
			self.patient_name = patient.patient_name
			self.patient_sex = patient.sex
			self.patient_age = calculate_age(patient.dob) if patient.dob else None

	def before_submit(self):
		if self.status not in ["Completed", "Cancelled"]:
			self.status = "In Progress"

	def on_submit(self):
		self.update_service_request_status()

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		self.update_service_request_status()

	def update_service_request_status(self):
		if self.service_request:
			if self.status == "Completed":
				frappe.db.set_value(
					"Service Request", self.service_request, "status", "completed-Request Status"
				)
			elif self.status == "Cancelled":
				frappe.db.set_value(
					"Service Request", self.service_request, "status", "revoked-Request Status"
				)
			elif self.status == "In Progress":
				frappe.db.set_value(
					"Service Request", self.service_request, "status", "active-Request Status"
				)

	@frappe.whitelist()
	def complete_procedure(self):
		"""Mark the procedure as completed."""
		if self.docstatus != 1:
			frappe.throw(_("Procedure must be submitted before it can be completed."))
		self.db_set("status", "Completed")
		self.update_service_request_status()
		return True


def calculate_age(dob):
	"""Calculate age from date of birth."""
	if not dob:
		return None
	today = getdate()
	dob = getdate(dob)
	years = today.year - dob.year
	if today.month < dob.month or (today.month == dob.month and today.day < dob.day):
		years -= 1
	return f"{years} Years"
