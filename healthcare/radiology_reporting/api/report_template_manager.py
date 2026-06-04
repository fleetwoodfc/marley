"""
Report Template Manager API
Whitelisted methods for MRRT-compatible template governance and retrieval.
"""

import base64
import hashlib
import io
import re
import zipfile
from xml.etree import ElementTree as ET

import frappe
from frappe import _
from frappe.utils import now_datetime

_logger = frappe.logger("report_template_manager", with_more_info=False)


# ---------------------------------------------------------------------------
# Helpers – lifecycle transitions
# ---------------------------------------------------------------------------

_LIFECYCLE_EVENT_MAP = {
	"Review Ready": "Submitted",
	"Draft": "Rejected",
	"Approved": "Approved",
	"Published": "Published",
	"Superseded": "Superseded",
	"Retired": "Retired",
}


def _transition_version(version_name: str, to_status: str, notes: str = "") -> "Document":
	"""Load a version, apply a lifecycle transition, record a governance event, and save."""
	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	from_status = doc.lifecycle_status

	event_type = _LIFECYCLE_EVENT_MAP.get(to_status, to_status)
	doc.append_governance_event(event_type, from_status, to_status, notes)

	doc.lifecycle_status = to_status
	if to_status == "Published" and not doc.effective_from:
		doc.effective_from = now_datetime()
	elif to_status in ("Superseded", "Retired") and not doc.effective_to:
		doc.effective_to = now_datetime()

	doc.save()
	return doc


def _require_role(*roles: str):
	"""Raise PermissionError if the current user does not hold at least one of the given roles."""
	user_roles = frappe.get_roles()
	if not any(r in user_roles for r in roles):
		frappe.throw(
			_("You do not have permission to perform this action. Required role(s): {0}.").format(
				", ".join(roles)
			),
			frappe.PermissionError,
		)


# ---------------------------------------------------------------------------
# US1 – T015: Create Template
# ---------------------------------------------------------------------------

@frappe.whitelist()
def create_template(
	template_code: str,
	title: str,
	description: str = "",
	default_modality: str = "",
	default_body_part: str = "",
	default_language: str = "en",
	authoring_organization: str = "",
	specialty: str = "Radiology",
):
	"""POST /templates — Create a new managed Radiology Report Template definition."""
	_require_role("Radiology Template Author", "System Manager")

	doc = frappe.new_doc("Radiology Report Template")
	doc.template_code = template_code
	doc.title = title
	doc.description = description
	doc.default_modality = default_modality
	doc.default_body_part = default_body_part
	doc.default_language = default_language
	doc.authoring_organization = authoring_organization
	doc.specialty = specialty
	doc.status = "Active"
	doc.insert()

	return {"name": doc.name, "template_code": doc.template_code, "title": doc.title}


# ---------------------------------------------------------------------------
# US1 – T016: Create Version
# ---------------------------------------------------------------------------

@frappe.whitelist()
def create_version(
	report_template: str,
	version_label: str,
	mrrt_title: str = "",
	mrrt_html: str = "",
	language: str = "en",
	locale: str = "",
	replaces_version: str = "",
):
	"""POST /templates/{templateId}/versions — Create a new Draft version for a template."""
	_require_role("Radiology Template Author", "System Manager")

	frappe.has_permission("Radiology Report Template Version", ptype="create", throw=True)

	doc = frappe.new_doc("Radiology Report Template Version")
	doc.report_template = report_template
	doc.version_label = version_label
	doc.mrrt_title = mrrt_title
	doc.mrrt_html = mrrt_html
	doc.language = language
	doc.locale = locale
	doc.replaces_version = replaces_version
	doc.lifecycle_status = "Draft"
	doc.validation_status = "Not Run"
	doc.insert()

	# Record a Created governance event
	doc.append_governance_event("Created", "", "Draft", "Version created")
	doc.save()

	return {"name": doc.name, "version_label": doc.version_label, "lifecycle_status": doc.lifecycle_status}


# ---------------------------------------------------------------------------
# US1 – T017/T018: Validate Version
# ---------------------------------------------------------------------------

