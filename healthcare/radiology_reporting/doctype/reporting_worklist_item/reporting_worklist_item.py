# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class ReportingWorklistItem(Document):
	def before_insert(self):
		if not self.queued_at:
			self.queued_at = now_datetime()

	def validate(self):
		self.validate_status_transition()

	def validate_status_transition(self):
		if self.is_new():
			return
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		old_status = old_doc.status
		if old_status == self.status:
			return

		valid_transitions = {
			"Pending": ["In Progress", "Cancelled"],
			"In Progress": ["Draft Report", "Pending", "Cancelled"],
			"Draft Report": ["Preliminary", "In Progress", "Cancelled"],
			"Preliminary": ["Completed", "Cancelled"],
			"Completed": [],  # terminal — amendments go through report
			"Cancelled": ["Pending"],  # allow re-queue
		}
		if self.status not in valid_transitions.get(old_status, []):
			frappe.throw(
				_("Cannot transition worklist item from {0} to {1}").format(
					old_status, self.status
				)
			)

	def on_update(self):
		if self.status == "In Progress" and not self.started_at:
			self.started_at = now_datetime()
			self.db_set("started_at", self.started_at)

	@frappe.whitelist()
	def start_reading(self, reporting_session=None):
		"""Assign to radiologist and begin reading."""
		self.status = "In Progress"
		self.started_at = now_datetime()
		if reporting_session:
			self.reporting_session = reporting_session
		self.save()
		return self

	@frappe.whitelist()
	def create_report(self, template_version: str = ""):
		"""Create a new Radiology Report from this worklist item.

		When template_version is provided, the report is pre-populated from the
		corresponding Published MRRT template version before being saved. The
		operation is atomic: if template application fails the report is never
		inserted. An audit Comment is appended to the new report when a template
		is applied (FR-011).
		"""
		if self.radiology_report:
			frappe.throw(_("A report already exists for this worklist item"))

		report = frappe.new_doc("Radiology Report")
		report.patient = self.patient
		report.imaging_service_request = self.imaging_service_request
		report.radiology_procedure = self.radiology_procedure
		report.modality = self.modality
		report.body_part = self.body_part
		report.laterality = self.laterality
		report.study_instance_uid = self.study_instance_uid
		report.study_datetime = self.study_datetime
		report.number_of_series = self.number_of_series
		report.number_of_instances = self.number_of_instances
		report.referring_practitioner = self.referring_practitioner
		report.clinical_indication = self.clinical_indication
		report.report_priority = self.priority
		report.reporting_radiologist = self.assigned_radiologist
		report.reporting_session = self.reporting_session
		report.report_datetime = now_datetime()

		if template_version:
			# apply_template_version validates that the version is Published and
			# raises if not — no partial insert if this fails
			report.apply_template_version(template_version, pre_populate=True)

		report.insert()

		# FR-011: write a queryable audit record on the report document
		if template_version:
			frappe.get_doc({
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Radiology Report",
				"reference_name": report.name,
				"content": _(
					"Template applied: {0} — {1} ({2})"
				).format(
					report.report_template,
					report.template_version_label,
					report.report_template_version,
				),
			}).insert(ignore_permissions=True)

		self.radiology_report = report.name
		self.status = "Draft Report"
		self.save()

		return {
			"name": report.name,
			"report_status": report.report_status,
			"template_applied": bool(template_version),
			"report_template": report.report_template or None,
			"report_template_version": report.report_template_version or None,
			"template_version_label": report.template_version_label or None,
		}
