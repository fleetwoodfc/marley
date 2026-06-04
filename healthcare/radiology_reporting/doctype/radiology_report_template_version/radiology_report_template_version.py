import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Valid state transitions for the version lifecycle
_VALID_TRANSITIONS = {
	"Draft": {"Review Ready"},
	"Review Ready": {"Draft", "Approved"},
	"Approved": {"Published", "Retired"},
	"Published": {"Superseded", "Retired"},
	"Superseded": set(),
	"Retired": set(),
}

# Statuses that cannot be published without passing validation
_REQUIRES_PASSED_VALIDATION = {"Approved", "Published"}


class RadiologyReportTemplateVersion(Document):
	def before_save(self):
		self._compute_checksum()

	def validate(self):
		self._validate_lifecycle_transition()
		self._validate_validation_gate()

	def _compute_checksum(self):
		content = (self.mrrt_html or "").strip()
		self.checksum = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else ""

	def _validate_lifecycle_transition(self):
		if not self.is_new():
			previous = self.get_doc_before_save()
			if previous and previous.lifecycle_status != self.lifecycle_status:
				from_status = previous.lifecycle_status
				to_status = self.lifecycle_status
				allowed = _VALID_TRANSITIONS.get(from_status, set())
				if to_status not in allowed:
					frappe.throw(
						_("Cannot transition version lifecycle from {0} to {1}.").format(
							frappe.bold(from_status), frappe.bold(to_status)
						),
						title=_("Invalid Lifecycle Transition"),
					)

	def _validate_validation_gate(self):
		if self.lifecycle_status in _REQUIRES_PASSED_VALIDATION:
			if self.validation_status not in ("Passed", "Warnings"):
				frappe.throw(
					_("Validation must pass (or have only warnings) before moving to {0}. Current validation status: {1}.").format(
						frappe.bold(self.lifecycle_status), frappe.bold(self.validation_status)
					),
					title=_("Validation Required"),
				)

	def append_governance_event(self, event_type, from_status, to_status, notes=""):
		self.append(
			"governance_events",
			{
				"event_type": event_type,
				"performed_by": frappe.session.user,
				"performed_at": now_datetime(),
				"from_status": from_status,
				"to_status": to_status,
				"notes": notes,
			},
		)
