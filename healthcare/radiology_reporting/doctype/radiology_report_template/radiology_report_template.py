import frappe
from frappe import _
from frappe.model.document import Document


class RadiologyReportTemplate(Document):
	def validate(self):
		self._validate_template_code()

	def _validate_template_code(self):
		if not self.template_code:
			return
		existing = frappe.db.get_value(
			"Radiology Report Template",
			{"template_code": self.template_code, "name": ("!=", self.name)},
			"name",
		)
		if existing:
			frappe.throw(
				_("Template Code {0} is already used by {1}.").format(
					frappe.bold(self.template_code), frappe.bold(existing)
				),
				title=_("Duplicate Template Code"),
			)
