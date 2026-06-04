# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
DICOM MWL-RS (Modality Worklist - RESTful Services) Client

Python client for dcm4chee MWL-RS to manage Modality Worklist items.

MWL (Modality Worklist) is a DICOM service that provides scheduled procedure
information to imaging modalities. Unlike UPS (Unified Procedure Step), MWL
is query-only and does not manage workflow state.

References:
- DICOM PS3.4 (Network Service Procedures)
- DICOM PS3.18 (Web Services)
- dcm4chee-arc MWL-RS documentation
"""

import json
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from urllib.parse import urlencode
from functools import wraps

import frappe
import requests

if TYPE_CHECKING:
    from frappe.model.document import Document


# ==============================================================================
# Retry Configuration (T056)
# ==============================================================================

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


# ==============================================================================
# DICOM Tags for MWL
# ==============================================================================

class Tag:
    """DICOM tags used in MWL-RS."""
    # Patient Module (Patient Level)
    PatientName = "00100010"
    PatientID = "00100020"
    PatientBirthDate = "00100030"
    PatientSex = "00100040"
    
    # Study Module
    StudyInstanceUID = "0020000D"
    AccessionNumber = "00080050"
    ReferringPhysicianName = "00080090"
    
    # Requested Procedure Module
    RequestedProcedureID = "00401001"
    RequestedProcedureDescription = "00321060"
    
    # Scheduled Procedure Step Sequence
    ScheduledProcedureStepSequence = "00400100"
    
    # Scheduled Procedure Step Module (inside sequence)
    ScheduledStationAETitle = "00400001"
    ScheduledProcedureStepStartDate = "00400002"
    ScheduledProcedureStepStartTime = "00400003"
    ScheduledPerformingPhysicianName = "00400006"
    ScheduledProcedureStepDescription = "00400007"
    ScheduledProcedureStepID = "00400009"
    ScheduledStationName = "00400010"
    ScheduledProcedureStepStatus = "00400020"
    Modality = "00080060"


# ==============================================================================
# MwlStatus Enum (T004)
# ==============================================================================

class MwlStatus(Enum):
    """MWL Scheduled Procedure Step Status values supported by dcm4chee."""
    SCHEDULED = "SCHEDULED"
    ARRIVED = "ARRIVED"
    READY = "READY"
    STARTED = "STARTED"
    DEPARTED = "DEPARTED"
    COMPLETED = "COMPLETED"
    DISCONTINUED = "DISCONTINUED"


# ==============================================================================
# MwlRSError Exception (T003)
# ==============================================================================

class MwlRSError(Exception):
    """Exception raised for MWL-RS API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None
    ):
        """
        Initialize MWL-RS error.
        
        Args:
            message: Error description
            status_code: HTTP status code if from API response
            response_body: Raw response body for debugging
        """
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)
    
    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        return " ".join(parts)


# ==============================================================================
# MwlItem Dataclass (T005-T008)
# ==============================================================================

