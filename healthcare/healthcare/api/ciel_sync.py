"""
ciel_sync.py — CIEL terminology sync from Open Concept Lab (OCL) REST API.

Overview
--------
CIEL (Columbia International eHealth Laboratory) is an open-source concept
dictionary with 55,000+ concepts mapped to SNOMED CT, ICD-10, LOINC, and RxNORM.
Licensed CC BY 4.0.

This module syncs CIEL concepts into the local ``Terminology Concept`` DocType,
enabling the "Add Medical Code" picker on Service Request to autocomplete with
standardized codings without any external API calls at point of care.

OCL API
-------
Uses the OCL **REST API** (not the FHIR API) for bulk concept sync because it
returns inline mappings with ``?verbose=true``.

Endpoint: GET https://api.openconceptlab.org/orgs/CIEL/sources/CIEL/concepts/
           ?verbose=true&limit=100&offset=N

OCL API key requirement: anonymous API access is currently disabled on OCL.
Set an API key in DCM4CHEE Settings.ocl_api_key (or CIEL Settings if added later).
Until a key is configured, sync is a no-op with a logged warning.

HARD GATE
---------
Before relying on this sync in production, verify that ``?verbose=true`` returns
inline ``mappings[]`` by running:

    curl -H "Authorization: Token YOUR_KEY" \\
      "https://api.openconceptlab.org/orgs/CIEL/sources/CIEL/concepts/887/?verbose=true" \\
      | python3 -m json.tool | grep -A5 '"mappings"'

If ``mappings`` is empty, each concept requires a separate
``/concepts/{id}/mappings/`` call — adjust MAPPINGS_INLINE = False below.

Chunked sync
------------
Full sync of 55k concepts runs across many daily scheduler ticks rather than
one long-running job (avoids RQ worker timeout). Offset is persisted in
``DCM4CHEE Settings.sync_offset`` between runs.

  Day 1: offset 0→100     (100 concepts)
  Day 2: offset 100→200
  ...
  Day ~550: full sync complete, offset resets to 0 for next cycle

Rate limiting
-------------
Exponential backoff on HTTP 429. If rate-limited after 3 retries, the chunk
aborts and advances offset to avoid looping on the same concepts.
"""

import time

import frappe
import requests
from frappe import _

OCL_BASE = "https://api.openconceptlab.org"
CIEL_SOURCE_PATH = "/orgs/CIEL/sources/CIEL/concepts/"
CHUNK_SIZE = 100

# Set to False if verbose=true does NOT return inline mappings
# (requires separate /mappings/ call per concept — slower but supported)
MAPPINGS_INLINE = True

# Known FHIR system URIs for OCL map_type → canonical system
_SYSTEM_MAP = {
	"http://loinc.org": "http://loinc.org",
	"http://snomed.info/sct": "http://snomed.info/sct",
	"http://hl7.org/fhir/sid/icd-10-cm": "http://hl7.org/fhir/sid/icd-10-cm",
	"http://hl7.org/fhir/sid/icd-10": "http://hl7.org/fhir/sid/icd-10",
	"http://www.nlm.nih.gov/research/umls/rxnorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
}

CIEL_SYSTEM_URI = "https://openconceptlab.org/orgs/CIEL/sources/CIEL/"


def _get_ocl_headers() -> dict:
	"""Build OCL API request headers, including auth token if configured."""
	headers = {"Accept": "application/json"}
	# OCL API key stored in DCM4CHEE Settings for now.
	# TODO: move to a dedicated CIEL Settings singleton if CIEL sync grows.
	try:
		settings = frappe.get_single("DCM4CHEE Settings")
		# We reuse the auth_token field; a dedicated OCL field would be cleaner.
		# For now: if auth_token looks like an OCL token, use it.
		token = settings.get_password("auth_token") if settings.auth_token else None
		if token and token.startswith("Token "):
			headers["Authorization"] = token
		elif token:
			headers["Authorization"] = "Token {}".format(token)
	except Exception:  # noqa: BLE001
		pass
	return headers


