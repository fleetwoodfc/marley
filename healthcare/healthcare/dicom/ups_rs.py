# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
DICOM UPS-RS (Unified Procedure Step - RESTful Services) Client

Python equivalent of dcm4che20's UpsRS.java for use in Frappe Healthcare.

UPS-RS is part of DICOMweb standard for managing worklists and procedure steps:
- Create/Retrieve/Update/Search Workitems
- Change Workitem State (IN PROGRESS, COMPLETED, CANCELED)
- Subscribe to Workitem/Worklist events via WebSocket
- Request Cancellation of Workitems

References:
- DICOM PS3.18 (Web Services)
- IHE Radiology Technical Framework Supplement: UPS on FHIR
- https://github.com/dcm4che/dcm4che20
"""

import json
import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Union
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlencode, urlparse

import frappe
import requests
import websockets


# DICOM Tags for UPS
class Tag:
	"""Common DICOM tags used in UPS-RS."""
	# UPS Identifiers
	SOPInstanceUID = "00080018"
	SOPClassUID = "00080016"
	
	# Procedure Step
	ScheduledProcedureStepStartDateTime = "00404005"
	ScheduledProcedureStepModificationDateTime = "00404010"
	ProcedureStepState = "00741000"
	ProcedureStepProgress = "00741002"
	ProcedureStepProgressDescription = "00741004"
	TransactionUID = "00081195"
	
	# Workitem Information
	WorklistLabel = "00741202"
	ProcedureStepLabel = "00741204"
	ScheduledWorkitemCodeSequence = "00404018"
	ScheduledStationNameCodeSequence = "00404025"
	ScheduledStationClassCodeSequence = "00404026"
	ScheduledStationGeographicLocationCodeSequence = "00404027"
	ScheduledProcessingApplicationsCodeSequence = "00404034"
	ScheduledHumanPerformersSequence = "00404034"
	ScheduledProcedureStepPriority = "00741200"  # Required: ROUTINE, STAT, etc.
	InputReadinessState = "00404041"  # Required: INCOMPLETE, UNAVAILABLE, READY
	
	# Input/Output
	InputInformationSequence = "00404021"
	OutputInformationSequence = "00404033"
	
	# Patient/Study References
	PatientID = "00100020"
	PatientName = "00100010"
	StudyInstanceUID = "0020000D"
	AccessionNumber = "00080050"
	
	# Cancellation
	ReasonForCancellation = "00741238"
	ProcedureStepDiscontinuationReasonCodeSequence = "0074100E"
	ContactURI = "0074100A"
	ContactDisplayName = "0074100C"


class ProcedureStepState(Enum):
	"""UPS Procedure Step States per DICOM."""
	SCHEDULED = "SCHEDULED"
	IN_PROGRESS = "IN PROGRESS"
	COMPLETED = "COMPLETED"
	CANCELED = "CANCELED"


class UpsEvent(Enum):
	"""UPS Event types for WebSocket notifications."""
	STATE_REPORT = "StateReport"
	PROGRESS_REPORT = "ProgressReport"
	CANCEL_REQUEST = "CancelRequest"
	ASSIGNED = "Assigned"
	DELETE = "Delete"


@dataclass
class DicomCode:
	"""DICOM Coded Value (Code Sequence Item)."""
	code_value: str
	code_meaning: str
	coding_scheme_designator: str
	coding_scheme_version: Optional[str] = None
	
	def to_dict(self) -> Dict[str, Any]:
		"""Convert to DICOM JSON format."""
		item = {
			"00080100": {"vr": "SH", "Value": [self.code_value]},
			"00080102": {"vr": "SH", "Value": [self.coding_scheme_designator]},
			"00080104": {"vr": "LO", "Value": [self.code_meaning]},
		}
		if self.coding_scheme_version:
			item["00080103"] = {"vr": "SH", "Value": [self.coding_scheme_version]}
		return item
	
	@classmethod
	def from_string(cls, s: str) -> "DicomCode":
		"""Parse from format: code_value^code_meaning^coding_scheme."""
		parts = s.split("^")
		if len(parts) < 3:
			raise ValueError(f"Invalid code format: {s}. Expected: value^meaning^scheme")
		return cls(
			code_value=parts[0],
			code_meaning=parts[1],
			coding_scheme_designator=parts[2],
			coding_scheme_version=parts[3] if len(parts) > 3 else None
		)


@dataclass
class Workitem:
	"""UPS Workitem representation."""
	uid: Optional[str] = None
	procedure_step_state: ProcedureStepState = ProcedureStepState.SCHEDULED
	scheduled_start_datetime: Optional[datetime] = None
	worklist_label: Optional[str] = None
	procedure_step_label: Optional[str] = None
	patient_id: Optional[str] = None
	patient_name: Optional[str] = None
	study_instance_uid: Optional[str] = None
	accession_number: Optional[str] = None
	scheduled_workitem_code: Optional[DicomCode] = None
	scheduled_station_name: Optional[DicomCode] = None
	input_information: List[Dict] = field(default_factory=list)
	output_information: List[Dict] = field(default_factory=list)
	custom_attributes: Dict[str, Any] = field(default_factory=dict)
	# Required UPS fields
	priority: str = "MEDIUM"  # LOW, MEDIUM, HIGH
	input_readiness_state: str = "READY"  # INCOMPLETE, UNAVAILABLE, READY
	
	def to_dicom_json(self, include_uid: bool = False) -> Dict[str, Any]:
		"""Convert to DICOM JSON format for API requests.
		
		Args:
			include_uid: Whether to include SOP Instance UID in payload.
			            Set to False for create requests (UID goes in URL).
		"""
		data = {}
		
		# Only include UID if explicitly requested (not for create requests)
		if include_uid and self.uid:
			data[Tag.SOPInstanceUID] = {"vr": "UI", "Value": [self.uid]}
		
		# Required fields for UPS
		data[Tag.ScheduledProcedureStepPriority] = {"vr": "CS", "Value": [self.priority]}
		data[Tag.InputReadinessState] = {"vr": "CS", "Value": [self.input_readiness_state]}
		
		# MUST include ProcedureStepState - required by dcm4chee
		data[Tag.ProcedureStepState] = {"vr": "CS", "Value": [self.procedure_step_state.value]}
		
		if self.scheduled_start_datetime:
			dt_str = self.scheduled_start_datetime.strftime("%Y%m%d%H%M%S")
			data[Tag.ScheduledProcedureStepStartDateTime] = {"vr": "DT", "Value": [dt_str]}
		
		if self.worklist_label:
			data[Tag.WorklistLabel] = {"vr": "LO", "Value": [self.worklist_label]}
		
		if self.procedure_step_label:
			data[Tag.ProcedureStepLabel] = {"vr": "LO", "Value": [self.procedure_step_label]}
		
		if self.patient_id:
			data[Tag.PatientID] = {"vr": "LO", "Value": [self.patient_id]}
		
		if self.patient_name:
			data[Tag.PatientName] = {"vr": "PN", "Value": [{"Alphabetic": self.patient_name}]}
		
		if self.study_instance_uid:
			data[Tag.StudyInstanceUID] = {"vr": "UI", "Value": [self.study_instance_uid]}
		
		if self.accession_number:
			data[Tag.AccessionNumber] = {"vr": "SH", "Value": [self.accession_number]}
		
		if self.scheduled_workitem_code:
			data[Tag.ScheduledWorkitemCodeSequence] = {
				"vr": "SQ",
				"Value": [self.scheduled_workitem_code.to_dict()]
			}
		
		if self.scheduled_station_name:
			data[Tag.ScheduledStationNameCodeSequence] = {
				"vr": "SQ",
				"Value": [self.scheduled_station_name.to_dict()]
			}
		
		if self.input_information:
			data[Tag.InputInformationSequence] = {"vr": "SQ", "Value": self.input_information}
		
		if self.output_information:
			data[Tag.OutputInformationSequence] = {"vr": "SQ", "Value": self.output_information}
		
		# Add custom attributes
		data.update(self.custom_attributes)
		
		return data
	
	@classmethod
	def from_dicom_json(cls, data: Dict[str, Any]) -> "Workitem":
		"""Parse from DICOM JSON response."""
		def get_value(tag: str, default=None):
			if tag in data and "Value" in data[tag]:
				return data[tag]["Value"][0] if data[tag]["Value"] else default
			return default
		
		workitem = cls()
		workitem.uid = get_value(Tag.SOPInstanceUID)
		
		state_str = get_value(Tag.ProcedureStepState)
		if state_str:
			workitem.procedure_step_state = ProcedureStepState(state_str)
		
		dt_str = get_value(Tag.ScheduledProcedureStepStartDateTime)
		if dt_str:
			try:
				workitem.scheduled_start_datetime = datetime.strptime(dt_str[:14], "%Y%m%d%H%M%S")
			except ValueError:
				pass
		
		workitem.worklist_label = get_value(Tag.WorklistLabel)
		workitem.procedure_step_label = get_value(Tag.ProcedureStepLabel)
		workitem.patient_id = get_value(Tag.PatientID)
		workitem.study_instance_uid = get_value(Tag.StudyInstanceUID)
		workitem.accession_number = get_value(Tag.AccessionNumber)
		
		# Patient name handling
		pn = get_value(Tag.PatientName)
		if isinstance(pn, dict):
			workitem.patient_name = pn.get("Alphabetic", "")
		elif isinstance(pn, str):
			workitem.patient_name = pn
		
		return workitem


@dataclass
class CancellationRequest:
	"""UPS Cancellation Request."""
	reason: Optional[str] = None
	reason_code: Optional[DicomCode] = None
	contact_uri: Optional[str] = None
	contact_display_name: Optional[str] = None
	
	def to_dicom_json(self) -> Dict[str, Any]:
		"""Convert to DICOM JSON format."""
		data = {}
		
		if self.reason:
			data[Tag.ReasonForCancellation] = {"vr": "LT", "Value": [self.reason]}
		
		if self.reason_code:
			data[Tag.ProcedureStepDiscontinuationReasonCodeSequence] = {
				"vr": "SQ",
				"Value": [self.reason_code.to_dict()]
			}
		
		if self.contact_uri:
			data[Tag.ContactURI] = {"vr": "UR", "Value": [self.contact_uri]}
		
		if self.contact_display_name:
			data[Tag.ContactDisplayName] = {"vr": "LO", "Value": [self.contact_display_name]}
		
		return data


class UpsRSClient:
	"""
	DICOM UPS-RS (Unified Procedure Step - RESTful Services) Client.
	
	Implements DICOMweb UPS-RS operations for managing radiology worklists
	and procedure steps. Compatible with dcm4chee-arc and other DICOM servers.
	
	Usage:
		client = UpsRSClient(
			base_url="http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs",
			aet="MY_AET"
		)
		
		# Create workitem
		workitem = Workitem(
			procedure_step_label="CT Chest",
			patient_id="PAT001"
		)
		uid = client.create_workitem(workitem)
		
		# Change state to IN PROGRESS
		transaction_uid = client.change_state(uid, ProcedureStepState.IN_PROGRESS)
		
		# Complete the workitem
		client.complete_workitem(uid, transaction_uid)
		
		# Subscribe to worklist events
		async def on_event(event_type, data):
			print(f"Event: {event_type}, Data: {data}")
		
		await client.subscribe_websocket(on_event)
	"""
	
	# DICOM UPS SOP Class UIDs
	GLOBAL_SUBSCRIPTION_UID = "1.2.840.10008.5.1.4.34.5"
	FILTERED_SUBSCRIPTION_UID = "1.2.840.10008.5.1.4.34.5.1"
	
	# Media Types
	APPLICATION_DICOM_JSON = "application/dicom+json"
	APPLICATION_DICOM_XML = "application/dicom+xml"
	
	def __init__(
		self,
		base_url: str,
		aet: str,
		bearer_token: Optional[str] = None,
		timeout: int = 30,
		verify_ssl: bool = True
	):
		"""
		Initialize UPS-RS Client.
		
		Args:
			base_url: Base URL of the DICOMweb server (e.g., http://server:8080/dcm4chee-arc/aets/DCM4CHEE/rs)
			aet: Application Entity Title for this client
			bearer_token: Optional OAuth2 bearer token for authentication
			timeout: Request timeout in seconds
			verify_ssl: Whether to verify SSL certificates
		"""
		self.base_url = base_url.rstrip("/")
		self.aet = aet
		self.bearer_token = bearer_token
		self.timeout = timeout
		self.verify_ssl = verify_ssl
		self._session = None
		self._websocket = None
		self._ws_callbacks: List[Callable] = []
	
	@property
	def session(self) -> requests.Session:
		"""Get or create HTTP session with default headers."""
		if self._session is None:
			self._session = requests.Session()
			self._session.headers.update({
				"Accept": self.APPLICATION_DICOM_JSON,
				"Content-Type": self.APPLICATION_DICOM_JSON,
			})
			if self.bearer_token:
				self._session.headers["Authorization"] = f"Bearer {self.bearer_token}"
			self._session.verify = self.verify_ssl
		return self._session
	
	def _url(self, path: str) -> str:
		"""Build full URL from path."""
		return f"{self.base_url}/{path.lstrip('/')}"
	
	def _handle_response(self, response: requests.Response) -> Optional[Dict]:
		"""Handle HTTP response, raise on error."""
		if response.status_code >= 400:
			error_msg = f"UPS-RS Error: {response.status_code}"
			try:
				error_data = response.json()
				error_msg += f" - {error_data}"
			except Exception:
				error_msg += f" - {response.text}"
			frappe.log_error(error_msg, "UPS-RS Client Error")
			raise UpsRSError(response.status_code, error_msg)
		
		if response.status_code == 204 or not response.content:
			return None
		
		try:
			return response.json()
		except json.JSONDecodeError:
			return {"raw": response.text}
	
	# ============================================================
	# Workitem Operations
	# ============================================================
	
	def create_workitem(
		self,
		workitem: Workitem,
		uid: Optional[str] = None
	) -> str:
		"""
		Create a new UPS Workitem.
		
		Args:
			workitem: Workitem data to create
			uid: Optional UID to assign (generated if not provided)
		
		Returns:
			UID of the created workitem
		"""
		if uid is None:
			uid = self._generate_uid()
		
		# Ensure required fields
		if not workitem.scheduled_start_datetime:
			workitem.scheduled_start_datetime = datetime.now()
		
		url = self._url(f"workitems?{uid}")
		data = workitem.to_dicom_json()
		
		response = self.session.post(url, json=data, timeout=self.timeout)
		self._handle_response(response)
		
		# Extract UID from Location header if present
		location = response.headers.get("Location", "")
		if location:
			uid = location.split("/")[-1]
		
		frappe.logger().info(f"UPS-RS: Created workitem {uid}")
		return uid
	
	def retrieve_workitem(self, uid: str) -> Workitem:
		"""
		Retrieve a UPS Workitem by UID.
		
		Args:
			uid: Workitem UID
		
		Returns:
			Workitem object
		"""
		url = self._url(f"workitems/{uid}")
		response = self.session.get(url, timeout=self.timeout)
		data = self._handle_response(response)
		
		if isinstance(data, list) and data:
			data = data[0]
		
		return Workitem.from_dicom_json(data) if data else None
	
	def update_workitem(
		self,
		uid: str,
		workitem: Workitem,
		transaction_uid: Optional[str] = None
	) -> None:
		"""
		Update a UPS Workitem.
		
		Args:
			uid: Workitem UID
			workitem: Updated workitem data
			transaction_uid: Transaction UID (required if workitem is IN PROGRESS)
		"""
		url = self._url(f"workitems/{uid}")
		if transaction_uid:
			url += f"?{transaction_uid}"
		
		data = workitem.to_dicom_json()
		response = self.session.post(url, json=data, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Updated workitem {uid}")
	
	def search_workitems(
		self,
		filters: Optional[Dict[str, str]] = None,
		limit: Optional[int] = None,
		offset: Optional[int] = None
	) -> List[Workitem]:
		"""
		Search for UPS Workitems.
		
		Args:
			filters: DICOM attribute filters (e.g., {"00741000": "SCHEDULED"})
			limit: Maximum number of results
			offset: Result offset for pagination
		
		Returns:
			List of matching Workitems
		"""
		params = filters.copy() if filters else {}
		if limit:
			params["limit"] = str(limit)
		if offset:
			params["offset"] = str(offset)
		
		url = self._url("workitems")
		if params:
			url += "?" + urlencode(params)
		
		response = self.session.get(url, timeout=self.timeout)
		data = self._handle_response(response)
		
		if not data:
			return []
		
		if not isinstance(data, list):
			data = [data]
		
		return [Workitem.from_dicom_json(item) for item in data]
	
	# ============================================================
	# State Change Operations
	# ============================================================
	
	def change_state(
		self,
		uid: str,
		state: ProcedureStepState,
		transaction_uid: Optional[str] = None
	) -> str:
		"""
		Change Workitem state.
		
		Args:
			uid: Workitem UID
			state: Target state
			transaction_uid: Transaction UID (required for IN PROGRESS, generated if not provided)
		
		Returns:
			Transaction UID
		"""
		if state == ProcedureStepState.IN_PROGRESS and not transaction_uid:
			transaction_uid = self._generate_uid()
		
		if not transaction_uid:
			raise ValueError(f"Transaction UID required for state change to {state.value}")
		
		url = self._url(f"workitems/{uid}/state/{self.aet}")
		data = {
			Tag.TransactionUID: {"vr": "UI", "Value": [transaction_uid]},
			Tag.ProcedureStepState: {"vr": "CS", "Value": [state.value]},
		}
		
		response = self.session.put(url, json=data, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Changed workitem {uid} state to {state.value}")
		return transaction_uid
	
	def start_workitem(self, uid: str) -> str:
		"""
		Start a workitem (change to IN PROGRESS).
		
		Args:
			uid: Workitem UID
		
		Returns:
			Transaction UID for subsequent operations
		"""
		return self.change_state(uid, ProcedureStepState.IN_PROGRESS)
	
	def complete_workitem(
		self,
		uid: str,
		transaction_uid: str,
		performed_procedure_start: Optional[datetime] = None,
		performed_procedure_end: Optional[datetime] = None,
		performed_workitem_code: Optional[DicomCode] = None,
		performed_station_name: Optional[DicomCode] = None
	) -> None:
		"""
		Complete a workitem with Final State Requirements.
		
		This is a two-step process:
		1. Update the workitem with UnifiedProcedureStepPerformedProcedureSequence (Final State Requirements)
		2. Change the state to COMPLETED
		
		Args:
			uid: Workitem UID
			transaction_uid: Transaction UID from start_workitem
			performed_procedure_start: When procedure started (defaults to now)
			performed_procedure_end: When procedure ended (defaults to now)
			performed_workitem_code: Code for the performed workitem
			performed_station_name: Name of the station that performed it
			
		Note:
			DICOM UPS requires Final State Requirements in UnifiedProcedureStepPerformedProcedureSequence (00741216):
			- PerformedProcedureStepStartDateTime (0040,4050)
			- PerformedProcedureStepEndDateTime (0040,4051)
			- PerformedWorkitemCodeSequence (0040,4019)
			- PerformedStationNameCodeSequence (0040,4028)
		"""
		now = datetime.now()
		start_dt = performed_procedure_start or now
		end_dt = performed_procedure_end or now
		
		# Build UnifiedProcedureStepPerformedProcedureSequence item (00741216)
		performed_procedure_item = {
			# PerformedProcedureStepStartDateTime (required)
			"00404050": {"vr": "DT", "Value": [start_dt.strftime("%Y%m%d%H%M%S")]},
			# PerformedProcedureStepEndDateTime (required)
			"00404051": {"vr": "DT", "Value": [end_dt.strftime("%Y%m%d%H%M%S")]},
		}
		
		# Add PerformedWorkitemCodeSequence (required for completion)
		if performed_workitem_code:
			performed_procedure_item["00404019"] = {
				"vr": "SQ",
				"Value": [performed_workitem_code.to_dict()]
			}
		else:
			# Default workitem code if not provided
			performed_procedure_item["00404019"] = {
				"vr": "SQ",
				"Value": [{
					"00080100": {"vr": "SH", "Value": ["121726"]},  # Code Value
					"00080102": {"vr": "SH", "Value": ["DCM"]},  # Coding Scheme Designator
					"00080104": {"vr": "LO", "Value": ["Acquisition"]}  # Code Meaning
				}]
			}
		
		# Add PerformedStationNameCodeSequence (required for completion)
		if performed_station_name:
			performed_procedure_item["00404028"] = {
				"vr": "SQ", 
				"Value": [performed_station_name.to_dict()]
			}
		else:
			# Default station name if not provided
			performed_procedure_item["00404028"] = {
				"vr": "SQ",
				"Value": [{
					"00080100": {"vr": "SH", "Value": ["DEFAULT"]},  # Code Value
					"00080102": {"vr": "SH", "Value": ["99LOCAL"]},  # Coding Scheme Designator
					"00080104": {"vr": "LO", "Value": ["Default Station"]}  # Code Meaning
				}]
			}
		
		# Step 1: Update the workitem with the PerformedProcedureSequence
		# This is done via POST /workitems/{uid} with the transaction UID
		update_url = self._url(f"workitems/{uid}")
		update_data = {
			Tag.TransactionUID: {"vr": "UI", "Value": [transaction_uid]},
			# UnifiedProcedureStepPerformedProcedureSequence (00741216)
			"00741216": {
				"vr": "SQ",
				"Value": [performed_procedure_item]
			}
		}
		
		frappe.logger().info(f"UPS-RS: Updating workitem {uid} with PerformedProcedureSequence")
		response = self.session.post(update_url, json=update_data, timeout=self.timeout)
		self._handle_response(response)
		
		# Step 2: Change state to COMPLETED
		state_url = self._url(f"workitems/{uid}/state/{self.aet}")
		state_data = {
			Tag.TransactionUID: {"vr": "UI", "Value": [transaction_uid]},
			Tag.ProcedureStepState: {"vr": "CS", "Value": [ProcedureStepState.COMPLETED.value]},
		}
		
		frappe.logger().info(f"UPS-RS: Changing workitem {uid} state to COMPLETED")
		response = self.session.put(state_url, json=state_data, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Completed workitem {uid}")
	
	def cancel_workitem(self, uid: str, transaction_uid: str) -> None:
		"""
		Cancel a workitem.
		
		Args:
			uid: Workitem UID
			transaction_uid: Transaction UID from start_workitem
		"""
		self.change_state(uid, ProcedureStepState.CANCELED, transaction_uid)
	
	def request_cancellation(
		self,
		uid: str,
		request: Optional[CancellationRequest] = None
	) -> None:
		"""
		Request cancellation of a workitem (by non-owner).
		
		Args:
			uid: Workitem UID
			request: Optional cancellation request details
		"""
		url = self._url(f"workitems/{uid}/cancelrequest/{self.aet}")
		data = request.to_dicom_json() if request else {}
		
		response = self.session.post(url, json=data, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Requested cancellation for workitem {uid}")
	
	# ============================================================
	# Subscription Operations
	# ============================================================
	
	def subscribe_workitem(
		self,
		uid: str,
		deletion_lock: bool = False
	) -> None:
		"""
		Subscribe to a specific workitem's events.
		
		Args:
			uid: Workitem UID
			deletion_lock: Whether to prevent deletion while subscribed
		"""
		url = self._url(f"workitems/{uid}/subscribers/{self.aet}")
		if deletion_lock:
			url += "?deletionlock=true"
		
		response = self.session.post(url, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Subscribed to workitem {uid}")
	
	def subscribe_worklist(
		self,
		filters: Optional[Dict[str, str]] = None,
		deletion_lock: bool = False
	) -> None:
		"""
		Subscribe to worklist events.
		
		Args:
			filters: Optional filters for filtered subscription
			deletion_lock: Whether to prevent deletion while subscribed
		"""
		if filters:
			uid = self.FILTERED_SUBSCRIPTION_UID
			url = self._url(f"workitems/{uid}/subscribers/{self.aet}")
			params = filters.copy()
			if deletion_lock:
				params["deletionlock"] = "true"
			url += "?" + urlencode(params)
		else:
			uid = self.GLOBAL_SUBSCRIPTION_UID
			url = self._url(f"workitems/{uid}/subscribers/{self.aet}")
			if deletion_lock:
				url += "?deletionlock=true"
		
		response = self.session.post(url, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Subscribed to worklist")
	
	def unsubscribe_workitem(self, uid: str) -> None:
		"""Unsubscribe from a workitem."""
		url = self._url(f"workitems/{uid}/subscribers/{self.aet}")
		response = self.session.delete(url, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Unsubscribed from workitem {uid}")
	
	def unsubscribe_worklist(self, filtered: bool = False) -> None:
		"""Unsubscribe from worklist."""
		uid = self.FILTERED_SUBSCRIPTION_UID if filtered else self.GLOBAL_SUBSCRIPTION_UID
		url = self._url(f"workitems/{uid}/subscribers/{self.aet}")
		response = self.session.delete(url, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Unsubscribed from worklist")
	
	def suspend_subscription(self, filtered: bool = False) -> None:
		"""Suspend worklist subscription (stop receiving events temporarily)."""
		uid = self.FILTERED_SUBSCRIPTION_UID if filtered else self.GLOBAL_SUBSCRIPTION_UID
		url = self._url(f"workitems/{uid}/subscribers/{self.aet}/suspend")
		response = self.session.post(url, timeout=self.timeout)
		self._handle_response(response)
		
		frappe.logger().info(f"UPS-RS: Suspended subscription")
	
	# ============================================================
	# WebSocket Operations
	# ============================================================
	
	async def subscribe_websocket(
		self,
		callback: Callable[[str, Dict], None],
		reconnect: bool = True,
		reconnect_delay: int = 5
	) -> None:
		"""
		Open WebSocket channel to receive UPS events.
		
		Args:
			callback: Async function to call on each event (event_type, data)
			reconnect: Whether to automatically reconnect on disconnect
			reconnect_delay: Delay between reconnection attempts
		"""
		ws_url = self._get_websocket_url()
		headers = {}
		if self.bearer_token:
			headers["Authorization"] = f"Bearer {self.bearer_token}"
		
		while True:
			try:
				async with websockets.connect(
					ws_url,
					extra_headers=headers,
					ping_interval=30,
					ping_timeout=10
				) as websocket:
					self._websocket = websocket
					frappe.logger().info(f"UPS-RS: WebSocket connected to {ws_url}")
					
					# Publish connection event to Frappe realtime
					frappe.publish_realtime(
						"ups_websocket_connected",
						{"url": ws_url, "aet": self.aet}
					)
					
					async for message in websocket:
						try:
							event_data = json.loads(message)
							event_type = self._parse_event_type(event_data)
							await callback(event_type, event_data)
							
							# Also publish to Frappe realtime
							frappe.publish_realtime(
								f"ups_event_{event_type.lower()}",
								event_data
							)
						except json.JSONDecodeError:
							frappe.logger().warning(f"UPS-RS: Invalid JSON in WebSocket message: {message}")
						except Exception as e:
							frappe.log_error(f"UPS-RS WebSocket callback error: {e}")
			
			except websockets.exceptions.ConnectionClosed as e:
				frappe.logger().warning(f"UPS-RS: WebSocket closed: {e}")
				if not reconnect:
					break
				await asyncio.sleep(reconnect_delay)
			
			except Exception as e:
				frappe.log_error(f"UPS-RS WebSocket error: {e}")
				if not reconnect:
					break
				await asyncio.sleep(reconnect_delay)
		
		self._websocket = None
	
	async def close_websocket(self) -> None:
		"""Close WebSocket connection."""
		if self._websocket:
			await self._websocket.close()
			self._websocket = None
			frappe.logger().info("UPS-RS: WebSocket closed")
	
	def _get_websocket_url(self) -> str:
		"""Build WebSocket URL from base URL."""
		parsed = urlparse(self.base_url)
		ws_scheme = "wss" if parsed.scheme == "https" else "ws"
		# Standard dcm4chee-arc WebSocket path
		ws_path = parsed.path.replace("/rs", "/ws")
		return f"{ws_scheme}://{parsed.netloc}{ws_path}/subscribers/{self.aet}"
	
	def _parse_event_type(self, event_data: Dict) -> str:
		"""Parse event type from event data."""
		# UPS events typically include event type in the data
		if "00741000" in event_data:  # ProcedureStepState
			return UpsEvent.STATE_REPORT.value
		if "00741002" in event_data:  # ProcedureStepProgress
			return UpsEvent.PROGRESS_REPORT.value
		if Tag.ReasonForCancellation in event_data:
			return UpsEvent.CANCEL_REQUEST.value
		return "Unknown"
	
	# ============================================================
	# Utility Methods
	# ============================================================
	
	@staticmethod
	def _generate_uid() -> str:
		"""Generate a DICOM UID."""
		# Use UUID-based UID generation (2.25 prefix)
		return f"2.25.{uuid.uuid4().int}"
	
	def close(self) -> None:
		"""Close client and release resources."""
		if self._session:
			self._session.close()
			self._session = None
		frappe.logger().info("UPS-RS: Client closed")
	
	def __enter__(self):
		return self
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		self.close()


class UpsRSError(Exception):
	"""UPS-RS specific error."""
	
	def __init__(self, status_code: int, message: str):
		self.status_code = status_code
		self.message = message
		super().__init__(message)


# ============================================================
# Frappe Integration Helpers
# ============================================================

def get_ups_client(settings_name: Optional[str] = None) -> UpsRSClient:
	"""
	Get UPS-RS client configured from Healthcare Settings or specified settings.
	
	Args:
		settings_name: Optional name of specific DICOM server settings
	
	Returns:
		Configured UpsRSClient instance
	"""
	# Try to get settings from Healthcare Settings or custom DocType
	if settings_name:
		settings = frappe.get_doc("DICOM Server Settings", settings_name)
	else:
		# Default to Healthcare Settings
		hs = frappe.get_single("Healthcare Settings")
		settings = frappe._dict({
			"ups_rs_url": hs.get("ups_rs_url", ""),
			"aet": hs.get("dicom_aet", "FRAPPE"),
			"bearer_token": hs.get("dicom_bearer_token"),
			"verify_ssl": hs.get("dicom_verify_ssl", True)
		})
	
	if not settings.get("ups_rs_url"):
		frappe.throw("UPS-RS URL not configured in Healthcare Settings")
	
	return UpsRSClient(
		base_url=settings.ups_rs_url,
		aet=settings.aet,
		bearer_token=settings.get("bearer_token"),
		verify_ssl=settings.get("verify_ssl", True)
	)


@frappe.whitelist()
def create_ups_workitem(
	procedure_step_label: str,
	patient_id: str,
	patient_name: Optional[str] = None,
	accession_number: Optional[str] = None,
	scheduled_start: Optional[str] = None,
	workitem_code: Optional[str] = None,
	station_name: Optional[str] = None
) -> str:
	"""
	Create a UPS Workitem from Frappe.
	
	Args:
		procedure_step_label: Label for the procedure step
		patient_id: Patient ID
		patient_name: Patient name
		accession_number: Accession number
		scheduled_start: Scheduled start datetime (ISO format)
		workitem_code: Workitem code in format code^meaning^scheme
		station_name: Station name code in format code^meaning^scheme
	
	Returns:
		Created workitem UID
	"""
	client = get_ups_client()
	
	workitem = Workitem(
		procedure_step_label=procedure_step_label,
		patient_id=patient_id,
		patient_name=patient_name,
		accession_number=accession_number,
	)
	
	if scheduled_start:
		workitem.scheduled_start_datetime = datetime.fromisoformat(scheduled_start)
	
	if workitem_code:
		workitem.scheduled_workitem_code = DicomCode.from_string(workitem_code)
	
	if station_name:
		workitem.scheduled_station_name = DicomCode.from_string(station_name)
	
	try:
		uid = client.create_workitem(workitem)
		return uid
	finally:
		client.close()


@frappe.whitelist()
def get_ups_workitem(uid: str) -> Dict:
	"""Retrieve a UPS Workitem."""
	client = get_ups_client()
	try:
		workitem = client.retrieve_workitem(uid)
		return {
			"uid": workitem.uid,
			"state": workitem.procedure_step_state.value,
			"label": workitem.procedure_step_label,
			"patient_id": workitem.patient_id,
			"patient_name": workitem.patient_name,
			"scheduled_start": workitem.scheduled_start_datetime.isoformat() if workitem.scheduled_start_datetime else None,
		}
	finally:
		client.close()


@frappe.whitelist()
def search_ups_workitems(
	state: Optional[str] = None,
	patient_id: Optional[str] = None,
	limit: int = 100
) -> List[Dict]:
	"""Search for UPS Workitems."""
	client = get_ups_client()
	
	filters = {}
	if state:
		filters[Tag.ProcedureStepState] = state
	if patient_id:
		filters[Tag.PatientID] = patient_id
	
	try:
		workitems = client.search_workitems(filters, limit=limit)
		return [
			{
				"uid": w.uid,
				"state": w.procedure_step_state.value,
				"label": w.procedure_step_label,
				"patient_id": w.patient_id,
			}
			for w in workitems
		]
	finally:
		client.close()


@frappe.whitelist()
def change_ups_state(
	uid: str,
	state: str,
	transaction_uid: Optional[str] = None
) -> str:
	"""Change UPS Workitem state."""
	client = get_ups_client()
	try:
		return client.change_state(
			uid,
			ProcedureStepState(state),
			transaction_uid
		)
	finally:
		client.close()
