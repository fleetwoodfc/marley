import json

import frappe
from frappe import _
from frappe.utils import get_datetime


def _as_iso(dt):
	if not dt:
		return None
	try:
		return get_datetime(dt).isoformat()
	except (TypeError, ValueError, AttributeError):
		return str(dt)


def _build_codings_from_codification_table(rows):
	codings = []
	for row in rows or []:
		system = row.get("system")
		code = row.get("code")
		display = row.get("display")
		if system and code:
			coding = {"system": system, "code": code}
			if display:  # omit null display — FHIR rejects null for string fields
				coding["display"] = display
			codings.append(coding)
	return codings


def _get_doc_or_raise(doctype, name):
	"""Fetch a document or raise DoesNotExistError (single DB call).

	Note: Frappe's REST layer maps DoesNotExistError to HTTP 417, not 404.
	"""
	try:
		return frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		frappe.throw(_("{0} {1} not found").format(doctype, name), frappe.DoesNotExistError)


def _get_code_value(link_value):
	"""Resolve a Code Value link field to its FHIR-compatible code string.

	status/intent/priority on ServiceRequest are Link fields pointing to
	Code Value documents. doc.status contains the document name (e.g.
	'SR-STATUS-001'), not the FHIR code string. This fetches the actual
	code_value field from the linked document.
	"""
	if not link_value:
		return None
	return frappe.get_value("Code Value", link_value, "code_value") or link_value


def _extract_observation_value(doc):
	"""Extract the FHIR valueX element based on permitted_data_type.

	Handles all 11 permitted data types defined in Observation.permitted_data_type:
	Boolean, Text, Select, Quantity, Numeric, Range, Ratio, Time, DateTime, Period, Attach

	Dispatches on permitted_data_type (not value-presence) because result_boolean
	is a Select field with default '' — value-presence checks are unreliable.

	Returns a single-key dict with the appropriate FHIR valueX key, or None.
	"""
	data_type = doc.get("permitted_data_type")

	if data_type == "Boolean":
		val = doc.get("result_boolean")
		if val in (None, ""):
			return None
		# Guard against int values (Check field stores 0/1) — coerce to str first
		val_str = str(val).strip().lower()
		return {"valueBoolean": val_str in ("yes", "true", "1")}

	if data_type == "Text":
		val = doc.get("result_text")
		if not val:
			return None
		return {"valueString": val}

	if data_type == "Select":
		val = doc.get("result_select")
		if not val:
			return None
		return {
			"valueCodeableConcept": {
				"coding": [{"code": val, "display": val}],
				"text": val,
			}
		}

	if data_type in ("Quantity", "Numeric"):
		# Use is-not-None check to preserve legitimate zero values (e.g. blood glucose 0.0)
		_float_val = doc.get("result_float")
		val = _float_val if _float_val is not None else doc.get("result_data")
		if val in (None, ""):
			return None
		try:
			return {
				"valueQuantity": {
					"value": float(val),
					"unit": doc.get("uom"),
					"system": "http://unitsofmeasure.org",
				}
			}
		except (TypeError, ValueError):
			return {"valueString": str(val)}

	if data_type in ("Range", "Ratio"):
		# Range stored as "low-high" string; Ratio as "numerator:denominator"
		val = doc.get("result_data")
		if val in (None, ""):
			return None
		return {"valueString": str(val)}

	if data_type == "Time":
		val = doc.get("result_time")
		if not val:
			return None
		return {"valueTime": _as_iso(val)}

	if data_type == "DateTime":
		val = doc.get("result_datetime")
		if not val:
			return None
		return {"valueDateTime": _as_iso(val)}

	if data_type == "Period":
		period_from = doc.get("result_period_from")
		period_to = doc.get("result_period_to")
		if not period_from and not period_to:
			return None
		return {
			"valuePeriod": {
				"start": _as_iso(period_from),
				"end": _as_iso(period_to),
			}
		}

	if data_type == "Attach":
		val = doc.get("result_attach")
		if not val:
			return None
		return {"valueAttachment": {"url": val}}

	return None


@frappe.whitelist()
def get_patient_for_fhir(name: str):
	"""Return a FHIR R4 Patient resource for the given Frappe Patient name."""
	frappe.logger("fhir_integration").info("get_patient_for_fhir: %s", name)
	doc = _get_doc_or_raise("Patient", name)

	given = [n for n in [doc.first_name, doc.middle_name] if n]

	telecom = []
	if doc.phone:
		telecom.append({"system": "phone", "value": doc.phone, "use": "home"})
	if doc.mobile:
		telecom.append({"system": "phone", "value": doc.mobile, "use": "mobile"})
	if doc.email:
		telecom.append({"system": "email", "value": doc.email})

	return {
		"resourceType": "Patient",
		"id": doc.name,
		"active": doc.status != "Disabled",
		"name": [
			{
				"use": "official",
				"text": doc.patient_name,
				"family": doc.last_name or "",
				"given": given,
			}
		],
		"gender": (doc.sex or "unknown").lower(),
		"birthDate": str(doc.dob) if doc.dob else None,
		"telecom": telecom,
		"meta": {
			"lastUpdated": _as_iso(doc.modified),
		},
	}


