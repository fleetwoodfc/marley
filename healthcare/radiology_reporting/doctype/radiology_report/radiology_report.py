# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

def _get_logger():
	return frappe.logger("radiology_report", with_more_info=False)


# ---------------------------------------------------------------------------
# MRRT section extraction helpers (T002)
# ---------------------------------------------------------------------------

# Section IDs that map directly to named Radiology Report text fields
_SECTION_FIELD_MAP = {
	"technique": "technique",
	"impression": "impression",
	"conclusion": "conclusion",
	"comparison": "comparison",
	"recommendations": "recommendations",
}

# Section IDs that carry no reportable content (structural / header only)
_SKIP_SECTIONS = {"report-header"}


def _extract_sections_from_mrrt(mrrt_html: str) -> dict:
	"""Parse MRRT HTML and return a dict of field values for report pre-population.

	Returns:
		{
			"technique": str,
			"impression": str,
			"conclusion": str,
			"comparison": str,
			"recommendations": str,
			"findings": [
				{"section_id": str, "title": str, "text": str, "sequence": int},
				...
			]
		}
	All values default to empty string / empty list when not found.
	On any parse error, logs a warning and returns an empty dict.
	"""
	try:
		from bs4 import BeautifulSoup
	except ImportError:
		_get_logger().warning("bs4 (BeautifulSoup4) not available — MRRT section extraction skipped")
		return {}

	result = {k: "" for k in _SECTION_FIELD_MAP}
	result["findings"] = []

	try:
		soup = BeautifulSoup(mrrt_html, "html.parser")
		sections = soup.find_all("section", attrs={"data-section-id": True})
		finding_seq = 1
		for section in sections:
			section_id = section.get("data-section-id", "").strip()
			if not section_id or section_id in _SKIP_SECTIONS:
				continue

			# Extract header text
			header_tag = section.find("header")
			title_text = header_tag.get_text(separator=" ", strip=True) if header_tag else section_id

			# Extract body text from <p> tags
			paragraphs = section.find_all("p")
			body_text = "\n".join(p.get_text(separator=" ", strip=True) for p in paragraphs).strip()

			if section_id in _SECTION_FIELD_MAP:
				result[_SECTION_FIELD_MAP[section_id]] = body_text
			else:
				result["findings"].append({
					"section_id": section_id,
					"title": title_text,
					"text": body_text,
					"sequence": finding_seq,
				})
				finding_seq += 1

	except Exception:
		_get_logger().warning("Failed to parse MRRT HTML for section extraction", exc_info=True)
		return {}

	return result