def _run_mrrt_validation(mrrt_html: str) -> list[dict]:
	"""Run structural MRRT validation rules against the template HTML content.

	Returns a list of finding dicts with keys: severity, rule_code, message, location_hint, blocking.
	"""
	findings = []

	if not (mrrt_html or "").strip():
		findings.append({
			"severity": "Error",
			"rule_code": "MRRT-001",
			"message": "Template content (mrrt_html) is empty.",
			"location_hint": "mrrt_html",
			"blocking": 1,
		})
		return findings

	# Rule MRRT-002: must contain a <html> root element
	html_lower = mrrt_html.lower()
	if "<html" not in html_lower:
		findings.append({
			"severity": "Error",
			"rule_code": "MRRT-002",
			"message": "Template must contain a root <html> element.",
			"location_hint": "mrrt_html",
			"blocking": 1,
		})

	# Rule MRRT-003: must contain a <head> section
	if "<head" not in html_lower:
		findings.append({
			"severity": "Error",
			"rule_code": "MRRT-003",
			"message": "Template must contain a <head> element.",
			"location_hint": "mrrt_html",
			"blocking": 1,
		})

	# Rule MRRT-004: must contain a <body> section
	if "<body" not in html_lower:
		findings.append({
			"severity": "Error",
			"rule_code": "MRRT-004",
			"message": "Template must contain a <body> element.",
			"location_hint": "mrrt_html",
			"blocking": 1,
		})

	# Rule MRRT-005: body MUST contain at least one <section> element (IHE MRRT conformance gate, SC-002)
	if "<section" not in html_lower:
		findings.append({
			"severity": "Error",
			"rule_code": "MRRT-005",
			"message": "Template body must contain at least one <section> element (IHE MRRT conformance requirement). Template cannot be approved until this is resolved.",
			"location_hint": "body",
			"blocking": 1,
		})

	# Rule MRRT-006: title should be present in <head><title>
	if "<title" not in html_lower:
		findings.append({
			"severity": "Warning",
			"rule_code": "MRRT-006",
			"message": "Template <head> should contain a <title> element.",
			"location_hint": "head",
			"blocking": 0,
		})

	# Rule MRRT-007: required dcterms meta fields must be present and non-empty (FR-004, SC-002)
	# IHE MRRT conformance gate — all four are mandatory
	required_dcterms = [
		("dcterms.title", "dcterms:title"),
		("dcterms.identifier", "dcterms:identifier"),
		("dcterms.type", "dcterms:type"),
		("dcterms.language", "dcterms:language"),
	]
	for attr_name, display_name in required_dcterms:
		# Match both name="dcterms.xxx" and name="dcterms:xxx" forms
		attr_dotted = f'name="{attr_name}"'
		attr_colon = f'name="{attr_name.replace(".", ":")}"'
		if attr_dotted not in html_lower and attr_colon not in html_lower:
			findings.append({
				"severity": "Error",
				"rule_code": "MRRT-007",
				"message": f"Required IHE MRRT meta field '{display_name}' is missing. Template cannot be approved until this is resolved.",
				"location_hint": "head/meta",
				"blocking": 1,
			})

	# Rule MRRT-008: relative href/src links must not be broken (FR-004, SC-002)
	# Any relative path (not starting with http/https/#/data:) is flagged as a Warning
	import re as _re
	_relative_link_pattern = _re.compile(
		r'(?:href|src)\s*=\s*["\']([^"\'#][^"\']*)["\']',
		_re.IGNORECASE,
	)
	for match in _relative_link_pattern.finditer(mrrt_html or ""):
		value = match.group(1).strip()
		if not _re.match(r'^(?:https?://|data:|#)', value, _re.IGNORECASE):
			findings.append({
				"severity": "Warning",
				"rule_code": "MRRT-008",
				"message": f"Relative link '{value}' may be broken when the template is used outside its original context. Use absolute URLs, data URIs, or anchor references.",
				"location_hint": match.group(0)[:60],
				"blocking": 0,
			})

	return findings


