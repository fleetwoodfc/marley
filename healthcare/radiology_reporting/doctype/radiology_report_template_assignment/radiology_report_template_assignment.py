import frappe
from frappe import _
from frappe.model.document import Document


class RadiologyReportTemplateAssignment(Document):
	def validate(self):
		self._validate_version_is_published()
		self._check_priority_conflicts()

	def _validate_version_is_published(self):
		if not self.template_version:
			return
		status = frappe.db.get_value(
			"Radiology Report Template Version", self.template_version, "lifecycle_status"
		)
		if status != "Published":
			frappe.throw(
				_("Assignment can only reference a Published version. Version {0} has status {1}.").format(
					frappe.bold(self.template_version), frappe.bold(status)
				),
				title=_("Invalid Version Status"),
			)

	def _check_priority_conflicts(self):
		if not self.active:
			return
		filters = {
			"report_template": self.report_template,
			"organization": self.organization or "",
			"language": self.language or "",
			"modality": self.modality or "",
			"body_part": self.body_part or "",
			"radiology_procedure_template": self.radiology_procedure_template or "",
			"priority": self.priority,
			"active": 1,
			"name": ("!=", self.name),
		}
		conflict = frappe.db.get_value("Radiology Report Template Assignment", filters, "name")
		if conflict:
			frappe.msgprint(
				_("Assignment {0} has the same scope and priority. Consider adjusting priority to avoid ambiguous resolution.").format(
					frappe.bold(conflict)
				),
				title=_("Priority Conflict Warning"),
				indicator="orange",
			)
