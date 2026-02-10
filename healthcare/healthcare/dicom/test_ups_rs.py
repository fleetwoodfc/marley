# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Tests for UPS-RS Client

Run with:
	bench run-tests --app healthcare --module healthcare.healthcare.dicom.test_ups_rs
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json

import frappe
from frappe.tests import IntegrationTestCase

from healthcare.healthcare.dicom.ups_rs import (
	UpsRSClient,
	Workitem,
	ProcedureStepState,
	DicomCode,
	CancellationRequest,
	Tag,
	UpsRSError,
)


class MockResponse:
	"""Mock HTTP response for testing."""
	
	def __init__(self, json_data=None, status_code=200, headers=None, text=""):
		self._json_data = json_data
		self.status_code = status_code
		self.headers = headers or {}
		self.text = text
		self.content = json.dumps(json_data).encode() if json_data else b""
	
	def json(self):
		if self._json_data is None:
			raise json.JSONDecodeError("No JSON", "", 0)
		return self._json_data


class TestDicomCode(unittest.TestCase):
	"""Test DicomCode parsing and serialization."""
	
	def test_from_string_basic(self):
		code = DicomCode.from_string("12345^Test Code^SCT")
		self.assertEqual(code.code_value, "12345")
		self.assertEqual(code.code_meaning, "Test Code")
		self.assertEqual(code.coding_scheme_designator, "SCT")
		self.assertIsNone(code.coding_scheme_version)
	
	def test_from_string_with_version(self):
		code = DicomCode.from_string("12345^Test Code^SCT^2021")
		self.assertEqual(code.code_value, "12345")
		self.assertEqual(code.code_meaning, "Test Code")
		self.assertEqual(code.coding_scheme_designator, "SCT")
		self.assertEqual(code.coding_scheme_version, "2021")
	
	def test_from_string_invalid(self):
		with self.assertRaises(ValueError):
			DicomCode.from_string("invalid")
	
	def test_to_dict(self):
		code = DicomCode(
			code_value="12345",
			code_meaning="Test Code",
			coding_scheme_designator="SCT"
		)
		result = code.to_dict()
		self.assertEqual(result["00080100"]["Value"], ["12345"])
		self.assertEqual(result["00080104"]["Value"], ["Test Code"])
		self.assertEqual(result["00080102"]["Value"], ["SCT"])


class TestWorkitem(unittest.TestCase):
	"""Test Workitem serialization and deserialization."""
	
	def test_to_dicom_json_basic(self):
		workitem = Workitem(
			uid="1.2.3.4.5",
			procedure_step_label="CT Chest",
			patient_id="PAT001",
			patient_name="Doe^John"
		)
		
		result = workitem.to_dicom_json()
		
		self.assertEqual(result[Tag.SOPInstanceUID]["Value"], ["1.2.3.4.5"])
		self.assertEqual(result[Tag.ProcedureStepLabel]["Value"], ["CT Chest"])
		self.assertEqual(result[Tag.PatientID]["Value"], ["PAT001"])
		self.assertEqual(result[Tag.PatientName]["Value"][0]["Alphabetic"], "Doe^John")
	
	def test_to_dicom_json_with_datetime(self):
		dt = datetime(2025, 1, 15, 10, 30, 0)
		workitem = Workitem(
			scheduled_start_datetime=dt
		)
		
		result = workitem.to_dicom_json()
		
		self.assertEqual(
			result[Tag.ScheduledProcedureStepStartDateTime]["Value"],
			["20250115103000"]
		)
	
	def test_from_dicom_json(self):
		data = {
			Tag.SOPInstanceUID: {"vr": "UI", "Value": ["1.2.3.4.5"]},
			Tag.ProcedureStepState: {"vr": "CS", "Value": ["IN PROGRESS"]},
			Tag.ProcedureStepLabel: {"vr": "LO", "Value": ["MRI Brain"]},
			Tag.PatientID: {"vr": "LO", "Value": ["PAT002"]},
			Tag.PatientName: {"vr": "PN", "Value": [{"Alphabetic": "Smith^Jane"}]},
		}
		
		workitem = Workitem.from_dicom_json(data)
		
		self.assertEqual(workitem.uid, "1.2.3.4.5")
		self.assertEqual(workitem.procedure_step_state, ProcedureStepState.IN_PROGRESS)
		self.assertEqual(workitem.procedure_step_label, "MRI Brain")
		self.assertEqual(workitem.patient_id, "PAT002")
		self.assertEqual(workitem.patient_name, "Smith^Jane")


