# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""Scheduled task wrappers for terminology sync."""

import frappe


def sync_ciel_daily():
	"""
	Daily scheduler hook: import the latest CIEL version if it has not yet
	been imported.  Does nothing when auto-sync is disabled in Healthcare
	Settings (ciel_auto_sync_enabled flag).

	Promotion to default is intentionally NOT performed automatically -
	an admin should review and promote explicitly via the UI or CLI.
	"""
	try:
		enabled = frappe.db.get_single_value("Healthcare Settings", "ciel_auto_sync_enabled")
	except Exception:
		enabled = False

	if not enabled:
		return

	from healthcare.terminology.importer import CIELImporter

	try:
		summary = CIELImporter().import_version(version_tag="latest", make_default=False)
		if not summary.get("skipped"):
			frappe.logger().info(
				f"Daily CIEL sync complete: version={summary.get('version_tag')} "
				f"concepts={summary.get('concepts_imported')}"
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Daily CIEL sync failed")