class RadiologyReport(Document):
	def before_insert(self):
		if not self.report_datetime:
			self.report_datetime = now_datetime()

	def validate(self):
		self.validate_status_transition()
		self.validate_signing()
		self.validate_amendment()

	def validate_status_transition(self):
		if self.is_new():
			return
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return
		old_status = old_doc.report_status
		if old_status == self.report_status:
			return

		# IHE RRR-WF / FHIR DiagnosticReport status transitions
		valid_transitions = {
			"Draft": ["Preliminary", "Final", "Cancelled"],
			"Preliminary": ["Final", "Cancelled"],
			"Final": ["Amended", "Cancelled"],
			"Amended": ["Amended", "Cancelled"],  # can amend again
			"Cancelled": [],  # terminal state
		}
		if self.report_status not in valid_transitions.get(old_status, []):
			frappe.throw(
				_("Cannot transition report from {0} to {1}").format(
					old_status, self.report_status
				)
			)

	def validate_signing(self):
		"""Ensure a finalized report has signing info."""
		if self.report_status == "Final" and not self.signed_by:
			self.signed_by = self.reporting_radiologist
			self.signed_datetime = now_datetime()

	def validate_amendment(self):
		"""Ensure amended reports have addenda."""
		if self.report_status == "Amended" and not self.amendment_datetime:
			self.amendment_datetime = now_datetime()

	def apply_template_version(self, version_name: str, pre_populate: bool = True):
		"""Attach a published template version to this report and denormalize the label.

		Call before insert when initializing from the template manager.
		The selected version must be Published at time of application.

		When pre_populate=True (default), also extracts MRRT sections and sets the
		corresponding text fields (technique, impression, conclusion, comparison,
		recommendations) and rebuilds the findings child table. Non-empty extracted
		values only — existing field content is not cleared unless findings are replaced.
		On extraction failure the template linkage fields are still set (non-blocking).
		"""
		version = frappe.get_doc("Radiology Report Template Version", version_name)
		if version.lifecycle_status != "Published":
			frappe.throw(
				_("Template version {0} is not Published (status: {1}). Only Published versions can be applied.").format(
					frappe.bold(version_name), frappe.bold(version.lifecycle_status)
				)
			)
		self.report_template = version.report_template
		self.report_template_version = version_name
		self.template_version_label = version.version_label

		if pre_populate and version.mrrt_html:
			sections = _extract_sections_from_mrrt(version.mrrt_html)
			if sections:
				# Set direct-mapped text fields (non-empty values only)
				for field in ("technique", "impression", "conclusion", "comparison", "recommendations"):
					value = sections.get(field, "")
					if value:
						setattr(self, field, value)
				# Rebuild findings child table
				self.set("findings", [])
				for row in sections.get("findings", []):
					self.append("findings", {
						"finding_title": row["title"],
						"description": row["text"],
						"sequence": row["sequence"],
						"status": "Normal",
					})
				_get_logger().debug("Applied template %s to %s with %d finding row(s)", version_name, self.name or "(new)", len(sections.get("findings", [])))

	def on_update(self):
		self.update_worklist_item()
		self.update_session_event()
		self.sync_diagnostic_report()

	def sync_diagnostic_report(self):
		"""Create or update the FHIR Diagnostic Report bridge record.

		This ensures every Radiology Report has a corresponding
		Diagnostic Report for unified listing and FHIR interoperability.
		"""
		from healthcare.healthcare.doctype.diagnostic_report.diagnostic_report import (
			create_or_update_diagnostic_report,
		)
		create_or_update_diagnostic_report(self)

	def update_worklist_item(self):
		"""Sync status back to the linked Reporting Worklist Item."""
		worklist_items = frappe.get_all(
			"Reporting Worklist Item",
			filters={"radiology_report": self.name},
			pluck="name",
		)
		status_map = {
			"Draft": "Draft Report",
			"Preliminary": "Preliminary",
			"Final": "Completed",
			"Amended": "Completed",
			"Cancelled": "Cancelled",
		}
		new_status = status_map.get(self.report_status)
		for wl in worklist_items:
			frappe.db.set_value("Reporting Worklist Item", wl, "status", new_status)
			if self.report_status in ("Final", "Amended"):
				frappe.db.set_value(
					"Reporting Worklist Item", wl, "completed_at", now_datetime()
				)

	def update_session_event(self):
		"""Log status changes in the reporting session."""
		if not self.reporting_session:
			return
		old_doc = self.get_doc_before_save()
		if not old_doc or old_doc.report_status == self.report_status:
			return
		session = frappe.get_doc("Reporting Session", self.reporting_session)
		event_type = "Report Status Changed"
		if self.report_status == "Final":
			event_type = "Report Signed"
		elif self.report_status == "Amended":
			event_type = "Report Amended"
		session.add_event(
			event_type,
			report_context=self.name,
			patient=self.patient,
			previous_status=old_doc.report_status,
			new_status=self.report_status,
		)
		session.update_statistics()

	@frappe.whitelist()
	def sign_report(self):
		"""Electronically sign and finalize the report."""
		if self.report_status not in ("Draft", "Preliminary"):
			frappe.throw(_("Only Draft or Preliminary reports can be signed/finalized"))
		self.report_status = "Final"
		self.signed_by = self.reporting_radiologist
		self.signed_datetime = now_datetime()
		self.save()
		return self

	@frappe.whitelist()
	def add_addendum(self, addendum_text, reason=None, addendum_type="Addendum"):
		"""Add an addendum and set status to Amended."""
		self.append("addenda", {
			"addendum_type": addendum_type,
			"addendum_datetime": now_datetime(),
			"addendum_by": frappe.db.get_value(
				"Healthcare Practitioner",
				{"user_id": frappe.session.user},
				"name",
			),
			"addendum_text": addendum_text,
			"reason": reason,
		})
		if self.report_status == "Final":
			self.report_status = "Amended"
			self.amendment_datetime = now_datetime()
		self.save()
		return self
