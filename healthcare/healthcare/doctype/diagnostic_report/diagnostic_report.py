# Copyright (c) 2023, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import get_workflow_name, get_workflow_state_field
from frappe.utils import now_datetime

from healthcare.healthcare.doctype.observation.observation import get_observation_details


class DiagnosticReport(Document):
	def validate(self):
		self.set_reference_details()
		self.set_age()
		self.set_title()
		self.derive_fhir_status()
		# set_diagnostic_status(self)

	def before_insert(self):
		if self.ref_doctype == "Sales Invoice" and self.docname:
			self.practitioner = frappe.db.get_value(self.ref_doctype, self.docname, "ref_practitioner")
		if not self.category:
			self.infer_category()

	def infer_category(self):
		"""Auto-set category based on the source reference type."""
		if self.radiology_report:
			self.category = "RAD"
		elif self.ref_doctype == "Sales Invoice":
			self.category = "LAB"
		elif self.ref_doctype == "Patient Encounter":
			self.category = "LAB"

	def set_age(self):
		if not self.age and self.patient:
			patient_doc = frappe.get_doc("Patient", self.patient)
			if patient_doc.dob:
				self.age = patient_doc.calculate_age(self.reference_posting_date).get("age_in_string")

	def set_title(self):
		category_label = {
			"LAB": "Lab",
			"RAD": "Radiology",
			"PATH": "Pathology",
			"CARD": "Cardiology",
		}.get(self.category, "")
		prefix = f"{category_label} - " if category_label else ""
		self.title = f"{prefix}{self.patient_name} - {self.age or ''} {self.gender}"

	def set_reference_details(self):
		if self.ref_doctype == "Sales Invoice" and self.docname:
			self.reference_posting_date = frappe.db.get_value("Sales Invoice", self.docname, "posting_date")

	def derive_fhir_status(self):
		"""Map category-specific status to FHIR DiagnosticReport.status.

		FHIR R4 DiagnosticReport status value set:
		  registered | partial | preliminary | final | amended |
		  corrected | appended | cancelled | entered-in-error
		"""
		if self.category == "RAD" and self.radiology_report:
			rad_status = frappe.db.get_value(
				"Radiology Report", self.radiology_report, "report_status"
			) if not self.flags.rad_status else self.flags.rad_status
			rad_to_fhir = {
				"Draft": "Partial",
				"Preliminary": "Preliminary",
				"Final": "Final",
				"Amended": "Amended",
				"Cancelled": "Cancelled",
			}
			self.fhir_status = rad_to_fhir.get(rad_status, "Registered")
		else:
			# Lab / generic path — map the existing status field
			lab_to_fhir = {
				"Open": "Registered",
				"Pending Review": "Preliminary",
				"Partially Approved": "Partial",
				"Approved": "Final",
				"Rejected": "Cancelled",
			}
			self.fhir_status = lab_to_fhir.get(self.status, "Registered")

		if self.fhir_status in ("Final", "Amended") and not self.issued:
			self.issued = now_datetime()

	@property
	def sales_invoice_status(self):
		if self.ref_doctype and self.docname:
			return frappe.db.get_value(self.ref_doctype, self.docname, "status")
		return None

	def sync_from_radiology_report(self, rad_report=None):
		"""Pull data from the linked Radiology Report into FHIR fields.

		Called when a Radiology Report creates or updates its Diagnostic Report.
		"""
		if not rad_report and self.radiology_report:
			rad_report = frappe.get_doc("Radiology Report", self.radiology_report)
		if not rad_report:
			return

		self.category = "RAD"
		self.patient = rad_report.patient
		self.patient_name = rad_report.patient_name
		self.practitioner = rad_report.reporting_radiologist
		self.practitioner_name = rad_report.reporting_radiologist_name
		self.company = frappe.db.get_value("Healthcare Settings", None, "default_medical_code_standard") or frappe.defaults.get_defaults().get("company")
		self.radiology_report = rad_report.name
		self.imaging_service_request = rad_report.imaging_service_request
		self.accession_number = rad_report.accession_number
		self.modality = rad_report.modality
		self.body_part = rad_report.body_part
		self.laterality = rad_report.laterality
		self.study_instance_uid = rad_report.study_instance_uid
		self.report_impression = rad_report.impression
		self.conclusion = rad_report.conclusion or rad_report.impression
		self.effective_datetime = rad_report.study_datetime or rad_report.report_datetime
		if rad_report.report_datetime:
			rd = rad_report.report_datetime
			if isinstance(rd, str):
				from frappe.utils import get_datetime
				rd = get_datetime(rd)
			self.reference_posting_date = rd.date()
		else:
			self.reference_posting_date = None

		# Derive FHIR code from radiology procedure template
		if rad_report.radiology_procedure_template:
			template_doc = frappe.get_cached_doc(
				"Radiology Procedure Template", rad_report.radiology_procedure_template
			)
			# Use first codification entry if available
			if template_doc.codification_table and len(template_doc.codification_table) > 0:
				code_row = template_doc.codification_table[0]
				self.fhir_code = code_row.code
				self.fhir_code_display = code_row.description or template_doc.name
			else:
				self.fhir_code_display = template_doc.name

		# Map radiology report status
		rad_to_status = {
			"Draft": "Open",
			"Preliminary": "Pending Review",
			"Final": "Approved",
			"Amended": "Approved",
			"Cancelled": "Rejected",
		}
		self.status = rad_to_status.get(rad_report.report_status, "Open")
		self.flags.rad_status = rad_report.report_status
		self.derive_fhir_status()


