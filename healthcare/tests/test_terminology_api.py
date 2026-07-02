# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""
Tests for the internal terminology API endpoints.
"""

import frappe

from healthcare.healthcare.api import terminology as api
from healthcare.tests.utils import HealthcareTestSuite


def _create_test_version(version_tag="TEST-API-2024", is_default=True):
	if frappe.db.exists("CIEL Terminology Version", {"version_tag": version_tag}):
		name = frappe.db.get_value("CIEL Terminology Version", {"version_tag": version_tag}, "name")
		return frappe.get_doc("CIEL Terminology Version", name)
	doc = frappe.new_doc("CIEL Terminology Version")
	doc.version_tag = version_tag
	doc.status = "ready"
	doc.is_default = 1 if is_default else 0
	doc.ocl_org = "CIEL"
	doc.ocl_source = "CIEL"
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


def _create_test_concept(version_name, external_id="116128"):
	if frappe.db.exists("CIEL Concept", {"external_id": external_id, "terminology_version": version_name}):
		name = frappe.db.get_value(
			"CIEL Concept",
			{"external_id": external_id, "terminology_version": version_name},
			"name",
		)
		return frappe.get_doc("CIEL Concept", name)

	doc = frappe.new_doc("CIEL Concept")
	doc.external_id = external_id
	doc.terminology_version = version_name
	doc.concept_class = "Diagnosis"
	doc.datatype = "N/A"
	doc.retired = 0
	doc.append(
		"names",
		{
			"name_type": "FULLY_SPECIFIED",
			"locale": "en",
			"name_text": "Malaria",
			"preferred": 1,
			"voided": 0,
		},
	)
	doc.append(
		"mappings",
		{
			"map_type": "SAME-AS",
			"target_system": "ICD-10-WHO",
			"target_code": "B54",
			"target_display": "Unspecified malaria",
		},
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


class TestTerminologyAPI(HealthcareTestSuite):
	def setUp(self):
		super().setUp()
		self.version_doc = _create_test_version()
		self.concept_doc = _create_test_concept(self.version_doc.name)

	def tearDown(self):
		# Clean up test data in reverse dependency order
		for cname in frappe.get_all(
			"CIEL Concept",
			filters={"terminology_version": self.version_doc.name},
			pluck="name",
		):
			try:
				frappe.delete_doc("CIEL Concept", cname, ignore_permissions=True, force=True)
			except Exception:
				pass
		try:
			frappe.delete_doc(
				"CIEL Terminology Version",
				self.version_doc.name,
				ignore_permissions=True,
				force=True,
			)
		except Exception:
			pass
		frappe.db.commit()
		super().tearDown()

	# ------------------------------------------------------------------
	# search_concepts
	# ------------------------------------------------------------------

	def test_search_concepts_returns_results(self):
		result = api.search_concepts(query="Malaria", locale="en")
		self.assertIn("version_tag", result)
		self.assertEqual(result["version_tag"], "TEST-API-2024")
		self.assertTrue(len(result["results"]) > 0)
		names = [r["name_text"] for r in result["results"]]
		self.assertIn("Malaria", names)

	def test_search_concepts_no_default_version(self):
		# Temporarily unset default
		self.version_doc.is_default = 0
		self.version_doc.save(ignore_permissions=True)
		frappe.db.commit()

		result = api.search_concepts(query="Malaria")
		self.assertIn("error", result)

		# Restore
		self.version_doc.is_default = 1
		self.version_doc.save(ignore_permissions=True)
		frappe.db.commit()

	# ------------------------------------------------------------------
	# get_concept
	# ------------------------------------------------------------------

	def test_get_concept_returns_correct_concept(self):
		result = api.get_concept(external_id="116128")
		self.assertIn("version_tag", result)
		self.assertIn("concept", result)
		self.assertEqual(result["concept"]["external_id"], "116128")

	def test_get_concept_not_found_raises(self):
		with self.assertRaises(frappe.DoesNotExistError):
			api.get_concept(external_id="DOES-NOT-EXIST-9999")

	# ------------------------------------------------------------------
	# validate_code
	# ------------------------------------------------------------------

	def test_validate_code_valid(self):
		result = api.validate_code(system="CIEL", code="116128")
		self.assertTrue(result["valid"])
		self.assertFalse(result["retired"])

	def test_validate_code_invalid(self):
		result = api.validate_code(system="CIEL", code="DOES-NOT-EXIST")
		self.assertFalse(result["valid"])

	def test_validate_code_unsupported_system(self):
		result = api.validate_code(system="SNOMED-CT", code="116128")
		self.assertFalse(result["valid"])
		self.assertIn("error", result)

	# ------------------------------------------------------------------
	# get_mappings
	# ------------------------------------------------------------------

	def test_get_mappings_returns_results(self):
		result = api.get_mappings(target_system="ICD-10-WHO", code="B54")
		self.assertIn("results", result)
		self.assertTrue(len(result["results"]) > 0)
		self.assertEqual(result["results"][0]["target_code"], "B54")

	def test_get_mappings_no_match(self):
		result = api.get_mappings(target_system="ICD-10-WHO", code="ZZZZZ")
		self.assertEqual(result["results"], [])

	# ------------------------------------------------------------------
	# FHIR stubs
	# ------------------------------------------------------------------

	def test_fhir_lookup_found(self):
		result = api.fhir_lookup(system="http://openconceptlab.org/orgs/CIEL/sources/CIEL/", code="116128")
		self.assertEqual(result["resourceType"], "Parameters")
		params = {p["name"]: p for p in result["parameter"]}
		self.assertEqual(params["name"]["valueString"], "CIEL")
		self.assertFalse(params["inactive"]["valueBoolean"])

	def test_fhir_lookup_not_found(self):
		result = api.fhir_lookup(
			system="http://openconceptlab.org/orgs/CIEL/sources/CIEL/",
			code="DOES-NOT-EXIST",
		)
		self.assertEqual(result["resourceType"], "OperationOutcome")

	def test_fhir_expand_returns_valueset(self):
		result = api.fhir_expand(filter="Malaria")
		self.assertEqual(result["resourceType"], "ValueSet")
		codes = [c["code"] for c in result["expansion"]["contains"]]
		self.assertIn("116128", codes)
