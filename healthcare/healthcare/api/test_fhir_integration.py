"""
Tests for healthcare.healthcare.api.fhir_integration

Covers all 23 codepaths identified in the eng review:
- _as_iso: None, valid, invalid
- _build_codings_from_codification_table: empty, missing fields, valid rows
- _get_doc_or_raise: found, not found
- _get_code_value: None, valid link
- _extract_observation_value: all 11 permitted_data_type values + None
- get_patient_for_fhir: FHIR R4 shape, gender lowercase, active mapping
- get_service_request_for_fhir: FHIR R4 shape, Code Value lookup, encounter mapping
- get_observation_for_fhir: FHIR R4 shape, all result types
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from healthcare.healthcare.api.fhir_integration import (
	_as_iso,
	_build_codings_from_codification_table,
	_extract_observation_value,
	_get_code_value,
	_get_doc_or_raise,
	get_observation_for_fhir,
	get_patient_for_fhir,
	get_service_request_for_fhir,
)


def _make_doc(**kwargs):
	"""Create a MagicMock that behaves like a Frappe document for field access."""
	doc = MagicMock()
	doc.get = lambda key, default=None: kwargs.get(key, default)
	for key, value in kwargs.items():
		setattr(doc, key, value)
	return doc


class TestAsIso(unittest.TestCase):
	def test_none_returns_none(self):
		self.assertIsNone(_as_iso(None))

	def test_empty_string_returns_none(self):
		self.assertIsNone(_as_iso(""))

	def test_valid_datetime_returns_iso(self):
		result = _as_iso("2026-06-20 10:00:00")
		self.assertIn("2026-06-20", result)

	def test_invalid_string_returns_str_fallback(self):
		result = _as_iso("not-a-date")
		self.assertIsInstance(result, str)
		# Must not raise; must return the input as string
		self.assertEqual(result, "not-a-date")


class TestBuildCodings(unittest.TestCase):
	def test_none_rows_returns_empty(self):
		self.assertEqual(_build_codings_from_codification_table(None), [])

	def test_empty_list_returns_empty(self):
		self.assertEqual(_build_codings_from_codification_table([]), [])

	def test_row_missing_system_is_skipped(self):
		rows = [{"system": None, "code": "ABC", "display": "Test"}]
		self.assertEqual(_build_codings_from_codification_table(rows), [])

	def test_row_missing_code_is_skipped(self):
		rows = [{"system": "http://snomed.info/sct", "code": None, "display": "Test"}]
		self.assertEqual(_build_codings_from_codification_table(rows), [])

	def test_valid_rows_returned(self):
		rows = [
			{"system": "http://snomed.info/sct", "code": "12345", "display": "Finding"},
			{"system": None, "code": "SKIP", "display": "Skipped"},
		]
		result = _build_codings_from_codification_table(rows)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["code"], "12345")


class TestGetDocOrRaise(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration.frappe")
	def test_existing_doc_returned(self, mock_frappe):
		doc = MagicMock()
		mock_frappe.get_doc.return_value = doc
		mock_frappe.DoesNotExistError = frappe.DoesNotExistError
		result = _get_doc_or_raise("Patient", "PAT-0001")
		self.assertEqual(result, doc)

	@patch("healthcare.healthcare.api.fhir_integration.frappe")
	def test_missing_doc_raises(self, mock_frappe):
		mock_frappe.get_doc.side_effect = frappe.DoesNotExistError
		mock_frappe.DoesNotExistError = frappe.DoesNotExistError
		mock_frappe.throw.side_effect = frappe.DoesNotExistError
		with self.assertRaises(frappe.DoesNotExistError):
			_get_doc_or_raise("Patient", "NONEXISTENT")


class TestGetCodeValue(unittest.TestCase):
	def test_none_returns_none(self):
		self.assertIsNone(_get_code_value(None))

	def test_empty_string_returns_none(self):
		self.assertIsNone(_get_code_value(""))

	@patch("healthcare.healthcare.api.fhir_integration.frappe")
	def test_linked_code_value_returned(self, mock_frappe):
		mock_frappe.get_value.return_value = "active"
		result = _get_code_value("SR-STATUS-001")
		self.assertEqual(result, "active")
		mock_frappe.get_value.assert_called_once_with("Code Value", "SR-STATUS-001", "code_value")

	@patch("healthcare.healthcare.api.fhir_integration.frappe")
	def test_missing_code_value_falls_back_to_link_name(self, mock_frappe):
		mock_frappe.get_value.return_value = None
		result = _get_code_value("SR-STATUS-001")
		self.assertEqual(result, "SR-STATUS-001")


class TestExtractObservationValue(unittest.TestCase):
	def _doc(self, data_type, **kwargs):
		kwargs["permitted_data_type"] = data_type
		return _make_doc(**kwargs)

	def test_boolean_yes(self):
		doc = self._doc("Boolean", result_boolean="Yes")
		result = _extract_observation_value(doc)
		self.assertEqual(result, {"valueBoolean": True})

	def test_boolean_no(self):
		doc = self._doc("Boolean", result_boolean="No")
		result = _extract_observation_value(doc)
		self.assertEqual(result, {"valueBoolean": False})

	def test_boolean_empty_string_returns_none(self):
		# result_boolean is a Select field; default is '' — must NOT dispatch to boolean
		doc = self._doc("Boolean", result_boolean="")
		result = _extract_observation_value(doc)
		self.assertIsNone(result)

	def test_boolean_none_returns_none(self):
		doc = self._doc("Boolean", result_boolean=None)
		result = _extract_observation_value(doc)
		self.assertIsNone(result)

	def test_text(self):
		doc = self._doc("Text", result_text="Clinical note text")
		result = _extract_observation_value(doc)
		self.assertEqual(result, {"valueString": "Clinical note text"})

	def test_text_empty_returns_none(self):
		doc = self._doc("Text", result_text="")
		result = _extract_observation_value(doc)
		self.assertIsNone(result)

	def test_select(self):
		doc = self._doc("Select", result_select="Positive")
		result = _extract_observation_value(doc)
		self.assertIn("valueCodeableConcept", result)
		self.assertEqual(result["valueCodeableConcept"]["text"], "Positive")

	def test_select_empty_returns_none(self):
		doc = self._doc("Select", result_select="")
		self.assertIsNone(_extract_observation_value(doc))

	def test_quantity_from_float(self):
		doc = self._doc("Quantity", result_float=5.4, result_data="5.4", uom="mg/dL")
		result = _extract_observation_value(doc)
		self.assertIn("valueQuantity", result)
		self.assertEqual(result["valueQuantity"]["value"], 5.4)
		self.assertEqual(result["valueQuantity"]["unit"], "mg/dL")

	def test_quantity_non_numeric_falls_back_to_string(self):
		doc = self._doc("Quantity", result_float=None, result_data="N/A", uom="")
		result = _extract_observation_value(doc)
		self.assertEqual(result, {"valueString": "N/A"})

	def test_numeric(self):
		doc = self._doc("Numeric", result_float=42.0, result_data="42", uom="")
		result = _extract_observation_value(doc)
		self.assertIn("valueQuantity", result)

	def test_range(self):
		doc = self._doc("Range", result_data="1.5-3.5")
		result = _extract_observation_value(doc)
		self.assertEqual(result, {"valueString": "1.5-3.5"})

	def test_ratio(self):
		doc = self._doc("Ratio", result_data="2:1")
		result = _extract_observation_value(doc)
		self.assertEqual(result, {"valueString": "2:1"})

	def test_time(self):
		doc = self._doc("Time", result_time="2026-06-20 10:30:00")
		result = _extract_observation_value(doc)
		self.assertIn("valueTime", result)
		self.assertIsNotNone(result["valueTime"])

	def test_datetime(self):
		doc = self._doc("DateTime", result_datetime="2026-06-20 10:30:00")
		result = _extract_observation_value(doc)
		self.assertIn("valueDateTime", result)

	def test_period(self):
		doc = self._doc(
			"Period",
			result_period_from="2026-06-20 08:00:00",
			result_period_to="2026-06-20 16:00:00",
		)
		result = _extract_observation_value(doc)
		self.assertIn("valuePeriod", result)
		self.assertIsNotNone(result["valuePeriod"]["start"])
		self.assertIsNotNone(result["valuePeriod"]["end"])

	def test_period_both_none_returns_none(self):
		doc = self._doc("Period", result_period_from=None, result_period_to=None)
		self.assertIsNone(_extract_observation_value(doc))

	def test_attach(self):
		doc = self._doc("Attach", result_attach="/files/result.pdf")
		result = _extract_observation_value(doc)
		self.assertEqual(result, {"valueAttachment": {"url": "/files/result.pdf"}})

	def test_unknown_data_type_returns_none(self):
		doc = self._doc("SomeUnknownType")
		self.assertIsNone(_extract_observation_value(doc))

	def test_no_permitted_data_type_returns_none(self):
		doc = _make_doc(result_text="ignored")
		self.assertIsNone(_extract_observation_value(doc))


class TestGetPatientForFhir(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration._get_doc_or_raise")
	def _get_patient(self, mock_get_doc, **patient_fields):
		defaults = {
			"name": "PAT-0001",
			"patient_name": "John Smith",
			"first_name": "John",
			"middle_name": "",
			"last_name": "Smith",
			"sex": "Male",
			"dob": "1990-01-15",
			"email": "john@example.com",
			"mobile": "0412000000",
			"phone": None,
			"status": "Active",
			"modified": "2026-06-20 10:00:00",
		}
		defaults.update(patient_fields)
		doc = _make_doc(**defaults)
		mock_get_doc.return_value = doc
		return get_patient_for_fhir("PAT-0001")

	def test_resource_type(self):
		result = self._get_patient()
		self.assertEqual(result["resourceType"], "Patient")

	def test_id_is_doc_name(self):
		result = self._get_patient()
		self.assertEqual(result["id"], "PAT-0001")

	def test_gender_lowercased(self):
		result = self._get_patient(sex="Male")
		self.assertEqual(result["gender"], "male")

	def test_gender_female_lowercased(self):
		result = self._get_patient(sex="Female")
		self.assertEqual(result["gender"], "female")

	def test_gender_none_becomes_unknown(self):
		result = self._get_patient(sex=None)
		self.assertEqual(result["gender"], "unknown")

	def test_active_true_when_not_disabled(self):
		result = self._get_patient(status="Active")
		self.assertTrue(result["active"])

	def test_active_false_when_disabled(self):
		result = self._get_patient(status="Disabled")
		self.assertFalse(result["active"])

	def test_fhir_name_structure(self):
		result = self._get_patient(first_name="John", last_name="Smith")
		self.assertIn("name", result)
		self.assertEqual(result["name"][0]["family"], "Smith")
		self.assertIn("John", result["name"][0]["given"])

	def test_meta_last_updated_present(self):
		result = self._get_patient()
		self.assertIn("lastUpdated", result["meta"])


class TestGetServiceRequestForFhir(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration._get_code_value")
	@patch("healthcare.healthcare.api.fhir_integration._get_doc_or_raise")
	def _get_sr(self, mock_get_doc, mock_code_value, **sr_fields):
		mock_code_value.side_effect = lambda v: {"SR-STAT-001": "active", "SR-INT-001": "order"}.get(v, v)
		defaults = {
			"name": "SR-0001",
			"patient": "PAT-0001",
			"practitioner": "PRAC-0001",
			"referred_to_practitioner": None,
			"status": "SR-STAT-001",
			"intent": "SR-INT-001",
			"priority": None,
			"creation": "2026-06-20 09:00:00",
			"modified": "2026-06-20 10:00:00",
			"template_dn": "Chest X-Ray",
			"template_dt": "Lab Test Template",
			"source_doc": "Manual",
			"order_group": None,
		}
		defaults.update(sr_fields)
		doc = _make_doc(**defaults)
		doc.get = lambda key, default=None: defaults.get(key, default)
		mock_get_doc.return_value = doc
		return get_service_request_for_fhir("SR-0001")

	def test_resource_type(self):
		self.assertEqual(self._get_sr()["resourceType"], "ServiceRequest")

	def test_status_resolved_via_code_value(self):
		result = self._get_sr()
		self.assertEqual(result["status"], "active")

	def test_subject_reference_format(self):
		result = self._get_sr()
		self.assertEqual(result["subject"]["reference"], "Patient/PAT-0001")

	def test_requester_reference_format(self):
		result = self._get_sr()
		self.assertEqual(result["requester"]["reference"], "Practitioner/PRAC-0001")

	def test_encounter_set_when_patient_encounter(self):
		result = self._get_sr(source_doc="Patient Encounter", order_group="ENC-0001")
		self.assertIn("encounter", result)
		self.assertEqual(result["encounter"]["reference"], "Encounter/ENC-0001")

	def test_encounter_absent_for_other_source(self):
		result = self._get_sr(source_doc="Manual", order_group=None)
		self.assertNotIn("encounter", result)

	def test_identifier_has_accession_number(self):
		result = self._get_sr()
		self.assertTrue(any("ACSN" in str(i) for i in result.get("identifier", [])))

	def test_display_alias_present(self):
		# Backwards compatibility alias kept for existing consumers
		result = self._get_sr()
		self.assertIn("display", result)
		self.assertEqual(result["display"], "Chest X-Ray")


class TestGetObservationForFhir(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration._get_code_value")
	@patch("healthcare.healthcare.api.fhir_integration._get_doc_or_raise")
	def _get_obs(self, mock_get_doc, mock_code_value, **obs_fields):
		mock_code_value.return_value = "final"
		defaults = {
			"name": "OBS-0001",
			"patient": "PAT-0001",
			"service_request": "SR-0001",
			"healthcare_practitioner": "PRAC-0001",
			"specimen": None,
			"status": "OBS-STAT-001",
			"posting_datetime": "2026-06-20 10:00:00",
			"time_of_result": "2026-06-20 10:30:00",
			"permitted_data_type": "Quantity",
			"observation_template": "Glucose",
			"parent_observation": None,
			"note": None,
			"modified": "2026-06-20 10:30:00",
			"result_float": 5.4,
			"result_data": "5.4",
			"uom": "mmol/L",
		}
		defaults.update(obs_fields)
		doc = _make_doc(**defaults)
		doc.get = lambda key, default=None: defaults.get(key, default)
		mock_get_doc.return_value = doc
		return get_observation_for_fhir("OBS-0001")

	def test_resource_type(self):
		self.assertEqual(self._get_obs()["resourceType"], "Observation")

	def test_subject_reference(self):
		self.assertEqual(self._get_obs()["subject"]["reference"], "Patient/PAT-0001")

	def test_based_on_reference(self):
		result = self._get_obs()
		self.assertEqual(result["basedOn"][0]["reference"], "ServiceRequest/SR-0001")

	def test_quantity_result_type(self):
		result = self._get_obs(permitted_data_type="Quantity", result_float=5.4, uom="mmol/L")
		self.assertIn("valueQuantity", result)
		self.assertEqual(result["valueQuantity"]["value"], 5.4)

	def test_no_result_produces_no_value_key(self):
		result = self._get_obs(
			permitted_data_type="Text", result_text="", result_float=None, result_data=None
		)
		self.assertNotIn("valueString", result)
		self.assertNotIn("valueQuantity", result)

	def test_note_included_when_present(self):
		result = self._get_obs(note="Follow up required")
		self.assertEqual(result["note"][0]["text"], "Follow up required")

	def test_note_absent_when_empty(self):
		result = self._get_obs(note=None)
		self.assertNotIn("note", result)

	def test_performer_included(self):
		result = self._get_obs(healthcare_practitioner="PRAC-0001")
		self.assertEqual(result["performer"][0]["reference"], "Practitioner/PRAC-0001")

	def test_performer_absent_when_none(self):
		result = self._get_obs(healthcare_practitioner=None)
		self.assertNotIn("performer", result)


# ── Coverage gap tests added after Step 7 audit ─────────────────────────────


class TestGetImagingStudyByServiceRequest(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration._get_doc_or_raise")
	def test_sr_not_found_raises(self, mock_get_doc):
		mock_get_doc.side_effect = frappe.DoesNotExistError
		from healthcare.healthcare.api.fhir_integration import get_imaging_study_by_service_request

		with self.assertRaises(frappe.DoesNotExistError):
			get_imaging_study_by_service_request("SR-NONE")

	@patch("healthcare.healthcare.api.fhir_integration.frappe")
	def test_no_attachment_raises(self, mock_frappe):
		mock_frappe.DoesNotExistError = frappe.DoesNotExistError
		mock_frappe.get_doc.return_value = MagicMock()
		mock_frappe.get_all.return_value = []
		mock_frappe.throw.side_effect = frappe.DoesNotExistError
		from healthcare.healthcare.api.fhir_integration import get_imaging_study_by_service_request

		with self.assertRaises(frappe.DoesNotExistError):
			get_imaging_study_by_service_request("SR-0001")

	@patch("healthcare.healthcare.api.fhir_integration.frappe")
	def test_valid_attachment_returns_parsed_json(self, mock_frappe):
		mock_frappe.DoesNotExistError = frappe.DoesNotExistError
		file_mock = MagicMock()
		file_mock.get_content.return_value = '{"resourceType":"ImagingStudy","id":"IMG-001"}'
		attachment_row = MagicMock()
		attachment_row.file_url = "/files/imaging_study.json"
		mock_frappe.get_doc.side_effect = [MagicMock(), file_mock]
		mock_frappe.get_all.return_value = [attachment_row]
		from healthcare.healthcare.api.fhir_integration import get_imaging_study_by_service_request

		result = get_imaging_study_by_service_request("SR-0001")
		self.assertEqual(result["resourceType"], "ImagingStudy")

	@patch("healthcare.healthcare.api.fhir_integration.frappe")
	def test_invalid_json_attachment_raises(self, mock_frappe):
		mock_frappe.DoesNotExistError = frappe.DoesNotExistError
		file_mock = MagicMock()
		file_mock.get_content.return_value = "NOT JSON {{"
		attachment_row = MagicMock()
		attachment_row.file_url = "/files/imaging_study.json"
		mock_frappe.get_doc.side_effect = [MagicMock(), file_mock]
		mock_frappe.get_all.return_value = [attachment_row]
		mock_frappe.throw.side_effect = Exception("invalid json")
		from healthcare.healthcare.api.fhir_integration import get_imaging_study_by_service_request

		with self.assertRaises(Exception):
			get_imaging_study_by_service_request("SR-0001")


class TestServiceRequestEdgeCases(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration._get_code_value")
	@patch("healthcare.healthcare.api.fhir_integration._get_doc_or_raise")
	def _get_sr(self, mock_get_doc, mock_code_value, **sr_fields):
		mock_code_value.return_value = "active"
		defaults = {
			"name": "SR-0001",
			"patient": "PAT-0001",
			"practitioner": None,
			"referred_to_practitioner": None,
			"status": "SR-STAT",
			"intent": "SR-INT",
			"priority": None,
			"creation": "2026-06-20 09:00:00",
			"modified": "2026-06-20 10:00:00",
			"template_dn": "Test",
			"template_dt": "Test",
			"source_doc": "Manual",
			"order_group": None,
		}
		defaults.update(sr_fields)
		doc = _make_doc(**defaults)
		doc.get = lambda key, default=None: defaults.get(key, default)
		mock_get_doc.return_value = doc
		return get_service_request_for_fhir("SR-0001")

	def test_requester_from_referred_to_practitioner(self):
		result = self._get_sr(practitioner=None, referred_to_practitioner="PRAC-REF")
		self.assertEqual(result["requester"]["reference"], "Practitioner/PRAC-REF")

	def test_requester_absent_when_no_practitioner(self):
		result = self._get_sr(practitioner=None, referred_to_practitioner=None)
		self.assertNotIn("requester", result)

	def test_encounter_absent_when_patient_encounter_but_no_order_group(self):
		result = self._get_sr(source_doc="Patient Encounter", order_group=None)
		self.assertNotIn("encounter", result)


class TestObservationEdgeCases(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration._get_code_value")
	@patch("healthcare.healthcare.api.fhir_integration._get_doc_or_raise")
	def _get_obs(self, mock_get_doc, mock_code_value, **obs_fields):
		mock_code_value.return_value = "final"
		defaults = {
			"name": "OBS-0001",
			"patient": "PAT-0001",
			"service_request": None,
			"healthcare_practitioner": None,
			"specimen": None,
			"status": "OBS-STAT",
			"posting_datetime": None,
			"time_of_result": None,
			"permitted_data_type": "Text",
			"observation_template": "Test",
			"parent_observation": None,
			"note": None,
			"modified": None,
			"result_text": "Normal",
		}
		defaults.update(obs_fields)
		doc = _make_doc(**defaults)
		doc.get = lambda key, default=None: defaults.get(key, default)
		mock_get_doc.return_value = doc
		return get_observation_for_fhir("OBS-0001")

	def test_based_on_absent_when_no_service_request(self):
		result = self._get_obs(service_request=None)
		self.assertNotIn("basedOn", result)

	def test_specimen_included(self):
		result = self._get_obs(specimen="SPEC-0001")
		self.assertEqual(result["specimen"]["reference"], "Specimen/SPEC-0001")

	def test_specimen_absent_when_none(self):
		result = self._get_obs(specimen=None)
		self.assertNotIn("specimen", result)

	def test_derived_from_included(self):
		result = self._get_obs(parent_observation="OBS-PARENT")
		self.assertEqual(result["derivedFrom"][0]["reference"], "Observation/OBS-PARENT")

	def test_derived_from_absent_when_none(self):
		result = self._get_obs(parent_observation=None)
		self.assertNotIn("derivedFrom", result)


class TestPatientEdgeCases(unittest.TestCase):
	@patch("healthcare.healthcare.api.fhir_integration._get_doc_or_raise")
	def _get_patient(self, mock_get_doc, **patient_fields):
		defaults = {
			"name": "PAT-0001",
			"patient_name": "Test Patient",
			"first_name": "Test",
			"middle_name": None,
			"last_name": "Patient",
			"sex": "Male",
			"dob": "1990-01-01",
			"email": None,
			"mobile": None,
			"phone": None,
			"status": "Active",
			"modified": None,
		}
		defaults.update(patient_fields)
		doc = _make_doc(**defaults)
		mock_get_doc.return_value = doc
		return get_patient_for_fhir("PAT-0001")

	def test_birth_date_present(self):
		result = self._get_patient(dob="1990-01-01")
		self.assertEqual(result["birthDate"], "1990-01-01")

	def test_birth_date_none_when_no_dob(self):
		result = self._get_patient(dob=None)
		self.assertIsNone(result["birthDate"])

	def test_telecom_includes_phone(self):
		result = self._get_patient(phone="0298000000", mobile=None, email=None)
		self.assertTrue(any(t["system"] == "phone" and t["use"] == "home" for t in result["telecom"]))

	def test_telecom_empty_when_no_contact(self):
		result = self._get_patient(phone=None, mobile=None, email=None)
		self.assertEqual(result["telecom"], [])

	def test_given_includes_middle_name(self):
		result = self._get_patient(first_name="John", middle_name="Michael")
		self.assertIn("Michael", result["name"][0]["given"])
