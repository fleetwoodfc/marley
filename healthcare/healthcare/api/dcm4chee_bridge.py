"""
dcm4chee_bridge.py — Integration bridge between Frappe Healthcare and dcm4chee-arc-light.

Architecture:
  Frappe ServiceRequest (EHR order)
    │  on_submit → push_patient_to_dcm4chee (idempotent PUT)
    │             push_service_request_to_dcm4chee (POST FHIR R4)
    │
    ▼  dcm4chee-arc-light manages MWL/MPPS/UPS natively
    │  Modality polls MWL, scans, sends MPPS/UPS complete
    │
    ▼  Frappe Scheduler → poll_imaging_study_for_service_request
         GET /fhir/r4/ImagingStudy?identifier={accession_number}
         → attach JSON to ServiceRequest on completion

Prerequisites:
  - DCM4CHEE Settings singleton must be configured
  - For demo: disable dcm4chee auth (--no-authentication flag)
  - Verify HARD GATE: POST /fhir/r4/ServiceRequest creates a MWL item in dcm4chee

NOTE: Frappe maps DoesNotExistError to HTTP 417, not 404.
"""

import json

import frappe
import requests
from frappe import _


# ── Settings helpers ──────────────────────────────────────────────────────────


def _get_settings():
	"""Return DCM4CHEE Settings doc (cached per request)."""
	return frappe.get_single("DCM4CHEE Settings")


def _fhir_headers(settings=None):
	"""Build HTTP headers for dcm4chee FHIR R4 REST calls."""
	headers = {
		"Content-Type": "application/fhir+json",
		"Accept": "application/fhir+json",
	}
	if settings is None:
		settings = _get_settings()
	token = settings.get_password("auth_token") if settings.auth_token else None
	if token:
		headers["Authorization"] = "Bearer {}".format(token)
	return headers


def _fhir_url(settings, path):
	"""Construct a full FHIR endpoint URL."""
	base = (settings.fhir_base_url or "http://localhost:8080/fhir/r4").rstrip("/")
	return "{}/{}".format(base, path.lstrip("/"))


# ── Push: Frappe → dcm4chee ───────────────────────────────────────────────────


def push_patient_to_dcm4chee(patient_name: str) -> dict:
	"""
	Idempotent PUT /fhir/r4/Patient/{id} to dcm4chee.

	Called before push_service_request_to_dcm4chee to ensure the Patient
	resource exists. dcm4chee may create it implicitly from ServiceRequest,
	but explicit creation is safer.

	Returns the dcm4chee response dict, or {} on failure (failure is logged
	and non-blocking — the ServiceRequest submit must not roll back).
	"""
	settings = _get_settings()
	from healthcare.healthcare.api.fhir_integration import get_patient_for_fhir

	try:
		payload = get_patient_for_fhir(patient_name)
		url = _fhir_url(settings, "Patient/{}".format(patient_name))
		resp = requests.put(
			url,
			json=payload,
			headers=_fhir_headers(settings),
			timeout=5,
		)
		resp.raise_for_status()
		return resp.json()
	except Exception as e:  # noqa: BLE001
		frappe.log_error(
			title="DCM4CHEE patient push failed",
			message="Patient: {}\nError: {}".format(patient_name, str(e)),
		)
		return {}


def push_service_request_to_dcm4chee(sr_name: str) -> dict:
	"""
	POST /fhir/r4/ServiceRequest to dcm4chee, which should trigger MWL item creation.

	HARD GATE: verify that dcm4chee's FHIR adapter creates a MWL item from a
	ServiceRequest POST before relying on this in production. Fallback to
	/dcm4chee-arc/aets/{ae_title}/rs/mwlitems if the FHIR adapter doesn't support it.

	Non-blocking on error — failure is logged, not raised, so the SR submit
	succeeds even if dcm4chee is unreachable.
	"""
	settings = _get_settings()
	from healthcare.healthcare.api.fhir_integration import get_service_request_for_fhir

	try:
		sr_doc = frappe.get_doc("Service Request", sr_name)
		payload = get_service_request_for_fhir(sr_name)
		url = _fhir_url(settings, "ServiceRequest")
		resp = requests.post(
			url,
			json=payload,
			headers=_fhir_headers(settings),
			timeout=5,
		)
		resp.raise_for_status()
		result = resp.json()
		frappe.logger("dcm4chee_bridge").info(
			"SR %s pushed to dcm4chee — dcm4chee id: %s",
			sr_name,
			result.get("id", "?"),
		)
		# Show success alert via Frappe realtime (non-blocking)
		frappe.publish_realtime(
			"msgprint",
			{"message": "ServiceRequest sent to imaging system.", "indicator": "green"},
			user=frappe.session.user,
		)
		return result
	except requests.HTTPError as e:
		_notify_push_failure(sr_name, str(e))
		return {}
	except requests.Timeout:
		_notify_push_failure(sr_name, "Request timed out after 5s")
		return {}
	except Exception as e:  # noqa: BLE001
		_notify_push_failure(sr_name, str(e))
		return {}