@frappe.whitelist()
def validate_version(version_name: str):
	"""POST /versions/{versionId}/validate — Run validation rules and persist findings."""
	_require_role("Radiology Template Author", "Radiology Template Approver", "System Manager")

	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	frappe.has_permission(doc, ptype="write", throw=True)

	findings = _run_mrrt_validation(doc.mrrt_html)

	# Clear existing findings and persist new ones
	doc.validation_findings = []
	for f in findings:
		doc.append("validation_findings", f)

	# Determine overall validation status
	has_blocking = any(f["blocking"] for f in findings)
	has_errors = any(f["severity"] == "Error" for f in findings)
	has_warnings = any(f["severity"] == "Warning" for f in findings)

	if has_blocking or has_errors:
		doc.validation_status = "Failed"
	elif has_warnings:
		doc.validation_status = "Warnings"
	else:
		doc.validation_status = "Passed"

	error_count = sum(1 for f in findings if f["severity"] == "Error")
	warning_count = sum(1 for f in findings if f["severity"] == "Warning")
	doc.validation_summary = f"{error_count} error(s), {warning_count} warning(s)"

	doc.save()

	return {
		"version": version_name,
		"validation_status": doc.validation_status,
		"validation_summary": doc.validation_summary,
		"findings": findings,
	}


# ---------------------------------------------------------------------------
# US1 – T019: Submit for Review
# ---------------------------------------------------------------------------

@frappe.whitelist()
def submit_for_review(version_name: str, notes: str = ""):
	"""POST /versions/{versionId}/submit-review — Move Draft → Review Ready."""
	_require_role("Radiology Template Author", "System Manager")

	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	if doc.lifecycle_status != "Draft":
		frappe.throw(
			_("Only Draft versions can be submitted for review. Current status: {0}.").format(
				frappe.bold(doc.lifecycle_status)
			)
		)

	# Record who submitted so the 4-eyes approval rule can be enforced (FR-012)
	if not doc.submitted_by:
		doc.db_set("submitted_by", frappe.session.user, update_modified=False)

	_logger.info("submit_for_review | version=%s | actor=%s", version_name, frappe.session.user)
	doc = _transition_version(version_name, "Review Ready", notes or "Submitted for review")
	return {"name": doc.name, "lifecycle_status": doc.lifecycle_status}


# ---------------------------------------------------------------------------
# US1 – T020: Approve
# ---------------------------------------------------------------------------

@frappe.whitelist()
def approve_version(version_name: str, notes: str = ""):
	"""POST /versions/{versionId}/approve — Move Review Ready → Approved."""
	_require_role("Radiology Template Approver", "System Manager")

	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	if doc.lifecycle_status != "Review Ready":
		frappe.throw(
			_("Only Review Ready versions can be approved. Current status: {0}.").format(
				frappe.bold(doc.lifecycle_status)
			)
		)

	if doc.validation_status not in ("Passed", "Warnings"):
		frappe.throw(
			_("Version must pass validation before approval. Current validation status: {0}.").format(
				frappe.bold(doc.validation_status)
			)
		)

	# 4-eyes rule: submitter cannot approve their own submission (FR-012)
	# System Manager is exempt
	if (
		doc.submitted_by
		and doc.submitted_by == frappe.session.user
		and not frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "System Manager"})
	):
		frappe.throw(
			_("You cannot approve a version that you submitted for review (4-eyes rule). "
			  "Please ask a different approver to review this version.")
		)

	_logger.info("approve_version | version=%s | actor=%s | submitted_by=%s", version_name, frappe.session.user, doc.submitted_by)
	doc = _transition_version(version_name, "Approved", notes or "Approved by reviewer")
	return {"name": doc.name, "lifecycle_status": doc.lifecycle_status}


# ---------------------------------------------------------------------------
# US1 – T021: Publish
# ---------------------------------------------------------------------------

