# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.1.0] - 2026-06-22

### Added

- **FHIR R4 integration API** — four whitelisted endpoints that expose Frappe Healthcare
  clinical data as FHIR R4 conformant resources, suitable for direct consumption by
  FHIR-aware systems such as dcm4chee-arc-light:
  - `get_patient_for_fhir` — returns FHIR R4 Patient with `name[]`, `telecom[]`,
    `gender` (FHIR value set), `birthDate`, and `active` mapping
  - `get_service_request_for_fhir` — returns FHIR R4 ServiceRequest with accession
    number identifier, Code Value link resolution for `status`/`intent`/`priority`,
    FHIR coding array from `codification_table`, and optional encounter reference
  - `get_observation_for_fhir` — returns FHIR R4 Observation with full polymorphic
    result dispatch across all 11 Frappe `permitted_data_type` values (Boolean, Text,
    Select, Quantity, Numeric, Range, Ratio, Time, DateTime, Period, Attach)
  - `get_imaging_study_by_service_request` — returns a stored FHIR ImagingStudy
    JSON from a File attachment on the ServiceRequest (populated by future dcm4chee bridge)
- **78-test coverage suite** (`test_fhir_integration.py`) covering all endpoints,
  all result type branches, nil-path handling, Code Value link resolution,
  duplicate-prevention logic, and TOCTOU guard in imaging study fetch

### Fixed

- `result_boolean` field dispatched on value-presence (`is not None`) — broken because
  Frappe stores boolean as a `Select` field with default `""`. Fixed to dispatch on
  `permitted_data_type == "Boolean"` and coerce to string before `.lower()` comparison
  to handle both string and integer stored values
- Zero observation values (`result_float = 0.0`) were silently dropped by Python `or`
  short-circuit evaluation. Fixed to use `is not None` guard
- Patient references with blank `doc.patient` produced FHIR `"Patient/None"` references
  consumed silently by downstream systems. Now throws explicitly
- TOCTOU race in imaging study File fetch: `get_doc` with `file_url` filter could return
  a different file if the URL is shared. Fixed to include `name` in `get_all` fields and
  fetch by document name
- FHIR `Coding.display` was emitted as JSON `null` when absent. Now omitted entirely
  to satisfy FHIR validators

### Changed

- `get_imaging_study_for_fhir(name)` renamed to `get_imaging_study_by_service_request(sr_name)`
  to accurately reflect that ImagingStudy is addressed via its source ServiceRequest, not a
  stable FHIR resource ID
- Endpoint responses are now fully FHIR R4 conformant — `resourceType`, `name[]`,
  `subject.reference`, `code.coding[]` — replacing Frappe-shaped custom dicts
- `status`/`intent`/`priority` on ServiceRequest and Observation are resolved through
  `_get_code_value()` — a helper that looks up the FHIR code string from the linked
  Code Value document, rather than returning the Frappe document name
- README updated: payloads described as FHIR R4 conformant resources; imaging study
  endpoint marked as coming soon with dcm4chee integration prerequisites documented
