# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""Register the CIEL terminology Code System in Marley."""

import frappe
from frappe import _

from erpnext.setup.utils import insert_record


def execute():
	frappe.reload_doc("healthcare", "doctype", "code_system")

	records = [
		{
			"doctype": "Code System",
			"is_fhir_defined": 0,
			"uri": "http://openconceptlab.org/orgs/CIEL/sources/CIEL/",
			"code_system": _("CIEL"),
			"description": _(
				"Columbia International eHealth Laboratory (CIEL) concept dictionary, "
				"imported locally via OpenConceptLab. "
				"https://github.com/OpenConceptLab"
			),
			"oid": "2.16.840.1.113883.3.1937",
			"experimental": 0,
			"immutable": 0,
			"custom": 0,
		}
	]
	insert_record(records)