@frappe.whitelist()
def publish_version(version_name: str, notes: str = ""):
	"""POST /versions/{versionId}/publish — Move Approved → Published and update template pointer."""
	_require_role("Radiology Template Publisher", "System Manager")

	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	if doc.lifecycle_status != "Approved":
		frappe.throw(
			_("Only Approved versions can be published. Current status: {0}.").format(
				frappe.bold(doc.lifecycle_status)
			)
		)

	# Supersede any currently published version for the same template
	existing_published = frappe.db.get_value(
		"Radiology Report Template Version",
		{
			"report_template": doc.report_template,
			"lifecycle_status": "Published",
			"name": ("!=", version_name),
		},
		"name",
	)
	_logger.info("publish_version | version=%s | actor=%s | supersedes=%s", version_name, frappe.session.user, existing_published or "none")
	if existing_published:
		old_doc = _transition_version(existing_published, "Superseded", f"Superseded by {version_name}")
		# Cross-link replacement
		old_doc.reload()
		frappe.db.set_value(
			"Radiology Report Template Version", existing_published, "replacement_version", version_name
		)

	doc = _transition_version(version_name, "Published", notes or "Published")

	# Update the template's current_published_version pointer
	frappe.db.set_value(
		"Radiology Report Template", doc.report_template, "current_published_version", version_name
	)

	return {"name": doc.name, "lifecycle_status": doc.lifecycle_status, "effective_from": str(doc.effective_from)}


# ---------------------------------------------------------------------------
# US1 – T022: Retire
# ---------------------------------------------------------------------------

@frappe.whitelist()
def retire_version(version_name: str, notes: str = ""):
	"""POST /versions/{versionId}/retire — Move Published or Approved → Retired."""
	_require_role("Radiology Template Publisher", "System Manager")

	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	if doc.lifecycle_status not in ("Published", "Approved"):
		frappe.throw(
			_("Only Published or Approved versions can be retired. Current status: {0}.").format(
				frappe.bold(doc.lifecycle_status)
			)
		)

	doc = _transition_version(version_name, "Retired", notes or "Retired")
	_logger.info("retire_version | version=%s | actor=%s", version_name, frappe.session.user)
	current = frappe.db.get_value(
		"Radiology Report Template", doc.report_template, "current_published_version"
	)
	if current == version_name:
		frappe.db.set_value(
			"Radiology Report Template", doc.report_template, "current_published_version", None
		)

	return {"name": doc.name, "lifecycle_status": doc.lifecycle_status}


# ---------------------------------------------------------------------------
# US1 – Return to Draft (reject from review)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def return_to_draft(version_name: str, notes: str = ""):
	"""Move Review Ready → Draft (reviewer rejection)."""
	_require_role("Radiology Template Approver", "System Manager")

	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	if doc.lifecycle_status != "Review Ready":
		frappe.throw(
			_("Only Review Ready versions can be returned to Draft. Current status: {0}.").format(
				frappe.bold(doc.lifecycle_status)
			)
		)

	doc = _transition_version(version_name, "Draft", notes or "Returned to draft by reviewer")
	return {"name": doc.name, "lifecycle_status": doc.lifecycle_status}


# ===========================================================================
# US2 – Find and Use the Right Template
# ===========================================================================

# ---------------------------------------------------------------------------
# T025: List/search templates
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def list_templates(
	modality: str = "",
	body_part: str = "",
	language: str = "",
	status: str = "",
	q: str = "",
	limit: int = 50,
	offset: int = 0,
):
	"""GET /templates — Search and list managed report templates."""
	filters = {}
	if modality:
		filters["default_modality"] = ("like", f"%{modality}%")
	if body_part:
		filters["default_body_part"] = ("like", f"%{body_part}%")
	if status:
		filters["status"] = status
	else:
		filters["status"] = ("!=", "Archived")

	fields = [
		"name", "template_code", "title", "status", "default_modality",
		"default_body_part", "default_language", "current_published_version", "modified",
	]

	results = frappe.get_list(
		"Radiology Report Template",
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit_page_length=int(limit),
		limit_start=int(offset),
	)

	if q:
		q_lower = q.lower()
		results = [
			r for r in results
			if q_lower in (r.get("title") or "").lower()
			or q_lower in (r.get("template_code") or "").lower()
		]

	if language:
		# Filter to templates that have at least one version in the requested language
		results = [
			r for r in results
			if frappe.db.exists(
				"Radiology Report Template Version",
				{"report_template": r["name"], "language": language},
			)
		]

	return {"items": results, "total": len(results)}