@dataclass
class MwlItem:
    """
    Modality Worklist Item (Scheduled Procedure Step).
    
    Contains all DICOM attributes required for MWL queries.
    Maps between Frappe Healthcare Scheduled Procedure Step DocType
    and DICOM MWL data model.
    """
    
    # Patient Information (Patient Level) - Required
    patient_id: str = ""                      # (0010,0020) Patient ID
    patient_name: str = ""                    # (0010,0010) Patient Name
    patient_birth_date: Optional[str] = None  # (0010,0030) Patient Birth Date (YYYYMMDD)
    patient_sex: Optional[str] = None         # (0010,0040) Patient Sex (M/F/O)
    
    # Study Information - Required
    study_instance_uid: str = ""              # (0020,000D) Study Instance UID
    accession_number: Optional[str] = None    # (0008,0050) Accession Number
    referring_physician_name: Optional[str] = None  # (0008,0090) Referring Physician
    
    # Requested Procedure
    requested_procedure_id: Optional[str] = None        # (0040,1001) Requested Procedure ID
    requested_procedure_description: Optional[str] = None  # (0032,1060) Requested Procedure Description
    
    # Scheduled Procedure Step - Required
    sps_id: str = ""                          # (0040,0009) Scheduled Procedure Step ID
    sps_start_date: str = ""                  # (0040,0002) SPS Start Date (YYYYMMDD)
    sps_start_time: str = ""                  # (0040,0003) SPS Start Time (HHMMSS)
    modality: str = ""                        # (0008,0060) Modality (CT, MR, US, etc.)
    scheduled_station_aet: Optional[str] = None       # (0040,0001) Scheduled Station AE Title
    scheduled_station_name: Optional[str] = None      # (0040,0010) Scheduled Station Name
    sps_description: Optional[str] = None     # (0040,0007) SPS Description
    scheduled_performing_physician: Optional[str] = None  # (0040,0006) Scheduled Performing Physician
    
    # Status
    sps_status: str = "SCHEDULED"             # (0040,0020) SPS Status

    def to_dicom_json(self) -> List[Dict[str, Any]]:
        """
        Convert to DICOM JSON format for MWL-RS API.
        
        Returns DICOM JSON array format expected by dcm4chee MWL-RS.
        
        Returns:
            List containing single DICOM JSON object
        """
        # Build SPS sequence item
        sps_item = {}
        
        if self.sps_id:
            sps_item[Tag.ScheduledProcedureStepID] = {"vr": "SH", "Value": [self.sps_id]}
        
        if self.sps_start_date:
            sps_item[Tag.ScheduledProcedureStepStartDate] = {"vr": "DA", "Value": [self.sps_start_date]}
        
        if self.sps_start_time:
            sps_item[Tag.ScheduledProcedureStepStartTime] = {"vr": "TM", "Value": [self.sps_start_time]}
        
        if self.modality:
            sps_item[Tag.Modality] = {"vr": "CS", "Value": [self.modality]}
        
        if self.scheduled_station_aet:
            sps_item[Tag.ScheduledStationAETitle] = {"vr": "AE", "Value": [self.scheduled_station_aet]}
        
        if self.scheduled_station_name:
            sps_item[Tag.ScheduledStationName] = {"vr": "SH", "Value": [self.scheduled_station_name]}
        
        if self.sps_description:
            sps_item[Tag.ScheduledProcedureStepDescription] = {"vr": "LO", "Value": [self.sps_description]}
        
        if self.scheduled_performing_physician:
            sps_item[Tag.ScheduledPerformingPhysicianName] = {
                "vr": "PN", 
                "Value": [{"Alphabetic": self.scheduled_performing_physician}]
            }
        
        sps_item[Tag.ScheduledProcedureStepStatus] = {"vr": "CS", "Value": [self.sps_status]}
        
        # Build main dataset
        data = {}
        
        # Patient Level
        if self.patient_id:
            data[Tag.PatientID] = {"vr": "LO", "Value": [self.patient_id]}
        
        if self.patient_name:
            data[Tag.PatientName] = {"vr": "PN", "Value": [{"Alphabetic": self.patient_name}]}
        
        if self.patient_birth_date:
            data[Tag.PatientBirthDate] = {"vr": "DA", "Value": [self.patient_birth_date]}
        
        if self.patient_sex:
            data[Tag.PatientSex] = {"vr": "CS", "Value": [self.patient_sex]}
        
        # Study Level
        if self.study_instance_uid:
            data[Tag.StudyInstanceUID] = {"vr": "UI", "Value": [self.study_instance_uid]}
        
        if self.accession_number:
            data[Tag.AccessionNumber] = {"vr": "SH", "Value": [self.accession_number]}
        
        if self.referring_physician_name:
            data[Tag.ReferringPhysicianName] = {
                "vr": "PN",
                "Value": [{"Alphabetic": self.referring_physician_name}]
            }
        
        # Requested Procedure
        if self.requested_procedure_id:
            data[Tag.RequestedProcedureID] = {"vr": "SH", "Value": [self.requested_procedure_id]}
        
        if self.requested_procedure_description:
            data[Tag.RequestedProcedureDescription] = {"vr": "LO", "Value": [self.requested_procedure_description]}
        
        # Scheduled Procedure Step Sequence
        data[Tag.ScheduledProcedureStepSequence] = {"vr": "SQ", "Value": [sps_item]}
        
        return [data]

    @classmethod
    def from_dicom_json(cls, data: Dict[str, Any]) -> "MwlItem":
        """
        Parse from DICOM JSON response.
        
        Args:
            data: Single DICOM JSON object (not array)
            
        Returns:
            MwlItem instance
        """
        def get_value(tag: str, default=None):
            """Extract single value from DICOM JSON attribute."""
            if tag in data and "Value" in data[tag]:
                values = data[tag]["Value"]
                return values[0] if values else default
            return default
        
        def get_pn_value(tag: str, default=None):
            """Extract Person Name value."""
            val = get_value(tag)
            if isinstance(val, dict):
                return val.get("Alphabetic", default)
            return val or default
        
        item = cls()
        
        # Patient Level
        item.patient_id = get_value(Tag.PatientID) or ""
        item.patient_name = get_pn_value(Tag.PatientName) or ""
        item.patient_birth_date = get_value(Tag.PatientBirthDate)
        item.patient_sex = get_value(Tag.PatientSex)
        
        # Study Level
        item.study_instance_uid = get_value(Tag.StudyInstanceUID) or ""
        item.accession_number = get_value(Tag.AccessionNumber)
        item.referring_physician_name = get_pn_value(Tag.ReferringPhysicianName)
        
        # Requested Procedure
        item.requested_procedure_id = get_value(Tag.RequestedProcedureID)
        item.requested_procedure_description = get_value(Tag.RequestedProcedureDescription)
        
        # Scheduled Procedure Step Sequence
        sps_seq = data.get(Tag.ScheduledProcedureStepSequence, {}).get("Value", [])
        if sps_seq:
            sps_item = sps_seq[0]
            
            def get_sps_value(tag: str, default=None):
                if tag in sps_item and "Value" in sps_item[tag]:
                    values = sps_item[tag]["Value"]
                    return values[0] if values else default
                return default
            
            def get_sps_pn_value(tag: str, default=None):
                val = get_sps_value(tag)
                if isinstance(val, dict):
                    return val.get("Alphabetic", default)
                return val or default
            
            item.sps_id = get_sps_value(Tag.ScheduledProcedureStepID) or ""
            item.sps_start_date = get_sps_value(Tag.ScheduledProcedureStepStartDate) or ""
            item.sps_start_time = get_sps_value(Tag.ScheduledProcedureStepStartTime) or ""
            item.modality = get_sps_value(Tag.Modality) or ""
            item.scheduled_station_aet = get_sps_value(Tag.ScheduledStationAETitle)
            item.scheduled_station_name = get_sps_value(Tag.ScheduledStationName)
            item.sps_description = get_sps_value(Tag.ScheduledProcedureStepDescription)
            item.scheduled_performing_physician = get_sps_pn_value(Tag.ScheduledPerformingPhysicianName)
            item.sps_status = get_sps_value(Tag.ScheduledProcedureStepStatus) or "SCHEDULED"
        
        return item
    
    @classmethod
    def from_scheduled_procedure_step(cls, sps: "Document") -> "MwlItem":
        """
        Create MwlItem from Frappe Scheduled Procedure Step document.
        
        Maps Healthcare module SPS DocType fields to DICOM MWL attributes.
        
        Args:
            sps: Scheduled Procedure Step Frappe document
            
        Returns:
            MwlItem populated from SPS document
        """
        item = cls()
        
        # Patient Information - fetch from linked Patient doc
        if sps.patient:
            item.patient_id = sps.patient
            item.patient_name = sps.patient_name or ""
            
            # Get additional patient info if available
            try:
                patient_doc = frappe.get_cached_doc("Patient", sps.patient)
                if patient_doc.dob:
                    item.patient_birth_date = patient_doc.dob.strftime("%Y%m%d")
                if patient_doc.sex:
                    # Map Frappe sex values to DICOM
                    sex_map = {"Male": "M", "Female": "F", "Other": "O"}
                    item.patient_sex = sex_map.get(patient_doc.sex, "O")
            except Exception:
                pass  # Patient info is optional for MWL
        
        # Study Information
        item.study_instance_uid = sps.study_instance_uid or ""
        item.accession_number = getattr(sps, "accession_number", None)
        
        # Referring Physician
        if hasattr(sps, "referring_practitioner") and sps.referring_practitioner:
            try:
                practitioner = frappe.get_cached_doc(
                    "Healthcare Practitioner", sps.referring_practitioner
                )
                item.referring_physician_name = practitioner.practitioner_name
            except Exception:
                pass
        
        # Requested Procedure
        item.requested_procedure_id = getattr(sps, "requested_procedure_id", None)
        item.requested_procedure_description = getattr(sps, "requested_procedure_description", None)
        
        # Scheduled Procedure Step
        item.sps_id = sps.name  # Use doc name as SPS ID
        
        # Parse scheduled datetime
        if sps.scheduled_datetime:
            if isinstance(sps.scheduled_datetime, str):
                try:
                    dt = datetime.fromisoformat(sps.scheduled_datetime)
                except ValueError:
                    dt = datetime.now()
            else:
                dt = sps.scheduled_datetime
            item.sps_start_date = dt.strftime("%Y%m%d")
            item.sps_start_time = dt.strftime("%H%M%S")
        
        item.modality = sps.modality or ""
        item.scheduled_station_aet = getattr(sps, "station_aet", None)
        item.scheduled_station_name = getattr(sps, "station_name", None)
        
        # SPS Description - use radiology procedure if available
        if hasattr(sps, "radiology_procedure") and sps.radiology_procedure:
            try:
                proc = frappe.get_cached_doc("Radiology Procedure", sps.radiology_procedure)
                item.sps_description = proc.procedure_name
            except Exception:
                pass
        
        if not item.sps_description:
            item.sps_description = getattr(sps, "procedure_description", None)
        
        # Scheduled Performing Physician
        if hasattr(sps, "scheduled_practitioner") and sps.scheduled_practitioner:
            try:
                practitioner = frappe.get_cached_doc(
                    "Healthcare Practitioner", sps.scheduled_practitioner
                )
                item.scheduled_performing_physician = practitioner.practitioner_name
            except Exception:
                pass
        
        # Status - map UPS state to MWL status
        ups_state = getattr(sps, "ups_state", "SCHEDULED")
        state_map = {
            "SCHEDULED": "SCHEDULED",
            "IN PROGRESS": "STARTED",
            "COMPLETED": "COMPLETED",
            "CANCELED": "DISCONTINUED",
        }
        item.sps_status = state_map.get(ups_state, "SCHEDULED")
        
        return item