class TestCancellationRequest(unittest.TestCase):
	"""Test CancellationRequest serialization."""
	
	def test_to_dicom_json(self):
		request = CancellationRequest(
			reason="Patient requested",
			contact_uri="mailto:doctor@hospital.com",
			contact_display_name="Dr. Smith"
		)
		
		result = request.to_dicom_json()
		
		self.assertEqual(result[Tag.ReasonForCancellation]["Value"], ["Patient requested"])
		self.assertEqual(result[Tag.ContactURI]["Value"], ["mailto:doctor@hospital.com"])
		self.assertEqual(result[Tag.ContactDisplayName]["Value"], ["Dr. Smith"])
	
	def test_to_dicom_json_with_code(self):
		request = CancellationRequest(
			reason_code=DicomCode("110513", "Equipment failure", "DCM")
		)
		
		result = request.to_dicom_json()
		
		self.assertIn(Tag.ProcedureStepDiscontinuationReasonCodeSequence, result)


class TestUpsRSClient(unittest.TestCase):
	"""Test UpsRSClient operations."""
	
	def setUp(self):
		self.client = UpsRSClient(
			base_url="http://localhost:8080/dcm4chee-arc/aets/TEST/rs",
			aet="TEST_AET"
		)
	
	def tearDown(self):
		self.client.close()
	
	def test_url_building(self):
		url = self.client._url("workitems")
		self.assertEqual(url, "http://localhost:8080/dcm4chee-arc/aets/TEST/rs/workitems")
	
	def test_url_building_with_leading_slash(self):
		url = self.client._url("/workitems")
		self.assertEqual(url, "http://localhost:8080/dcm4chee-arc/aets/TEST/rs/workitems")
	
	def test_generate_uid(self):
		uid = self.client._generate_uid()
		self.assertTrue(uid.startswith("2.25."))
		# Should be different each time
		uid2 = self.client._generate_uid()
		self.assertNotEqual(uid, uid2)
	
	@patch('requests.Session.post')
	def test_create_workitem(self, mock_post):
		mock_post.return_value = MockResponse(
			json_data=None,
			status_code=201,
			headers={"Location": "/workitems/1.2.3.4.5"}
		)
		
		workitem = Workitem(
			procedure_step_label="CT Chest",
			patient_id="PAT001"
		)
		
		uid = self.client.create_workitem(workitem, uid="1.2.3.4.5")
		
		self.assertEqual(uid, "1.2.3.4.5")
		mock_post.assert_called_once()
	
	@patch('requests.Session.get')
	def test_retrieve_workitem(self, mock_get):
		mock_get.return_value = MockResponse(
			json_data=[{
				Tag.SOPInstanceUID: {"vr": "UI", "Value": ["1.2.3.4.5"]},
				Tag.ProcedureStepState: {"vr": "CS", "Value": ["SCHEDULED"]},
				Tag.ProcedureStepLabel: {"vr": "LO", "Value": ["CT Chest"]},
			}],
			status_code=200
		)
		
		workitem = self.client.retrieve_workitem("1.2.3.4.5")
		
		self.assertEqual(workitem.uid, "1.2.3.4.5")
		self.assertEqual(workitem.procedure_step_state, ProcedureStepState.SCHEDULED)
		self.assertEqual(workitem.procedure_step_label, "CT Chest")
	
	@patch('requests.Session.get')
	def test_search_workitems(self, mock_get):
		mock_get.return_value = MockResponse(
			json_data=[
				{
					Tag.SOPInstanceUID: {"vr": "UI", "Value": ["1.2.3.4.5"]},
					Tag.ProcedureStepState: {"vr": "CS", "Value": ["SCHEDULED"]},
				},
				{
					Tag.SOPInstanceUID: {"vr": "UI", "Value": ["1.2.3.4.6"]},
					Tag.ProcedureStepState: {"vr": "CS", "Value": ["IN PROGRESS"]},
				},
			],
			status_code=200
		)
		
		workitems = self.client.search_workitems(
			filters={Tag.ProcedureStepState: "SCHEDULED"},
			limit=10
		)
		
		self.assertEqual(len(workitems), 2)
		self.assertEqual(workitems[0].uid, "1.2.3.4.5")
		self.assertEqual(workitems[1].uid, "1.2.3.4.6")
	
	@patch('requests.Session.put')
	def test_change_state(self, mock_put):
		mock_put.return_value = MockResponse(
			json_data=None,
			status_code=200
		)
		
		transaction_uid = self.client.change_state(
			"1.2.3.4.5",
			ProcedureStepState.IN_PROGRESS
		)
		
		# Should have generated a transaction UID
		self.assertTrue(transaction_uid.startswith("2.25."))
		mock_put.assert_called_once()
	
	@patch('requests.Session.put')
	def test_complete_workitem(self, mock_put):
		mock_put.return_value = MockResponse(status_code=200)
		
		self.client.complete_workitem("1.2.3.4.5", "2.25.12345")
		
		mock_put.assert_called_once()
		# Verify the state in the request
		call_kwargs = mock_put.call_args[1]
		data = call_kwargs['json']
		self.assertEqual(data[Tag.ProcedureStepState]["Value"], ["COMPLETED"])
	
	@patch('requests.Session.post')
	def test_subscribe_workitem(self, mock_post):
		mock_post.return_value = MockResponse(status_code=201)
		
		self.client.subscribe_workitem("1.2.3.4.5")
		
		mock_post.assert_called_once()
		call_url = mock_post.call_args[0][0]
		self.assertIn("subscribers/TEST_AET", call_url)
	
	@patch('requests.Session.post')
	def test_request_cancellation(self, mock_post):
		mock_post.return_value = MockResponse(status_code=202)
		
		request = CancellationRequest(reason="Patient no-show")
		self.client.request_cancellation("1.2.3.4.5", request)
		
		mock_post.assert_called_once()
		call_url = mock_post.call_args[0][0]
		self.assertIn("cancelrequest/TEST_AET", call_url)
	
	@patch('requests.Session.get')
	def test_error_handling(self, mock_get):
		mock_get.return_value = MockResponse(
			json_data={"error": "Not found"},
			status_code=404,
			text="Not found"
		)
		
		with self.assertRaises(UpsRSError) as context:
			self.client.retrieve_workitem("nonexistent")
		
		self.assertEqual(context.exception.status_code, 404)
	
	def test_websocket_url_http(self):
		url = self.client._get_websocket_url()
		self.assertTrue(url.startswith("ws://"))
		self.assertIn("subscribers/TEST_AET", url)
	
	def test_websocket_url_https(self):
		client = UpsRSClient(
			base_url="https://secure.server/dcm4chee-arc/aets/TEST/rs",
			aet="TEST_AET"
		)
		url = client._get_websocket_url()
		self.assertTrue(url.startswith("wss://"))
		client.close()