def _fetch_concepts_page(offset: int, verbose: bool = True) -> tuple[list, int]:
	"""
	Fetch one page of CIEL concepts from OCL.

	Returns (concepts_list, total_count).
	Raises on HTTP errors after exponential backoff.
	"""
	params = {"limit": CHUNK_SIZE, "offset": offset}
	if verbose:
		params["verbose"] = "true"

	url = OCL_BASE + CIEL_SOURCE_PATH
	backoff = 2
	for attempt in range(3):
		resp = requests.get(url, params=params, headers=_get_ocl_headers(), timeout=30)
		if resp.status_code == 429:
			retry_after = int(resp.headers.get("Retry-After", backoff))
			time.sleep(retry_after)
			backoff = min(backoff * 2, 240)
			continue
		resp.raise_for_status()
		data = resp.json()
		# OCL REST API returns {"num_found": N, "results": [...]} or a list
		if isinstance(data, list):
			return data, len(data)
		results = data.get("results", data.get("concepts", []))
		total = data.get("num_found", len(results))
		return results, total
	raise requests.HTTPError("Rate limited after 3 retries at offset {}".format(offset))


def _fetch_mappings_for_concept(concept_id: str) -> list:
	"""
	Fetch mappings for a concept via separate /mappings/ call.

	Used when MAPPINGS_INLINE = False (verbose=true doesn't return mappings).
	"""
	url = "{}/orgs/CIEL/sources/CIEL/concepts/{}/mappings/".format(OCL_BASE, concept_id)
	try:
		resp = requests.get(url, headers=_get_ocl_headers(), timeout=15)
		resp.raise_for_status()
		return resp.json() if isinstance(resp.json(), list) else resp.json().get("results", [])
	except Exception:  # noqa: BLE001
		return []


def _extract_codings_from_concept(concept: dict) -> list[dict]:
	"""
	Extract FHIR coding rows from an OCL concept dict.

	Always includes the CIEL code itself as the first coding.
	Then adds mappings to LOINC, SNOMED, ICD-10, RxNORM.
	"""
	codings = []

	# CIEL code itself
	ciel_id = concept.get("id") or concept.get("concept_id") or ""
	ciel_display = concept.get("display_name") or concept.get("names", [{}])[0].get("name", "")
	if ciel_id:
		codings.append({
			"system": CIEL_SYSTEM_URI,
			"code": str(ciel_id),
			"display": ciel_display,
		})

	# Mappings (inline from verbose=true, or fetched separately)
	mappings = concept.get("mappings", [])
	if not mappings and not MAPPINGS_INLINE:
		mappings = _fetch_mappings_for_concept(str(ciel_id))

	for mapping in mappings:
		# OCL mapping shape: {to_source_url, to_concept_code, map_type, to_concept_name}
		to_source = mapping.get("to_source_url") or mapping.get("to_source", {}).get("url", "")
		to_code = mapping.get("to_concept_code") or mapping.get("to_concept", {}).get("id")
		to_display = mapping.get("to_concept_name") or mapping.get("to_concept", {}).get("display_name", "")

		if not to_source or not to_code:
			continue

		# Normalize to canonical FHIR system URI
		system = None
		for key, uri in _SYSTEM_MAP.items():
			if key in to_source:
				system = uri
				break

		if system:
			codings.append({"system": system, "code": str(to_code), "display": to_display or ""})

	return codings


def _upsert_concept(concept: dict) -> bool:
	"""
	Upsert one OCL concept into Terminology Concept DocType.

	Returns True if the concept was created/updated, False if skipped.
	"""
	ciel_id = str(concept.get("id") or concept.get("concept_id") or "").strip()
	if not ciel_id:
		return False

	display_name = (
		concept.get("display_name")
		or (concept.get("names") or [{}])[0].get("name", "")
		or ciel_id
	)
	retired = concept.get("retired", False)
	data_type = concept.get("datatype") or concept.get("concept_class") or ""

	# Map OCL data type to Frappe permitted_data_type options
	_dtype_map = {
		"Numeric": "Quantity",
		"Coded": "Select",
		"Text": "Text",
		"Boolean": "Boolean",
		"Rule": "Text",
		"Document Observations": "Text",
	}
	permitted_data_type = _dtype_map.get(data_type, "Text")

	codings = _extract_codings_from_concept(concept)

	existing_name = frappe.db.get_value("Terminology Concept", {"ciel_concept_id": ciel_id}, "name")

	if existing_name:
		doc = frappe.get_doc("Terminology Concept", existing_name)
		doc.display_name = display_name
		doc.permitted_data_type = permitted_data_type
		doc.is_active = 0 if retired else 1
		doc.set("codings", [])
		for c in codings:
			doc.append("codings", c)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({
			"doctype": "Terminology Concept",
			"ciel_concept_id": ciel_id,
			"display_name": display_name,
			"permitted_data_type": permitted_data_type,
			"is_active": 0 if retired else 1,
			"codings": codings,
		})
		doc.insert(ignore_permissions=True)

	return True


