# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, time_diff_in_seconds


class ReportingSession(Document):
	def before_insert(self):
		if not self.session_id:
			self.session_id = frappe.generate_hash(length=16)
		if not self.started_at:
			self.started_at = now_datetime()

	def validate(self):
		self.calculate_duration()
		self.validate_status_transition()

	def calculate_duration(self):
		if self.started_at and self.ended_at:
			diff = time_diff_in_seconds(self.ended_at, self.started_at)
			self.duration_minutes = max(0, int(diff / 60))

	def validate_status_transition(self):
		if self.is_new():
			return
		old_status = self.get_doc_before_save()
		if not old_status:
			return
		old_status = old_status.status
		valid_transitions = {
			"Active": ["Suspended", "Closed"],
			"Suspended": ["Active", "Closed"],
			"Closed": [],  # terminal state
		}
		if self.status != old_status and self.status not in valid_transitions.get(old_status, []):
			frappe.throw(
				_("Cannot transition session from {0} to {1}").format(old_status, self.status)
			)

	def close_session(self):
		"""Close the session and record the end time."""
		self.status = "Closed"
		self.ended_at = now_datetime()
		self.add_event("Session Closed")
		self.save()

	def suspend_session(self):
		"""Suspend the session (IHE IRA suspend/resume)."""
		self.status = "Suspended"
		self.add_event("Session Suspended")
		self.save()

	def resume_session(self):
		"""Resume a suspended session."""
		self.status = "Active"
		self.add_event("Session Resumed")
		self.save()

	def open_report_context(self, radiology_report, patient=None, study=None):
		"""Open a report context in this session (IHE IRA DiagnosticReport-open)."""
		self.current_report_context = radiology_report
		self.current_patient = patient
		self.current_study = study
		self.add_event(
			"Context Opened",
			report_context=radiology_report,
			patient=patient,
			study_reference=study,
		)
		self.save()

	def close_report_context(self):
		"""Close the current report context (IHE IRA DiagnosticReport-close)."""
		self.add_event(
			"Context Closed",
			report_context=self.current_report_context,
			patient=self.current_patient,
			study_reference=self.current_study,
		)
		self.current_report_context = None
		self.current_patient = None
		self.current_study = None
		self.save()

	def add_event(self, event_type, **kwargs):
		"""Add an audit event to the session event log."""
		self.append("events", {
			"event_type": event_type,
			"event_timestamp": now_datetime(),
			"actor": kwargs.get("actor") or frappe.session.user,
			"report_context": kwargs.get("report_context"),
			"patient": kwargs.get("patient"),
			"study_reference": kwargs.get("study_reference"),
			"previous_status": kwargs.get("previous_status"),
			"new_status": kwargs.get("new_status"),
			"detail": kwargs.get("detail"),
		})

	def update_statistics(self):
		"""Recalculate session statistics from linked reports."""
		reports = frappe.get_all(
			"Radiology Report",
			filters={"reporting_session": self.name},
			fields=["report_status"],
		)
		self.reports_drafted = sum(1 for r in reports if r.report_status == "Draft")
		self.reports_finalized = sum(
			1 for r in reports if r.report_status in ("Final", "Amended")
		)
		self.studies_read = len(reports)

		worklist = frappe.get_all(
			"Reporting Worklist Item",
			filters={"reporting_session": self.name, "status": "Pending"},
		)
		self.studies_pending = len(worklist)
		self.save()