class TestUpsRSClientIntegration(IntegrationTestCase):
	"""
	Integration tests for UPS-RS Client with Frappe.
	
	These tests require a running DICOM server.
	Set DICOM_TEST_URL environment variable to run.
	"""
	
	@classmethod
	def setUpClass(cls):
		import os
		cls.test_url = os.environ.get("DICOM_TEST_URL")
		if not cls.test_url:
			raise unittest.SkipTest("DICOM_TEST_URL not set")
		
		cls.client = UpsRSClient(
			base_url=cls.test_url,
			aet="FRAPPE_TEST"
		)
	
	@classmethod
	def tearDownClass(cls):
		if hasattr(cls, 'client'):
			cls.client.close()
	
	def test_create_and_retrieve_workitem(self):
		"""Test creating and retrieving a workitem."""
		workitem = Workitem(
			procedure_step_label="Integration Test",
			patient_id="TEST001",
			patient_name="Test^Patient",
			scheduled_start_datetime=datetime.now()
		)
		
		uid = self.client.create_workitem(workitem)
		self.assertIsNotNone(uid)
		
		retrieved = self.client.retrieve_workitem(uid)
		self.assertEqual(retrieved.procedure_step_label, "Integration Test")
		self.assertEqual(retrieved.patient_id, "TEST001")
	
	def test_workitem_lifecycle(self):
		"""Test complete workitem lifecycle: create -> start -> complete."""
		workitem = Workitem(
			procedure_step_label="Lifecycle Test",
			patient_id="TEST002",
			scheduled_start_datetime=datetime.now()
		)
		
		# Create
		uid = self.client.create_workitem(workitem)
		
		# Start (IN PROGRESS)
		transaction_uid = self.client.start_workitem(uid)
		
		retrieved = self.client.retrieve_workitem(uid)
		self.assertEqual(retrieved.procedure_step_state, ProcedureStepState.IN_PROGRESS)
		
		# Complete
		self.client.complete_workitem(uid, transaction_uid)
		
		retrieved = self.client.retrieve_workitem(uid)
		self.assertEqual(retrieved.procedure_step_state, ProcedureStepState.COMPLETED)


if __name__ == "__main__":
	unittest.main()