# ---------------------------------------------------------------------------
# T026: Template detail
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def get_template(template_name: str):
	"""GET /templates/{templateId} — Template definition with current published version summary."""
	doc = frappe.get_doc("Radiology Report Template", template_name)
	frappe.has_permission(doc, ptype="read", throw=True)

	versions = frappe.get_list(
		"Radiology Report Template Version",
		filters={"report_template": template_name},
		fields=["name", "version_label", "lifecycle_status", "language", "effective_from", "validation_status"],
		order_by="creation desc",
		limit_page_length=20,
	)

	return {
		"name": doc.name,
		"template_code": doc.template_code,
		"title": doc.title,
		"description": doc.description,
		"status": doc.status,
		"specialty": doc.specialty,
		"default_modality": doc.default_modality,
		"default_body_part": doc.default_body_part,
		"default_language": doc.default_language,
		"authoring_organization": doc.authoring_organization,
		"current_published_version": doc.current_published_version,
		"versions": versions,
	}


# ---------------------------------------------------------------------------
# T027/T028: Resolve active template for a reporting context
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def resolve_template(
	modality: str = "",
	body_part: str = "",
	language: str = "",
	organization: str = "",
	radiology_procedure_template: str = "",
):
	"""GET /resolve — Find the best-matching published template version for a reporting context.

	Resolution order (most-specific first):
	  1. Procedure template + org + language + modality + body part
	  2. Org + language + modality + body part
	  3. Language + modality + body part
	  4. Modality + body part
	  5. Modality only
	  Falls back through each level of specificity until a match is found.
	"""
	matches = _find_best_assignment(
		modality=modality,
		body_part=body_part,
		language=language,
		organization=organization,
		radiology_procedure_template=radiology_procedure_template,
	)
	assignment = matches[0] if matches else None

	if not assignment:
		return {"resolved": False, "template": None, "version": None}

	version_doc = frappe.get_doc("Radiology Report Template Version", assignment.template_version)
	template_doc = frappe.get_doc("Radiology Report Template", assignment.report_template)

	return {
		"resolved": True,
		"template": {
			"name": template_doc.name,
			"template_code": template_doc.template_code,
			"title": template_doc.title,
		},
		"version": {
			"name": version_doc.name,
			"version_label": version_doc.version_label,
			"lifecycle_status": version_doc.lifecycle_status,
			"language": version_doc.language,
			"mrrt_title": version_doc.mrrt_title,
			"mrrt_html": version_doc.mrrt_html,
		},
		"assignment": assignment.name,
	}


@frappe.whitelist(allow_guest=False)
def resolve_template_candidates(
	modality: str = "",
	body_part: str = "",
	language: str = "",
	organization: str = "",
	radiology_procedure_template: str = "",
	limit: int = 5,
):
	"""GET /candidates — Return all published template candidates for a reporting context.

	Returns all tied candidates at the best (most-specific) matching scope level —
	never a mix of candidates from different scope levels. Ordered by priority asc.
	mrrt_html is excluded from the response payload to keep it lightweight.
	Used to populate the template selection dialog on the Worklist Item form.
	"""
	matches = _find_best_assignment(
		modality=modality,
		body_part=body_part,
		language=language,
		organization=organization,
		radiology_procedure_template=radiology_procedure_template,
		limit=int(limit),
	)

	if not matches:
		return {"resolved": False, "scope_level": None, "candidates": []}

	# Determine scope_level label from the first assignment
	first = matches[0]
	scope_label = _describe_scope(first, modality, body_part, language, organization, radiology_procedure_template)

	candidates = []
	for assignment in matches:
		version_doc = frappe.get_doc("Radiology Report Template Version", assignment.template_version)
		template_doc = frappe.get_doc("Radiology Report Template", assignment.report_template)
		candidates.append({
			"assignment": assignment.name,
			"priority": assignment.priority,
			"template": {
				"name": template_doc.name,
				"template_code": template_doc.template_code,
				"title": template_doc.title,
				"description": template_doc.description,
			},
			"version": {
				"name": version_doc.name,
				"version_label": version_doc.version_label,
				"lifecycle_status": version_doc.lifecycle_status,
				"language": version_doc.language,
				"mrrt_title": version_doc.mrrt_title,
			},
		})

	return {"resolved": True, "scope_level": scope_label, "candidates": candidates}


