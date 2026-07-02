# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""
Internal terminology API endpoints for Marley.

All functions are decorated with ``@frappe.whitelist()`` so they are
accessible from the Frappe REST API at::

    /api/method/healthcare.healthcare.api.terminology.<function>

Example calls::

    GET /api/method/healthcare.healthcare.api.terminology.search_concepts
        ?query=malaria&locale=en&limit=20

    GET /api/method/healthcare.healthcare.api.terminology.get_concept
        ?external_id=116128&version=default

    GET /api/method/healthcare.healthcare.api.terminology.validate_code
        ?system=CIEL&code=116128

    GET /api/method/healthcare.healthcare.api.terminology.get_mappings
        ?target_system=ICD-10&code=A09

FHIR-style stubs (phase 2)::

    GET /api/method/healthcare.healthcare.api.terminology.fhir_lookup
        ?system=http://openconceptlab.org/orgs/CIEL/sources/CIEL/&code=116128

    POST /api/method/healthcare.healthcare.api.terminology.fhir_validate_code

    GET /api/method/healthcare.healthcare.api.terminology.fhir_expand
        ?url=<valueSetUrl>
"""

import frappe
from frappe import _

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_default_version_name() -> str | None:
	return frappe.db.get_value("CIEL Terminology Version", {"is_default": 1, "status": "ready"}, "name")


def _resolve_version(version: str | None) -> str | None:
	"""Return the DB name of the requested version, or the default."""
	if not version or version == "default":
		return _get_default_version_name()
	return frappe.db.get_value(
		"CIEL Terminology Version", {"version_tag": version, "status": "ready"}, "name"
	)


def _version_tag(version_name: str | None) -> str | None:
	if not version_name:
		return None
	return frappe.db.get_value("CIEL Terminology Version", version_name, "version_tag")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=False)
def search_concepts(query: str, locale: str = "en", limit: int = 20, version: str = "default"):
	"""
	Search CIEL concepts by name text.

	Returns a list of matching concept summaries including version metadata
	and retired status.
	"""
	version_name = _resolve_version(version)
	if not version_name:
		return {"error": _("No default CIEL terminology version is available."), "results": []}

	limit = min(int(limit), 200)

	# Find concept_name rows matching the query text
	ConceptName = frappe.qb.DocType("CIEL Concept Name")
	Concept = frappe.qb.DocType("CIEL Concept")

	rows = (
		frappe.qb.from_(ConceptName)
		.join(Concept)
		.on(ConceptName.parent == Concept.name)
		.select(
			Concept.name,
			Concept.external_id,
			Concept.concept_class,
			Concept.datatype,
			Concept.retired,
			ConceptName.name_text,
			ConceptName.locale,
			ConceptName.name_type,
			ConceptName.preferred,
		)
		.where(ConceptName.name_text.like(f"%{frappe.db.escape(query, percent=False)}%"))
		.where(ConceptName.locale == locale)
		.where(ConceptName.voided == 0)
		.where(Concept.terminology_version == version_name)
		.limit(limit)
		.run(as_dict=True)
	)

	tag = _version_tag(version_name)
	return {
		"version_tag": tag,
		"results": rows,
	}


@frappe.whitelist(allow_guest=False)
def get_concept(external_id: str, version: str = "default"):
	"""
	Retrieve full concept details by CIEL external ID.
	"""
	version_name = _resolve_version(version)
	if not version_name:
		return {"error": _("No default CIEL terminology version is available.")}

	concept_name = frappe.db.get_value(
		"CIEL Concept",
		{"external_id": external_id, "terminology_version": version_name},
		"name",
	)
	if not concept_name:
		frappe.throw(
			_("Concept {0} not found in version {1}.").format(external_id, version), frappe.DoesNotExistError
		)

	doc = frappe.get_doc("CIEL Concept", concept_name)
	tag = _version_tag(version_name)
	return {
		"version_tag": tag,
		"concept": doc.as_dict(),
	}


@frappe.whitelist(allow_guest=False)
def validate_code(system: str = "CIEL", code: str = "", version: str = "default"):
	"""
	Validate whether a code exists (and is not retired) in the given system.

	Returns ``{"valid": true/false, "retired": true/false, "version_tag": "..."}``
	"""
	if system.upper() != "CIEL":
		return {"valid": False, "retired": False, "error": _("Only CIEL system is supported.")}

	version_name = _resolve_version(version)
	if not version_name:
		return {
			"valid": False,
			"retired": False,
			"error": _("No default CIEL terminology version is available."),
		}

	result = frappe.db.get_value(
		"CIEL Concept",
		{"external_id": code, "terminology_version": version_name},
		["name", "retired"],
		as_dict=True,
	)
	tag = _version_tag(version_name)
	if not result:
		return {"valid": False, "retired": False, "version_tag": tag}
	return {
		"valid": True,
		"retired": bool(result.retired),
		"version_tag": tag,
	}


@frappe.whitelist(allow_guest=False)
def get_mappings(target_system: str = "", code: str = "", version: str = "default"):
	"""
	Retrieve CIEL concepts that have a mapping to the given target system + code.

	Returns a list of CIEL concepts (with their full mapping rows filtered to
	the requested target system/code).
	"""
	version_name = _resolve_version(version)
	if not version_name:
		return {"error": _("No default CIEL terminology version is available."), "results": []}

	ConceptMapping = frappe.qb.DocType("CIEL Concept Mapping")
	Concept = frappe.qb.DocType("CIEL Concept")

	query = (
		frappe.qb.from_(ConceptMapping)
		.join(Concept)
		.on(ConceptMapping.parent == Concept.name)
		.select(
			Concept.external_id,
			Concept.concept_class,
			Concept.retired,
			ConceptMapping.map_type,
			ConceptMapping.target_system,
			ConceptMapping.target_code,
			ConceptMapping.target_display,
		)
		.where(Concept.terminology_version == version_name)
	)

	if target_system:
		query = query.where(
			ConceptMapping.target_system.like(f"%{frappe.db.escape(target_system, percent=False)}%")
		)
	if code:
		query = query.where(ConceptMapping.target_code == code)

	rows = query.limit(200).run(as_dict=True)
	tag = _version_tag(version_name)
	return {"version_tag": tag, "results": rows}


# ---------------------------------------------------------------------------
# FHIR terminology facade stubs (phase 2)
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=False)
def fhir_lookup(system: str = "", code: str = "", version: str = "default"):
	"""
	FHIR ``CodeSystem/$lookup`` stub.

	Performs a concept lookup by system URI + code and returns a minimal
	FHIR Parameters resource backed by local CIEL data.
	"""
	CIEL_URI = "http://openconceptlab.org/orgs/CIEL/sources/CIEL/"
	if system != CIEL_URI and system.upper() != "CIEL":
		return _fhir_error(f"Unsupported system: {system}")

	version_name = _resolve_version(version)
	if not version_name:
		return _fhir_error("No default CIEL terminology version is available.")

	result = frappe.db.get_value(
		"CIEL Concept",
		{"external_id": code, "terminology_version": version_name},
		["name", "retired", "concept_class", "datatype"],
		as_dict=True,
	)
	if not result:
		return _fhir_error(f"Unknown code: {code}")

	doc = frappe.get_doc("CIEL Concept", result.name)
	display = next(
		(n.name_text for n in doc.names if n.preferred and not n.voided),
		code,
	)
	tag = _version_tag(version_name)

	return {
		"resourceType": "Parameters",
		"parameter": [
			{"name": "name", "valueString": "CIEL"},
			{"name": "version", "valueString": tag},
			{"name": "display", "valueString": display},
			{"name": "inactive", "valueBoolean": bool(result.retired)},
		],
	}


@frappe.whitelist(allow_guest=False, methods=["POST"])
def fhir_validate_code():
	"""
	FHIR ``ValueSet/$validate-code`` stub.

	Accepts a FHIR Parameters body (JSON) and returns a Parameters resource
	with a ``result`` boolean.
	"""
	body = frappe.local.form_dict
	system = body.get("system", "")
	code = body.get("code", "")
	version = body.get("version", "default")

	validation = validate_code(system=system, code=code, version=version)
	valid = validation.get("valid", False)
	retired = validation.get("retired", False)

	params = [{"name": "result", "valueBoolean": valid and not retired}]
	if not valid:
		params.append({"name": "message", "valueString": f"Code {code!r} not found in {system}."})
	elif retired:
		params.append({"name": "message", "valueString": f"Code {code!r} is retired."})

	return {"resourceType": "Parameters", "parameter": params}


@frappe.whitelist(allow_guest=False)
def fhir_expand(url: str = "", version: str = "default", filter: str = "", count: int = 50):
	"""
	FHIR ``ValueSet/$expand`` stub.

	Returns a minimal ValueSet resource containing active CIEL concepts
	matching the optional *filter* text.  When *url* refers to a specific
	concept class (e.g. ``...?url=Diagnosis``), the results are filtered to
	that class.
	"""
	version_name = _resolve_version(version)
	if not version_name:
		return _fhir_error("No default CIEL terminology version is available.")

	tag = _version_tag(version_name)
	count = min(int(count), 500)

	Concept = frappe.qb.DocType("CIEL Concept")
	ConceptName = frappe.qb.DocType("CIEL Concept Name")

	query = (
		frappe.qb.from_(Concept)
		.join(ConceptName)
		.on(ConceptName.parent == Concept.name)
		.select(Concept.external_id, Concept.concept_class, ConceptName.name_text)
		.where(Concept.terminology_version == version_name)
		.where(Concept.retired == 0)
		.where(ConceptName.preferred == 1)
		.where(ConceptName.voided == 0)
	)

	if filter:
		query = query.where(ConceptName.name_text.like(f"%{frappe.db.escape(filter, percent=False)}%"))

	# Use url as a concept_class filter when it looks like a plain class name
	if url and "/" not in url:
		query = query.where(Concept.concept_class == url)

	rows = query.limit(count).run(as_dict=True)

	contains = [
		{
			"system": "http://openconceptlab.org/orgs/CIEL/sources/CIEL/",
			"version": tag,
			"code": r.external_id,
			"display": r.name_text,
		}
		for r in rows
	]

	return {
		"resourceType": "ValueSet",
		"expansion": {
			"identifier": f"urn:uuid:ciel-{tag}",
			"timestamp": frappe.utils.now(),
			"total": len(contains),
			"contains": contains,
		},
	}


def _fhir_error(message: str) -> dict:
	return {
		"resourceType": "OperationOutcome",
		"issue": [{"severity": "error", "code": "not-found", "diagnostics": message}],
	}
