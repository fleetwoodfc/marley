import frappe
from frappe import _
from frappe.utils import get_datetime


def _as_iso(dt):
	if not dt:
		return None
	try:
		return get_datetime(dt).isoformat()
	except Exception:
		return str(dt)


def _build_codings_from_codification_table(rows):
	codings = []
	for row in rows or []:
		system = row.get("system")
		code = row.get("code")
		display = row.get("display")
		if system and code:
			codings.append(
				{
					"system": system,
					"code": code,
					"display": display,
				}
			)
	return codings


def _get_doc_or_404(doctype, name):
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} not found").format(doctype, name), frappe.DoesNotExistError)
	return frappe.get_doc(doctype, name)


@frappe.whitelist()
def get_patient_for_fhir(name: str):
	doc = _get_doc_or_404("Patient", name)

	return {
		"id": doc.name,
		"full_name": doc.patient_name,
		"first_name": doc.first_name,
		"middle_name": doc.middle_name,
		"last_name": doc.last_name,
		"gender": doc.sex,
		"birth_date": str(doc.dob) if doc.dob else None,
		"email": doc.email,
		"mobile": doc.mobile,
		"phone": doc.phone,
		"active": False if doc.status == "Disabled" else True,
		"meta": {
			"doctype": doc.doctype,
			"last_modified": _as_iso(doc.modified),
		},
	}


@frappe.whitelist()
def get_service_request_for_fhir(name: str):
	doc = _get_doc_or_404("Service Request", name)

	codings = _build_codings_from_codification_table(doc.get("codification_table"))

	return {
		"id": doc.name,
		"patient_id": doc.patient,
		"requester_id": doc.practitioner or doc.referred_to_practitioner,
		"status": doc.status,
		"intent_code": doc.intent,
		"priority_code": doc.priority,
		"authored_on": _as_iso(doc.creation),
		"display": doc.template_dn,
		"template_type": doc.template_dt,
		"template_name": doc.template_dn,
		"encounter_id": doc.order_group if doc.source_doc == "Patient Encounter" else None,
		"codings": codings,
		"meta": {
			"doctype": doc.doctype,
			"last_modified": _as_iso(doc.modified),
		},
	}


def _extract_observation_result(doc):
	if doc.get("result_boolean") is not None:
		return {
			"type": "boolean",
			"value": bool(doc.result_boolean),
		}

	if doc.get("result_text"):
		return {
			"type": "string",
			"value": doc.result_text,
		}

	if doc.get("result_select"):
		return {
			"type": "codeable-concept",
			"value": doc.result_select,
			"display": doc.result_select,
		}

	if doc.get("result_data") not in (None, ""):
		try:
			return {
				"type": "quantity",
				"value": float(doc.result_data),
				"unit": doc.get("uom"),
			}
		except Exception:
			return {
				"type": "string",
				"value": str(doc.result_data),
			}

	if doc.get("result_attach"):
		return {
			"type": "attachment",
			"value": doc.result_attach,
		}

	return None


@frappe.whitelist()
def get_observation_for_fhir(name: str):
	doc = _get_doc_or_404("Observation", name)

	codings = _build_codings_from_codification_table(doc.get("codification_table"))
	result = _extract_observation_result(doc)

	return {
		"id": doc.name,
		"patient_id": doc.patient,
		"service_request_id": doc.service_request,
		"performer_id": doc.healthcare_practitioner,
		"specimen_id": doc.specimen,
		"status": doc.status,
		"effective_datetime": _as_iso(doc.posting_datetime),
		"issued_datetime": _as_iso(doc.time_of_result),
		"permitted_data_type": doc.permitted_data_type,
		"display": doc.observation_template or doc.name,
		"reference_doctype": doc.reference_doctype,
		"reference_docname": doc.reference_docname,
		"parent_observation_id": doc.parent_observation,
		"codings": codings,
		"result": result,
		"note": doc.note,
		"meta": {
			"doctype": doc.doctype,
			"last_modified": _as_iso(doc.modified),
		},
	}