# ==============================================================================
# MwlRSClient Class (T009-T016)
# ==============================================================================

class MwlRSClient:
    """
    Client for dcm4chee MWL-RS (Modality Worklist RESTful Services).
    
    Manages MWL items (Scheduled Procedure Steps) on the dcm4chee archive
    for modality worklist queries via DICOM C-FIND.
    
    Usage:
        client = MwlRSClient(
            base_url="http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs"
        )
        
        # Create MWL item
        mwl_item = MwlItem.from_scheduled_procedure_step(sps_doc)
        study_uid = client.create_mwl_item(mwl_item)
        
        # Delete MWL item
        client.delete_mwl_item(study_uid, sps_id)
        
        # Search MWL items
        items = client.search_mwl_items({"Modality": "CT"})
    """
    
    APPLICATION_DICOM_JSON = "application/dicom+json"
    
    def __init__(
        self,
        base_url: str,
        aet: str = "DCM4CHEE",
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY
    ):
        """
        Initialize MWL-RS client.
        
        Args:
            base_url: Base URL for dcm4chee REST services 
                      (e.g., "http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs")
            aet: Application Entity Title (default: DCM4CHEE)
            username: Optional Basic Auth username
            password: Optional Basic Auth password
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
            max_retries: Maximum retry attempts for transient errors (default: 3)
            retry_delay: Delay between retries in seconds (default: 1.0)
        """
        self.base_url = base_url.rstrip("/")
        self.aet = aet
        self.username = username
        self.password = password
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: Optional[requests.Session] = None
    
    @property
    def session(self) -> requests.Session:
        """Get or create HTTP session with default headers."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Accept": self.APPLICATION_DICOM_JSON,
                "Content-Type": self.APPLICATION_DICOM_JSON,
            })
            if self.username and self.password:
                self._session.auth = (self.username, self.password)
            self._session.verify = self.verify_ssl
        return self._session
    
    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request with retry logic for transient errors.
        
        Retries on connection errors, timeouts, and certain HTTP status codes
        (408, 429, 500, 502, 503, 504).
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            url: Request URL
            **kwargs: Additional arguments passed to requests
            
        Returns:
            HTTP response
            
        Raises:
            MwlRSError: After all retries exhausted
        """
        kwargs.setdefault("timeout", self.timeout)
        last_error: Optional[Exception] = None
        
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(method, url, **kwargs)
                
                # Check if we should retry based on status code
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    frappe.logger().warning(
                        f"MWL-RS: Retryable status {response.status_code} for {method} {url}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}"
                    )
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                
                return response
                
            except RETRYABLE_EXCEPTIONS as e:
                last_error = e
                if attempt < self.max_retries:
                    frappe.logger().warning(
                        f"MWL-RS: Retryable error for {method} {url}: {e}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}"
                    )
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise MwlRSError(
                    f"MWL-RS request failed after {self.max_retries + 1} attempts: {e}"
                )
            except requests.RequestException as e:
                # Non-retryable request error
                raise MwlRSError(f"MWL-RS request failed: {e}")
        
        # Should not reach here, but handle it anyway
        if last_error:
            raise MwlRSError(f"MWL-RS request failed: {last_error}")
        raise MwlRSError("MWL-RS request failed: Unknown error")
    
    def _url(self, path: str) -> str:
        """Build full URL from path."""
        return f"{self.base_url}/{path.lstrip('/')}"
    
    def _handle_response(
        self, 
        response: requests.Response,
        allow_404: bool = False
    ) -> Optional[Any]:
        """
        Handle HTTP response, raise on error.
        
        Args:
            response: HTTP response object
            allow_404: If True, return None on 404 instead of raising
            
        Returns:
            Parsed JSON response or None
            
        Raises:
            MwlRSError: On HTTP error
        """
        # Handle 404 specially if allowed
        if response.status_code == 404 and allow_404:
            return None
        
        if response.status_code >= 400:
            error_msg = f"MWL-RS Error: HTTP {response.status_code}"
            response_body = None
            try:
                error_data = response.json()
                error_msg += f" - {error_data}"
                response_body = json.dumps(error_data)
            except Exception:
                error_msg += f" - {response.text}"
                response_body = response.text
            
            frappe.log_error(error_msg, "MWL-RS Client Error")
            raise MwlRSError(error_msg, response.status_code, response_body)
        
        # No content responses
        if response.status_code == 204 or not response.content:
            return None
        
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw": response.text}
    
    # ==========================================================================
    # MWL Item Operations (T010-T016)
    # ==========================================================================
    
    def create_mwl_item(self, mwl_item: MwlItem) -> str:
        """
        Create a new MWL item (Scheduled Procedure Step).
        
        POST /mwlitems
        
        Args:
            mwl_item: MWL item data
            
        Returns:
            Study Instance UID of created item
            
        Raises:
            MwlRSError: On HTTP error or invalid response
        """
        url = self._url("mwlitems")
        data = mwl_item.to_dicom_json()
        
        response = self._request_with_retry("POST", url, json=data)
        self._handle_response(response)
        
        frappe.logger().info(
            f"MWL-RS: Created MWL item StudyUID={mwl_item.study_instance_uid}, "
            f"SPSID={mwl_item.sps_id}"
        )
        
        return mwl_item.study_instance_uid
    
    def delete_mwl_item(self, study_instance_uid: str, sps_id: str) -> bool:
        """
        Delete an MWL item.
        
        DELETE /mwlitems/{studyUID}/{spsID}
        
        Args:
            study_instance_uid: DICOM Study Instance UID
            sps_id: Scheduled Procedure Step ID
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            MwlRSError: On HTTP error (except 404)
        """
        url = self._url(f"mwlitems/{study_instance_uid}/{sps_id}")
        
        response = self._request_with_retry("DELETE", url)
        
        if response.status_code == 404:
            frappe.logger().debug(
                f"MWL-RS: MWL item not found StudyUID={study_instance_uid}, SPSID={sps_id}"
            )
            return False
        
        self._handle_response(response)
        
        frappe.logger().info(
            f"MWL-RS: Deleted MWL item StudyUID={study_instance_uid}, SPSID={sps_id}"
        )
        return True
    
    def update_mwl_item(self, mwl_item: MwlItem) -> None:
        """
        Update an existing MWL item.
        
        POST /mwlitems (idempotent - creates or updates)
        
        Note: MWL-RS POST is idempotent based on Study Instance UID + SPS ID.
        
        Args:
            mwl_item: MWL item data with existing study_instance_uid
            
        Raises:
            MwlRSError: On HTTP error
        """
        # MWL-RS uses POST for both create and update (idempotent)
        self.create_mwl_item(mwl_item)
        
        frappe.logger().info(
            f"MWL-RS: Updated MWL item StudyUID={mwl_item.study_instance_uid}, "
            f"SPSID={mwl_item.sps_id}"
        )
    
    def search_mwl_items(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[MwlItem]:
        """
        Search for MWL items.
        
        GET /mwlitems
        
        Args:
            filters: QIDO-RS style query parameters (e.g., {"Modality": "CT"})
            limit: Maximum results to return
            offset: Result offset for pagination
            
        Returns:
            List of matching MWL items
            
        Raises:
            MwlRSError: On HTTP error
        """
        params = filters.copy() if filters else {}
        params["limit"] = limit
        params["offset"] = offset
        
        url = self._url("mwlitems")
        if params:
            url += "?" + urlencode(params)
        
        response = self._request_with_retry("GET", url)
        data = self._handle_response(response)
        
        if not data:
            return []
        
        if isinstance(data, list):
            return [MwlItem.from_dicom_json(item) for item in data]
        
        return []
    
    def mwl_item_exists(self, study_instance_uid: str, sps_id: str) -> bool:
        """
        Check if MWL item exists.
        
        Uses search with specific UID filter.
        
        Args:
            study_instance_uid: DICOM Study Instance UID
            sps_id: Scheduled Procedure Step ID
            
        Returns:
            True if exists, False otherwise
        """
        try:
            items = self.search_mwl_items({
                "StudyInstanceUID": study_instance_uid,
                "ScheduledProcedureStepID": sps_id
            }, limit=1)
            return len(items) > 0
        except MwlRSError:
            return False
    
    def count_mwl_items(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count MWL items matching filters.
        
        GET /mwlitems/count
        
        Args:
            filters: QIDO-RS style query parameters
            
        Returns:
            Count of matching items
            
        Raises:
            MwlRSError: On HTTP error
        """
        url = self._url("mwlitems/count")
        if filters:
            url += "?" + urlencode(filters)
        
        response = self._request_with_retry("GET", url)
        data = self._handle_response(response)
        
        if isinstance(data, dict) and "count" in data:
            return int(data["count"])
        elif isinstance(data, int):
            return data
        
        return 0
    
    def change_status(
        self,
        study_instance_uid: str,
        sps_id: str,
        status: MwlStatus
    ) -> None:
        """
        Change status of an MWL item.
        
        POST /mwlitems/{studyUID}/{spsID}/status/{status}
        
        Args:
            study_instance_uid: DICOM Study Instance UID
            sps_id: Scheduled Procedure Step ID
            status: New MWL status
            
        Raises:
            MwlRSError: On HTTP error
        """
        url = self._url(
            f"mwlitems/{study_instance_uid}/{sps_id}/status/{status.value}"
        )
        
        response = self._request_with_retry("POST", url)
        self._handle_response(response)
        
        frappe.logger().info(
            f"MWL-RS: Changed status StudyUID={study_instance_uid}, "
            f"SPSID={sps_id}, NewStatus={status.value}"
        )