def _describe_scope(
	assignment,
	modality: str,
	body_part: str,
	language: str,
	organization: str,
	radiology_procedure_template: str,
) -> str:
	"""Return a human-readable scope label for the resolved assignment."""
	if radiology_procedure_template and assignment.radiology_procedure_template:
		return "procedure_template"
	if organization and assignment.organization:
		if language and assignment.language:
			return "org+language+modality+body_part"
		return "org+modality+body_part"
	if language and assignment.language:
		return "language+modality+body_part"
	if body_part and assignment.body_part:
		return "modality+body_part"
	return "modality"


def _find_best_assignment(
	modality: str,
	body_part: str,
	language: str,
	organization: str,
	radiology_procedure_template: str,
	limit: int = 1,
) -> "list":
	"""Resolve active assignments for the given context, falling back through scope levels.

	Returns a list of Assignment documents at the best (most-specific) scope level
	found, up to *limit* entries. Returns an empty list when nothing matches.
	Pass limit=1 (default) to preserve original single-match behaviour — caller
	takes result[0].
	"""
	base_filters = {
		"active": 1,
		"template_version": ("in", frappe.get_list(
			"Radiology Report Template Version",
			filters={"lifecycle_status": "Published"},
			pluck="name",
		)),
	}

	# Build scope levels from most-specific to most-general
	scope_levels = []

	if radiology_procedure_template:
		scope_levels.append({**base_filters, "radiology_procedure_template": radiology_procedure_template})

	if organization:
		scope_levels.append({**base_filters, "organization": organization, "modality": modality or "", "body_part": body_part or "", "language": language or ""})
		scope_levels.append({**base_filters, "organization": organization, "modality": modality or "", "body_part": body_part or ""})

	scope_levels.append({**base_filters, "modality": modality or "", "body_part": body_part or "", "language": language or ""})
	scope_levels.append({**base_filters, "modality": modality or "", "body_part": body_part or ""})
	if modality:
		scope_levels.append({**base_filters, "modality": modality})

	for scope_filter in scope_levels:
		matches = frappe.get_list(
			"Radiology Report Template Assignment",
			filters=scope_filter,
			fields=["name", "report_template", "template_version", "priority"],
			order_by="priority asc",
			limit_page_length=limit,
		)
		if matches:
			return [
				frappe.get_doc("Radiology Report Template Assignment", m["name"])
				for m in matches
			]

	return []


# ===========================================================================
# US3 – Manage Versioning, Distribution, and Retirement
# ===========================================================================

# ---------------------------------------------------------------------------
# T035: MRRT parse/extract helpers
# ---------------------------------------------------------------------------

def _extract_mrrt_html_from_zip(zip_bytes: bytes) -> tuple[str, str]:
	"""Extract MRRT HTML content and title from a ZIP-packaged MRRT file.

	Returns (mrrt_title, mrrt_html) tuple.
	"""
	with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
		html_names = [n for n in zf.namelist() if n.lower().endswith(".html") or n.lower().endswith(".htm")]
		if not html_names:
			frappe.throw(_("No HTML file found inside MRRT ZIP package."))
		html_content = zf.read(html_names[0]).decode("utf-8", errors="replace")
	return _parse_mrrt_title(html_content), html_content


def _parse_mrrt_title(html_content: str) -> str:
	"""Extract the <title> value from MRRT HTML, or return empty string."""
	match = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE)
	return match.group(1).strip() if match else ""


def _parse_mrrt_metadata(html_content: str) -> dict:
	"""Extract MRRT meta tags from HTML <head> as a dict."""
	meta = {}
	for m in re.finditer(r'<meta\s+name=["\']([^"\']+)["\']\s+content=["\']([^"\']*)["\']', html_content, re.IGNORECASE):
		meta[m.group(1).lower()] = m.group(2)
	return meta


