# Copyright (c) 2026, Healthcare Dev and contributors
# SPDX-License-Identifier: MIT
"""
Migration patch: load IHE RRR-WF §40.4.1.2 standard codesets into UPS DICOM Code.

This patch ensures the fixture data is present even if the standard
`bench migrate` fixture-sync step ran before the doctype table was created
(a race condition on the very first install).  It is idempotent — existing
records are updated, missing records are inserted.
"""

import frappe


def execute():
	from frappe.modules.import_file import import_file_by_path

	fixture_path = frappe.get_app_path(
                "healthcare",
                "healthcare",
		"fixtures",
		"ups_dicom_code.json",
	)

	import_file_by_path(fixture_path, force=True, data_import=True, reset_permissions=True)
	frappe.db.commit()
