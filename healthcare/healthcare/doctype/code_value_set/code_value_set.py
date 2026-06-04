# Copyright (c) 2023, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CodeValueSet(Document):
	def autoname(self):
		self.name = f"{self.value_set}-{self.code_system}"

	def on_update(self):
		self._sync_code_value_links()

	def _sync_code_value_links(self):
		"""Keep Code Value.value_set in sync with the members child table."""
		new_members = {row.code_value for row in self.get("members") if row.code_value}

		existing = set(
			frappe.get_all("Code Value", filters={"value_set": self.name}, pluck="name")
		)

		# Assign this set on newly added members
		for cv_name in new_members - existing:
			frappe.db.set_value("Code Value", cv_name, "value_set", self.name)

		# Clear the set link on removed members
		for cv_name in existing - new_members:
			frappe.db.set_value("Code Value", cv_name, "value_set", None)