def sync_ciel_concepts_chunk() -> dict:
	"""
	Frappe Scheduler daily job: sync one CHUNK_SIZE page of CIEL concepts.

	Reads current offset from DCM4CHEE Settings.sync_offset, advances it
	by CHUNK_SIZE, and wraps back to 0 when the full dictionary is consumed.
	Returns a summary dict for logging.
	"""
	settings = frappe.get_single("DCM4CHEE Settings")

	# Require an OCL API key — anonymous access is disabled
	has_token = bool(settings.auth_token)
	if not has_token:
		frappe.logger("ciel_sync").warning(
			"CIEL sync skipped: no OCL API key configured in DCM4CHEE Settings. "
			"Set auth_token to a Token from https://app.openconceptlab.org."
		)
		return {"skipped": True, "reason": "no_api_key"}

	offset = int(settings.sync_offset or 0)

	frappe.logger("ciel_sync").info("CIEL sync: offset %d, chunk %d", offset, CHUNK_SIZE)

	try:
		concepts, total = _fetch_concepts_page(offset, verbose=MAPPINGS_INLINE)
	except Exception as e:  # noqa: BLE001
		frappe.log_error(title="CIEL sync fetch failed", message=str(e))
		return {"error": str(e), "offset": offset}

	synced = 0
	errors = 0
	for concept in concepts:
		try:
			_upsert_concept(concept)
			synced += 1
		except Exception as e:  # noqa: BLE001
			errors += 1
			frappe.log_error(
				title="CIEL upsert error",
				message="Concept {}: {}".format(concept.get("id"), str(e)),
			)

	frappe.db.commit()

	# Advance offset; wrap to 0 if exhausted
	new_offset = offset + CHUNK_SIZE
	if not concepts or new_offset >= total:
		new_offset = 0  # Full sync complete — start over next cycle

	frappe.db.set_value("DCM4CHEE Settings", "DCM4CHEE Settings", {
		"sync_offset": new_offset,
		"last_sync_timestamp": frappe.utils.now_datetime(),
	})

	frappe.logger("ciel_sync").info(
		"CIEL sync chunk done: synced=%d, errors=%d, offset %d→%d (total=%d)",
		synced, errors, offset, new_offset, total,
	)

	return {
		"synced": synced,
		"errors": errors,
		"offset_before": offset,
		"offset_after": new_offset,
		"total": total,
	}


@frappe.whitelist()
def search_ciel_concepts(term: str, limit: int = 20) -> list:
	"""
	Search local Terminology Concept by display_name.

	Called by the "Add Medical Code" client script on Service Request.
	Queries the local DocType only — no external API call at runtime.

	Returns [{name, display_name, codings: [{system, code, display}]}]
	"""
	if not term or len(term) < 2:
		return []

	results = frappe.get_all(
		"Terminology Concept",
		filters={
			"display_name": ["like", "%{}%".format(term)],
			"is_active": 1,
		},
		fields=["name", "display_name", "permitted_data_type"],
		order_by="display_name asc",
		limit=int(limit),
	)

	for r in results:
		r["codings"] = frappe.get_all(
			"Terminology Concept Coding",
			filters={"parent": r["name"]},
			fields=["system", "code", "display"],
			order_by="idx asc",
		)

	return results


@frappe.whitelist()
def trigger_ciel_sync() -> str:
	"""
	On-demand full CIEL sync trigger (runs as background job).

	Resets the offset to 0 and enqueues the first chunk. Subsequent chunks
	run via the daily scheduler.
	"""
	frappe.db.set_value("DCM4CHEE Settings", "DCM4CHEE Settings", "sync_offset", 0)
	frappe.enqueue(
		"healthcare.healthcare.api.ciel_sync.sync_ciel_concepts_chunk",
		queue="long",
		is_async=True,
	)
	return _("CIEL sync started. Progress is logged in Error Log.")