# ---------------------------------------------------------------------------
# T033-ext: Extract MRRT package (for client-side file upload)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def extract_mrrt_package(file_content_b64: str, filename: str = ""):
	"""Decode a base64-encoded .mrrt (ZIP) or .html file and extract MRRT content.

	Called from the browser after the user selects a file. Returns extracted
	title, HTML content, and parsed metadata so the dialog can auto-populate
	before the user clicks Import.
	"""
	_require_role("Radiology Template Author", "System Manager")

	try:
		raw_bytes = base64.b64decode(file_content_b64)
	except Exception:
		frappe.throw(_("Could not decode file content. Ensure the file was uploaded correctly."))

	# Detect ZIP vs raw HTML by magic bytes
	is_zip = raw_bytes[:2] == b"PK"

	if is_zip:
		try:
			mrrt_title, mrrt_html = _extract_mrrt_html_from_zip(raw_bytes)
		except Exception as e:
			frappe.throw(_("Failed to extract MRRT content from ZIP: {0}").format(str(e)))
	else:
		mrrt_html = raw_bytes.decode("utf-8", errors="replace")
		mrrt_title = _parse_mrrt_title(mrrt_html)

	meta = _parse_mrrt_metadata(mrrt_html)

	return {
		"mrrt_title": mrrt_title or meta.get("dcterms.title", ""),
		"mrrt_html": mrrt_html,
		"language": meta.get("dcterms.language", meta.get("language", "en")),
		"meta": meta,
	}


# ---------------------------------------------------------------------------
# T033: MRRT import
# ---------------------------------------------------------------------------

@frappe.whitelist()
def import_mrrt(
	report_template: str,
	version_label: str,
	mrrt_content: str = "",
	language: str = "en",
	replaces_version: str = "",
	notes: str = "",
):
	"""POST /imports/mrrt — Import MRRT HTML content as a new Draft version.

	Accepts raw HTML string in mrrt_content. Creates a Draft version, runs
	import-time validation, and persists findings.
	"""
	_require_role("Radiology Template Author", "System Manager")
	frappe.has_permission("Radiology Report Template Version", ptype="create", throw=True)

	if not mrrt_content:
		frappe.throw(_("mrrt_content is required for MRRT import."))

	mrrt_title = _parse_mrrt_title(mrrt_content)
	meta = _parse_mrrt_metadata(mrrt_content)

	doc = frappe.new_doc("Radiology Report Template Version")
	doc.report_template = report_template
	doc.version_label = version_label
	doc.mrrt_title = mrrt_title or meta.get("title", "")
	doc.mrrt_html = mrrt_content
	doc.language = meta.get("language", language)
	doc.replaces_version = replaces_version
	doc.lifecycle_status = "Draft"
	doc.validation_status = "Not Run"
	doc.insert()

	# Record Imported governance event
	doc.append_governance_event("Imported", "", "Draft", notes or "Imported via MRRT import endpoint")
	doc.save()

	# Run T036 import-time validation and persist findings
	validation_result = validate_version(doc.name)

	return {
		"name": doc.name,
		"version_label": doc.version_label,
		"mrrt_title": doc.mrrt_title,
		"lifecycle_status": doc.lifecycle_status,
		"validation_status": validation_result["validation_status"],
		"validation_summary": validation_result["validation_summary"],
	}


# ---------------------------------------------------------------------------
# T034: MRRT export
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def export_mrrt(version_name: str):
	"""GET /versions/{versionId}/export — Export the exact MRRT HTML for a version.

	Records an Exported governance event without changing lifecycle status.
	"""
	doc = frappe.get_doc("Radiology Report Template Version", version_name)
	frappe.has_permission(doc, ptype="read", throw=True)

	if not doc.mrrt_html:
		frappe.throw(_("Version {0} has no MRRT content to export.").format(frappe.bold(version_name)))

	# Record Exported governance event
	doc.append_governance_event("Exported", doc.lifecycle_status, doc.lifecycle_status, "Exported via API")
	doc.save()

	return {
		"version": version_name,
		"version_label": doc.version_label,
		"lifecycle_status": doc.lifecycle_status,
		"mrrt_title": doc.mrrt_title,
		"mrrt_html": doc.mrrt_html,
		"checksum": doc.checksum,
		"language": doc.language,
		"effective_from": str(doc.effective_from) if doc.effective_from else None,
	}

