# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CIELTerminologyVersion(Document):
	def validate(self):
		if self.is_default:
			self._ensure_single_default()

	def _ensure_single_default(self):
		"""Ensure only one version is marked as default at a time."""
		frappe.db.set_value(
			"CIEL Terminology Version",
			{"is_default": 1, "name": ("!=", self.name)},
			"is_default",
			0,
		)

	def promote_to_default(self):
		"""Promote this version to be the default terminology version."""
		if self.status != "ready":
			frappe.throw(_("Only versions with status 'ready' can be promoted to default."))
		self.is_default = 1
		self._ensure_single_default()
		self.save()
		frappe.msgprint(_("Version {0} is now the default CIEL terminology.").format(self.version_tag))

	@staticmethod
	def get_default_version():
		"""Return the current default CIEL Terminology Version document, or None."""
		name = frappe.db.get_value("CIEL Terminology Version", {"is_default": 1, "status": "ready"}, "name")
		if name:
			return frappe.get_doc("CIEL Terminology Version", name)
		return None
