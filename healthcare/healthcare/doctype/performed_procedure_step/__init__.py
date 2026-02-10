# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PerformedProcedureStep(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from healthcare.healthcare.doctype.output_information_item.output_information_item import OutputInformationItem
		from healthcare.healthcare.doctype.protocol_code_item.protocol_code_item import ProtocolCodeItem

		comments: DF.Text | None
		contrast_agent: DF.Data | None
		contrast_used: DF.Check
		discontinuation_code: DF.Link | None
		discontinuation_reason: DF.SmallText | None
		end_datetime: DF.Datetime | None
		naming_series: DF.Literal["PPS-.#####"]
		output_information: DF.Table[OutputInformationItem]
		patient: DF.Link
		performed_protocol_codes: DF.Table[ProtocolCodeItem]
		performing_operator: DF.Link
		performing_practitioner: DF.Link | None
		radiation_dose: DF.Float | None
		scheduled_procedure_step: DF.Link
		start_datetime: DF.Datetime
		status: DF.Literal["In Progress", "Completed", "Discontinued"]
	# end: auto-generated types

	pass
