# Copyright (c) 2026, Healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, time_diff_in_seconds, getdate, nowdate, nowtime


class Visit(Document):
	def validate(self):
		self.set_title()
		self.set_patient_age()
		self.validate_visit_date()
		self.calculate_visit_duration()

	def before_save(self):
		self.update_status_on_timing()

	def set_title(self):
		self.title = f"{self.patient_name or self.patient} - {self.visit_date}"

	def set_patient_age(self):
		if self.patient:
			patient_doc = frappe.get_cached_doc("Patient", self.patient)
			if patient_doc.dob:
				self.patient_age = patient_doc.calculate_age().get("age_in_string", "")

	def validate_visit_date(self):
		if self.visit_date and getdate(self.visit_date) > getdate(nowdate()):
			if self.status not in ["Scheduled"]:
				frappe.throw(_("Future visits can only have 'Scheduled' status"))

	def calculate_visit_duration(self):
		"""Calculate duration between arrival and departure"""
		if self.arrival_time and self.departure_time:
			# Convert times to seconds for duration field
			arrival_seconds = time_to_seconds(self.arrival_time)
			departure_seconds = time_to_seconds(self.departure_time)
			if departure_seconds > arrival_seconds:
				self.visit_duration = departure_seconds - arrival_seconds

	def update_status_on_timing(self):
		"""Automatically update status based on timing fields"""
		if self.departure_time and self.status not in ["Completed", "Cancelled"]:
			self.status = "Completed"
		elif self.arrival_time and self.status == "Scheduled":
			self.status = "Arrived"

	@frappe.whitelist()
	def check_in(self):
		"""Mark patient as arrived"""
		if self.status != "Scheduled":
			frappe.throw(_("Can only check in scheduled visits"))
		
		self.arrival_time = nowtime()
		self.status = "Arrived"
		self.save()
		frappe.msgprint(_("Patient checked in at {0}").format(self.arrival_time))

	@frappe.whitelist()
	def start_visit(self):
		"""Mark visit as in progress"""
		if self.status not in ["Scheduled", "Arrived"]:
			frappe.throw(_("Cannot start a visit that is not scheduled or arrived"))
		
		if not self.arrival_time:
			self.arrival_time = nowtime()
		self.status = "In Progress"
		self.save()
		frappe.msgprint(_("Visit started"))

	@frappe.whitelist()
	def check_out(self):
		"""Mark patient as departed / visit completed"""
		if self.status in ["Completed", "Cancelled", "No Show"]:
			frappe.throw(_("Visit is already {0}").format(self.status))
		
		self.departure_time = nowtime()
		self.status = "Completed"
		self.save()
		frappe.msgprint(_("Patient checked out at {0}").format(self.departure_time))

	@frappe.whitelist()
	def mark_no_show(self):
		"""Mark patient as no show"""
		if self.status not in ["Scheduled"]:
			frappe.throw(_("Can only mark scheduled visits as no show"))
		
		self.status = "No Show"
		self.save()
		frappe.msgprint(_("Visit marked as No Show"))

	@frappe.whitelist()
	def cancel_visit(self):
		"""Cancel the visit"""
		if self.status == "Completed":
			frappe.throw(_("Cannot cancel a completed visit"))
		
		self.status = "Cancelled"
		self.save()
		frappe.msgprint(_("Visit cancelled"))

	@frappe.whitelist()
	def create_encounter(self):
		"""Create a Patient Encounter for this visit"""
		if not self.patient:
			frappe.throw(_("Patient is required to create an encounter"))
		
		encounter = frappe.new_doc("Patient Encounter")
		encounter.patient = self.patient
		encounter.visit = self.name
		encounter.company = self.company
		if self.primary_practitioner:
			encounter.practitioner = self.primary_practitioner
		if self.medical_department:
			encounter.medical_department = self.medical_department
		
		return encounter

	@frappe.whitelist()
	def create_appointment(self):
		"""Create a Patient Appointment linked to this visit"""
		if not self.patient:
			frappe.throw(_("Patient is required to create an appointment"))
		
		appointment = frappe.new_doc("Patient Appointment")
		appointment.patient = self.patient
		appointment.visit = self.name
		appointment.company = self.company
		appointment.appointment_date = self.visit_date
		if self.primary_practitioner:
			appointment.practitioner = self.primary_practitioner
		if self.service_unit:
			appointment.service_unit = self.service_unit
		
		return appointment

	@frappe.whitelist()
	def get_visit_summary(self):
		"""Get summary of all activities in this visit"""
		summary = {
			"appointments": [],
			"encounters": [],
			"service_requests": [],
			"lab_tests": [],
			"procedures": [],
			"invoices": []
		}
		
		# Get linked appointments
		for row in self.appointments or []:
			if row.appointment:
				appt = frappe.get_doc("Patient Appointment", row.appointment)
				summary["appointments"].append({
					"name": appt.name,
					"practitioner": appt.practitioner_name,
					"status": appt.status,
					"time": appt.appointment_time
				})
		
		# Get linked encounters
		for row in self.encounters or []:
			if row.encounter:
				enc = frappe.get_doc("Patient Encounter", row.encounter)
				summary["encounters"].append({
					"name": enc.name,
					"practitioner": enc.practitioner_name,
					"date": enc.encounter_date
				})
		
		# Get linked service requests
		for row in self.service_requests or []:
			if row.service_request:
				sr = frappe.get_doc("Service Request", row.service_request)
				summary["service_requests"].append({
					"name": sr.name,
					"template": sr.template_dn,
					"status": sr.status
				})
		
		return summary


def time_to_seconds(time_value):
	"""Convert time string or timedelta to seconds"""
	if isinstance(time_value, str):
		parts = time_value.split(":")
		hours = int(parts[0])
		minutes = int(parts[1]) if len(parts) > 1 else 0
		seconds = int(float(parts[2])) if len(parts) > 2 else 0
		return hours * 3600 + minutes * 60 + seconds
	return 0


@frappe.whitelist()
def get_visit_for_patient(patient, visit_date=None):
	"""Get or create a visit for a patient on a given date"""
	if not visit_date:
		visit_date = nowdate()
	
	# Check if visit exists for this patient on this date
	existing_visit = frappe.db.get_value(
		"Visit",
		{"patient": patient, "visit_date": visit_date, "status": ["not in", ["Completed", "Cancelled", "No Show"]]},
		"name"
	)
	
	if existing_visit:
		return frappe.get_doc("Visit", existing_visit)
	
	return None


@frappe.whitelist()
def create_visit_from_appointment(appointment_name):
	"""Create a visit from a patient appointment"""
	appointment = frappe.get_doc("Patient Appointment", appointment_name)
	
	# Check if visit already exists for this date
	existing_visit = get_visit_for_patient(appointment.patient, appointment.appointment_date)
	if existing_visit:
		# Add appointment to existing visit
		existing_visit.append("appointments", {"appointment": appointment_name})
		existing_visit.save()
		return existing_visit
	
	# Create new visit
	visit = frappe.new_doc("Visit")
	visit.patient = appointment.patient
	visit.visit_date = appointment.appointment_date
	visit.scheduled_time = appointment.appointment_time
	visit.company = appointment.company
	visit.service_unit = appointment.service_unit
	visit.primary_practitioner = appointment.practitioner
	visit.medical_department = appointment.department
	visit.insurance_policy = appointment.insurance_policy
	
	visit.append("appointments", {"appointment": appointment_name})
	visit.insert()
	
	return visit