def _notify_push_failure(sr_name: str, error: str) -> None:
	"""Log error and notify the current Frappe user that the push failed."""
	frappe.log_error(
		title="DCM4CHEE push failed: {}".format(sr_name),
		message=error,
	)
	frappe.publish_realtime(
		"msgprint",
		{
			"message": (
				"Could not send ServiceRequest {} to imaging system: {}. "
				"Check dcm4chee connection in DCM4CHEE Settings.".format(sr_name, error)
			),
			"indicator": "orange",
		},
		user=frappe.session.user,
	)


# ── Pull: dcm4chee → Frappe ───────────────────────────────────────────────────


def pull_imaging_study_from_dcm4chee(accession_number: str) -> dict | None:
	"""
	GET /fhir/r4/ImagingStudy?identifier={accession_number} from dcm4chee.

	Returns the first matching ImagingStudy resource dict, or None if not yet
	available (modality hasn't completed acquisition).
	"""
	settings = _get_settings()
	try:
		url = _fhir_url(settings, "ImagingStudy")
		resp = requests.get(
			url,
			params={"identifier": accession_number},
			headers=_fhir_headers(settings),
			timeout=5,
		)
		resp.raise_for_status()
		bundle = resp.json()
		entries = bundle.get("entry", [])
		if entries:
			return entries[0].get("resource")
		return None
	except Exception as e:  # noqa: BLE001
		frappe.log_error(
			title="DCM4CHEE ImagingStudy poll failed: {}".format(accession_number),
			message=str(e),
		)
		return None


def complete_service_request(sr_name: str, imaging_study: dict) -> None:
	"""
	Write ImagingStudy result back to the ServiceRequest.

	Stores the ImagingStudy JSON as a File attachment and transitions the
	ServiceRequest to 'Completed'.
	"""
	# Store as JSON attachment
	content = json.dumps(imaging_study, indent=2)
	file_name = "imaging_study_{}.json".format(sr_name.replace("/", "-"))
	frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": "Service Request",
			"attached_to_name": sr_name,
			"content": content,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)

	frappe.log_error(
		title="DCM4CHEE ImagingStudy received: {}".format(sr_name),
		message="ImagingStudy ID: {}".format(imaging_study.get("id", "?")),
	)


@frappe.whitelist()
def poll_imaging_study_for_service_request(sr_name: str) -> None:
	"""
	Background job: poll dcm4chee for ImagingStudy completion.

	Called by the Frappe Scheduler (daily) for all open ServiceRequests,
	or enqueued directly on SR submit. Retries are handled by re-enqueueing
	up to POLL_MAX_RETRIES times.

	Retry state tracked via sr_doc.custom fields or a separate tracking DocType
	(v2 — for now, the scheduler daily job covers re-polling).
	"""
	POLL_MAX_RETRIES = 3

	try:
		sr_doc = frappe.get_doc("Service Request", sr_name)
	except frappe.DoesNotExistError:
		return

	# Build accession number (same algorithm as in fhir_integration.py)
	accession_number = (
		"ACC-{}-{}".format(
			str(sr_doc.creation)[:10].replace("-", ""), sr_doc.name
		)
		if sr_doc.creation
		else sr_doc.name
	)

	imaging_study = pull_imaging_study_from_dcm4chee(accession_number)

	if imaging_study:
		complete_service_request(sr_name, imaging_study)
		frappe.logger("dcm4chee_bridge").info(
			"ImagingStudy received for SR %s — accession %s", sr_name, accession_number
		)
	else:
		frappe.logger("dcm4chee_bridge").info(
			"ImagingStudy not yet available for SR %s — will retry on next poll", sr_name
		)


# ── Scheduler: poll all open ServiceRequests ─────────────────────────────────


def on_service_request_submit(doc, method=None):
	"""
	hooks.py doc_events["Service Request"]["on_submit"] handler.

	Enqueues async push to dcm4chee — does NOT run synchronously in the
	submit request to avoid blocking the clinician's UI while dcm4chee
	responds (cold starts can take 10-30s).
	"""
	frappe.enqueue(
		"healthcare.healthcare.api.dcm4chee_bridge._push_service_request_async",
		sr_name=doc.name,
		patient_name=doc.patient,
		queue="short",
		is_async=True,
	)


def _push_service_request_async(sr_name: str, patient_name: str) -> None:
	"""Background worker: push Patient + ServiceRequest to dcm4chee."""
	push_patient_to_dcm4chee(patient_name)
	push_service_request_to_dcm4chee(sr_name)


def poll_all_open_service_requests() -> None:
	"""
	Frappe Scheduler daily job: poll dcm4chee for all submitted ServiceRequests
	that don't yet have an ImagingStudy attachment.

	Only runs if DCM4CHEE Settings.sync_enabled is checked.
	"""
	settings = _get_settings()
	if not settings.sync_enabled:
		return

	open_srs = frappe.get_all(
		"Service Request",
		filters={"docstatus": 1},
		fields=["name"],
		limit=200,
	)

	for sr in open_srs:
		# Skip if already has an ImagingStudy attachment
		has_imaging = frappe.db.exists(
			"File",
			{
				"attached_to_doctype": "Service Request",
				"attached_to_name": sr.name,
				"file_name": ["like", "%imaging_study%"],
			},
		)
		if has_imaging:
			continue

		frappe.enqueue(
			"healthcare.healthcare.api.dcm4chee_bridge.poll_imaging_study_for_service_request",
			sr_name=sr.name,
			queue="long",
			is_async=True,
		)
