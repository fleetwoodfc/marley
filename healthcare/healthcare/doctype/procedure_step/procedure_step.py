# Copyright (c) 2026, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ProcedureStep(Document):
	"""
	Procedure Step: A child table row linking a Procedure Step Type to a Procedure Type.
	
	Each row represents a step in the workflow for a specific Procedure Type,
	referencing a reusable Procedure Step Type template with a sequence number
	to define the order of execution.
	"""
	pass
