# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""
Unit tests for the CIEL importer service.

These tests use a mock OCL client so no network calls are made.
"""

from unittest.mock import MagicMock, patch

import frappe

from healthcare.terminology.importer import CIELImporter
from healthcare.tests.utils import HealthcareTestSuite


def _make_raw_concept(external_id="116128", retired=False):
	"""Return a minimal raw concept dict in the shape returned by OCLClient."""
	return {
		"id": external_id,
		"external_id": external_id,
		"concept_class": "Diagnosis",
		"datatype": "N/A",
		"retired": retired,
		"names": [
			{
				"name": "Malaria",
				"locale": "en",
				"name_type": "FULLY_SPECIFIED",
				"locale_preferred": True,
				"voided": False,
			},
			{
				"name": "Paludisme",
				"locale": "fr",
				"name_type": "FULLY_SPECIFIED",
				"locale_preferred": True,
				"voided": False,
			},
		],
		"mappings": [
			{
				"map_type": "SAME-AS",
				"to_source_url": "ICD-10-WHO",
				"to_concept_code": "B54",
				"to_concept_name": "Unspecified malaria",
			}
		],
	}


class TestCIELImporter(HealthcareTestSuite):
	def setUp(self):
		super().setUp()
		self._delete_test_versions()

	def tearDown(self):
		self._delete_test_versions()
		super().tearDown()

	def _delete_test_versions(self):
		for name in frappe.get_all("CIEL Terminology Version", pluck="name"):
			try:
				# Delete child concepts first
				for cname in frappe.get_all(
					"CIEL Concept", filters={"terminology_version": name}, pluck="name"
				):
					frappe.delete_doc("CIEL Concept", cname, ignore_permissions=True, force=True)
				frappe.delete_doc("CIEL Terminology Version", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()

	def _make_mock_client(self, version_tag="TEST-2024-01", concepts=None):
		if concepts is None:
			concepts = [_make_raw_concept()]
		client = MagicMock()
		client.org = "CIEL"
		client.source = "CIEL"
		client.get_latest_ciel_version.return_value = version_tag
		client.stream_concepts.return_value = iter(concepts)
		return client

	# ------------------------------------------------------------------
	# Tests
	# ------------------------------------------------------------------

	def test_import_creates_version_and_concept(self):
		client = self._make_mock_client(version_tag="TEST-2024-01")
		importer = CIELImporter(client=client)
		summary = importer.import_version(version_tag="TEST-2024-01")

		self.assertFalse(summary["skipped"])
		self.assertFalse(summary["dry_run"])
		self.assertEqual(summary["concepts_imported"], 1)
		self.assertEqual(summary["names_imported"], 2)
		self.assertEqual(summary["mappings_imported"], 1)
		self.assertEqual(summary["concepts_retired"], 0)
		self.assertEqual(summary["import_errors"], 0)

		version = frappe.db.get_value(
			"CIEL Terminology Version", {"version_tag": "TEST-2024-01"}, ["name", "status"], as_dict=True
		)
		self.assertIsNotNone(version)
		self.assertEqual(version.status, "ready")

		concept = frappe.db.get_value(
			"CIEL Concept",
			{"external_id": "116128", "terminology_version": version.name},
			"name",
		)
		self.assertIsNotNone(concept)

	def test_idempotency_skips_existing_ready_version(self):
		client = self._make_mock_client(version_tag="TEST-2024-02")
		importer = CIELImporter(client=client)

		# First import
		importer.import_version(version_tag="TEST-2024-02")
		# Second import without force should skip
		client.stream_concepts.reset_mock()
		summary2 = importer.import_version(version_tag="TEST-2024-02")

		self.assertTrue(summary2["skipped"])
		client.stream_concepts.assert_not_called()

	def test_force_flag_reimports(self):
		client = self._make_mock_client(version_tag="TEST-2024-03")
		importer = CIELImporter(client=client)

		importer.import_version(version_tag="TEST-2024-03")
		# Reset mock to track second call
		client.stream_concepts.return_value = iter([_make_raw_concept()])
		summary2 = importer.import_version(version_tag="TEST-2024-03", force=True)

		self.assertFalse(summary2["skipped"])
		client.stream_concepts.assert_called_once()

	def test_dry_run_makes_no_changes(self):
		client = self._make_mock_client(version_tag="TEST-2024-04")
		importer = CIELImporter(client=client)
		summary = importer.import_version(version_tag="TEST-2024-04", dry_run=True)

		self.assertTrue(summary["dry_run"])
		self.assertEqual(summary["concepts_imported"], 0)
		client.stream_concepts.assert_not_called()

		# No version doc should have been created
		exists = frappe.db.exists("CIEL Terminology Version", {"version_tag": "TEST-2024-04"})
		self.assertFalse(exists)

	def test_retired_concept_counted(self):
		client = self._make_mock_client(
			version_tag="TEST-2024-05",
			concepts=[_make_raw_concept(external_id="999999", retired=True)],
		)
		importer = CIELImporter(client=client)
		summary = importer.import_version(version_tag="TEST-2024-05")

		self.assertEqual(summary["concepts_retired"], 1)

	def test_latest_version_resolved(self):
		client = self._make_mock_client(version_tag="TEST-LATEST")
		importer = CIELImporter(client=client)
		summary = importer.import_version(version_tag="latest")

		client.get_latest_ciel_version.assert_called_once()
		self.assertEqual(summary["version_tag"], "TEST-LATEST")

	def test_make_default_promotes_version(self):
		client = self._make_mock_client(version_tag="TEST-2024-06")
		importer = CIELImporter(client=client)
		importer.import_version(version_tag="TEST-2024-06", make_default=True)

		is_default = frappe.db.get_value(
			"CIEL Terminology Version", {"version_tag": "TEST-2024-06"}, "is_default"
		)
		self.assertEqual(is_default, 1)

	def test_parse_concept_structure(self):
		raw = _make_raw_concept()
		parsed = CIELImporter._parse_concept(raw, "CIEL-VER-TEST")
		self.assertEqual(parsed["external_id"], "116128")
		self.assertEqual(parsed["concept_class"], "Diagnosis")
		self.assertEqual(len(parsed["names"]), 2)
		self.assertEqual(len(parsed["mappings"]), 1)
		self.assertFalse(parsed["retired"])

	def test_bad_concept_increments_error_count(self):
		bad_concept = {}  # missing required fields

		def _bad_parse(raw, version_name):
			raise ValueError("parse error")

		client = self._make_mock_client(version_tag="TEST-2024-07", concepts=[bad_concept])
		importer = CIELImporter(client=client)

		with patch.object(CIELImporter, "_parse_concept", side_effect=_bad_parse):
			summary = importer.import_version(version_tag="TEST-2024-07")

		self.assertEqual(summary["import_errors"], 1)
		self.assertEqual(summary["concepts_imported"], 0)