@frappe.whitelist()
def get_service_request_for_fhir(name: str):
	"""Return a FHIR R4 ServiceRequest resource for the given Frappe Service Request name."""
	frappe.logger("fhir_integration").info("get_service_request_for_fhir: %s", name)
	doc = _get_doc_or_raise("Service Request", name)

	codings = _build_codings_from_codification_table(doc.get("codification_table"))
	accession_number = (
		"ACC-{}-{}".format(str(doc.creation)[:10].replace("-", ""), doc.name) if doc.creation else doc.name
	)

	result = {
		"resourceType": "ServiceRequest",
		"id": doc.name,
		"identifier": [
			{
				"value": accession_number,
				"type": {
					"coding": [
						{
							"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
							"code": "ACSN",
						}
					]
				},
			}
		],
		"status": _get_code_value(doc.status) or "unknown",
		"intent": _get_code_value(doc.intent) or "order",
		"priority": _get_code_value(doc.priority),
		"subject": {"reference": f"Patient/{doc.patient}"},
		"code": {
			"coding": codings,
			"text": doc.template_dn,
		},
		"authoredOn": _as_iso(doc.creation),
		"meta": {
			"lastUpdated": _as_iso(doc.modified),
		},
		# Deprecated alias — kept for backwards compatibility with existing consumers
		"display": doc.template_dn,
	}

	requester = doc.practitioner or doc.referred_to_practitioner
	if requester:
		result["requester"] = {"reference": f"Practitioner/{requester}"}

	if doc.source_doc == "Patient Encounter" and doc.order_group:
		result["encounter"] = {"reference": f"Encounter/{doc.order_group}"}

	return result


@frappe.whitelist()
def get_observation_for_fhir(name: str):
	"""Return a FHIR R4 Observation resource for the given Frappe Observation name."""
	frappe.logger("fhir_integration").info("get_observation_for_fhir: %s", name)
	doc = _get_doc_or_raise("Observation", name)

	codings = _build_codings_from_codification_table(doc.get("codification_table"))
	value_element = _extract_observation_value(doc)

	if not doc.patient:
		frappe.throw(_("Observation {0} has no patient — cannot generate FHIR resource").format(doc.name))

	result = {
		"resourceType": "Observation",
		"id": doc.name,
		"status": _get_code_value(doc.status) or "unknown",
		"subject": {"reference": f"Patient/{doc.patient}"},
		"code": {
			"coding": codings,
			"text": doc.observation_template or doc.name,
		},
		"effectiveDateTime": _as_iso(doc.posting_datetime),
		"issued": _as_iso(doc.time_of_result),
		"meta": {
			"lastUpdated": _as_iso(doc.modified),
		},
	}

	if doc.service_request:
		result["basedOn"] = [{"reference": f"ServiceRequest/{doc.service_request}"}]

	if doc.healthcare_practitioner:
		result["performer"] = [{"reference": f"Practitioner/{doc.healthcare_practitioner}"}]

	if doc.specimen:
		result["specimen"] = {"reference": f"Specimen/{doc.specimen}"}

	if doc.parent_observation:
		result["derivedFrom"] = [{"reference": f"Observation/{doc.parent_observation}"}]

	if doc.note:
		result["note"] = [{"text": doc.note}]

	if value_element:
		result.update(value_element)

	return result


@frappe.whitelist()
def get_imaging_study_by_service_request(sr_name: str):
	"""Return a FHIR R4 ImagingStudy for the given Service Request name.

	Retrieves the ImagingStudy JSON stored as a file attachment on the
	ServiceRequest after a dcm4chee imaging workflow completes.

	TODO: Implement full attachment storage once dcm4chee_bridge.py is in place.
	"""
	frappe.logger("fhir_integration").info("get_imaging_study_by_service_request: %s", sr_name)
	_get_doc_or_raise("Service Request", sr_name)

	attachment = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Service Request",
			"attached_to_name": sr_name,
			"file_name": ["like", "%imaging_study%"],
		},
		fields=["name", "file_url", "creation"],
		order_by="creation desc",
		limit=1,
	)

	if not attachment:
		frappe.throw(
			_("No ImagingStudy found for Service Request {0}").format(sr_name),
			frappe.DoesNotExistError,
		)

	# Fetch by name (from get_all) to avoid TOCTOU and ambiguous file_url lookups
	file_doc = frappe.get_doc("File", attachment[0].name)
	try:
		return json.loads(file_doc.get_content())
	except (ValueError, TypeError):
		frappe.throw(_("ImagingStudy attachment for {0} is not valid JSON").format(sr_name))