def diagnostic_report_print(diagnostic_report):
	return get_observation_details(diagnostic_report)


def validate_observations_has_result(doc):
	if doc.ref_doctype == "Sales Invoice":
		submittable = True
		observations = frappe.db.get_all(
			"Observation",
			{
				"sales_invoice": doc.docname,
				"docstatus": ["!=", 2],
				"has_component": False,
				"status": ["!=", "Cancelled"],
			},
			pluck="name",
		)
		for obs in observations:
			if not frappe.get_doc("Observation", obs).has_result():
				submittable = False
		return submittable


def set_diagnostic_status(doc):
	if doc.get("__islocal"):
		return
	observations = frappe.db.get_all(
		"Observation",
		{"sales_invoice": doc.docname, "docstatus": 0, "status": ["!=", "Approved"], "has_component": 0},
	)
	workflow_name = get_workflow_name("Diagnostic Report")
	workflow_state_field = get_workflow_state_field(workflow_name)
	if observations and len(observations) > 0:
		set_status = "Partially Approved"
	else:
		set_status = "Approved"
	doc.status = set_status
	doc.set(workflow_state_field, set_status)


@frappe.whitelist()
def set_observation_status(docname):
	doc = frappe.get_doc("Diagnostic Report", docname)
	if doc.ref_doctype == "Sales Invoice":
		observations = frappe.db.get_all(
			"Observation",
			{
				"sales_invoice": doc.docname,
				"docstatus": ["!=", 2],
				"has_component": False,
				"status": ["not in", ["Cancelled", "Approved", "Rejected"]],
			},
			pluck="name",
		)
		if observations:
			for obs in observations:
				if doc.status in ["Approved", "Rejected"]:
					observation_doc = frappe.get_doc("Observation", obs)
					if observation_doc.has_result():
						if doc.status == "Approved" and observation_doc.status not in [
							"Approved",
							"Rejected",
						]:
							observation_doc.status = doc.status
							observation_doc.save().submit()
						if doc.status == "Rejected" and observation_doc.status == "Approved":
							new_doc = frappe.copy_doc(observation_doc)
							new_doc.status = ""
							new_doc.insert()
							observation_doc.cancel()


def create_or_update_diagnostic_report(radiology_report):
	"""Create or update a Diagnostic Report from a Radiology Report.

	This is the SWF→RRR-WF FHIR bridge: when a Radiology Report reaches
	a significant status (Final, Amended, Preliminary), this function
	ensures a corresponding Diagnostic Report record exists and is
	synchronized.

	Args:
		radiology_report: A RadiologyReport document instance or name string.

	Returns:
		The name of the Diagnostic Report.
	"""
	if isinstance(radiology_report, str):
		radiology_report = frappe.get_doc("Radiology Report", radiology_report)

	# Look for existing linked Diagnostic Report
	existing = radiology_report.diagnostic_report
	if not existing:
		existing = frappe.db.get_value(
			"Diagnostic Report",
			{"radiology_report": radiology_report.name},
			"name",
		)

	if existing:
		dr = frappe.get_doc("Diagnostic Report", existing)
		dr.sync_from_radiology_report(radiology_report)
		dr.save(ignore_permissions=True)
	else:
		dr = frappe.new_doc("Diagnostic Report")
		dr.sync_from_radiology_report(radiology_report)
		dr.save(ignore_permissions=True)
		# Back-link the diagnostic report on the radiology report
		frappe.db.set_value(
			"Radiology Report",
			radiology_report.name,
			"diagnostic_report",
			dr.name,
			update_modified=False,
		)

	return dr.name


@frappe.whitelist()
def get_radiology_report_details(diagnostic_report_name):
	"""Return radiology report details for the Diagnostic Report form.

	Used by the client script to render radiology content inline.
	"""
	dr = frappe.get_doc("Diagnostic Report", diagnostic_report_name)
	if dr.category != "RAD" or not dr.radiology_report:
		return None

	rad = frappe.get_doc("Radiology Report", dr.radiology_report)
	findings = []
	for f in rad.findings:
		findings.append({
			"title": f.finding_title,
			"type": f.finding_type,
			"description": f.description,
			"body_site": f.body_site,
			"laterality": f.laterality,
			"significance": getattr(f, "significance", None),
			"status": f.status,
		})

	addenda = []
	for a in rad.addenda:
		addenda.append({
			"type": a.addendum_type,
			"datetime": str(a.addendum_datetime) if a.addendum_datetime else None,
			"author": a.addendum_by,
			"text": a.addendum_text,
			"reason": a.reason,
		})

	return {
		"report_name": rad.name,
		"report_status": rad.report_status,
		"report_datetime": str(rad.report_datetime) if rad.report_datetime else None,
		"signed_datetime": str(rad.signed_datetime) if rad.signed_datetime else None,
		"reporting_radiologist": rad.reporting_radiologist_name,
		"reviewing_radiologist": rad.reviewing_radiologist_name,
		"modality": rad.modality,
		"body_part": rad.body_part,
		"laterality": rad.laterality,
		"technique": rad.technique,
		"comparison": rad.comparison,
		"clinical_information": rad.clinical_information,
		"findings": findings,
		"impression": rad.impression,
		"conclusion": rad.conclusion,
		"recommendations": rad.recommendations,
		"addenda": addenda,
		"critical_result": rad.critical_result,
		"critical_result_communicated_to": rad.critical_result_communicated_to,
		"critical_result_communicated_at": str(rad.critical_result_communicated_at) if rad.critical_result_communicated_at else None,
		"report_format": rad.report_format,
	}
