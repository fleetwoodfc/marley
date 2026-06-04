# Copyright (c) 2026, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ProcedureStepType(Document):
	"""
	Procedure Step Type: A reusable workflow step type definition for radiology procedures.
	
	Step types are categorized by workflow phase (Acquisition, Post Processing, Reporting)
	and can be assigned to Procedure Types (as Procedure Steps) to define standardized workflows.
	
	System-provided step types (is_system=1) cannot be deleted, only deactivated.
	"""

	def before_delete(self):
		"""Prevent deletion of system-provided procedure step types."""
		if self.is_system:
			frappe.throw(
				_("System-provided procedure step types cannot be deleted. You can deactivate them instead by unchecking 'Active'."),
				title=_("Cannot Delete System Step Type")
			)

	def validate(self):
		"""Validate procedure step data."""
		self.validate_step_name_unique()

	def validate_step_name_unique(self):
		"""Provide a clear error message for duplicate step type names."""
		if self.is_new():
			existing = frappe.db.exists("Procedure Step Type", {"step_name": self.step_name})
			if existing:
				frappe.throw(
					_("A procedure step type with name '{0}' already exists. Step type names must be unique.").format(self.step_name),
					title=_("Duplicate Step Type Name")
				)
