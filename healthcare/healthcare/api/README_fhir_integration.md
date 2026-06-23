# FHIR Integration API

This module exposes FHIR R4 conformant resources from Frappe Healthcare for integration
with external FHIR consumers (e.g. dcm4chee-arc-light for IHE Scheduled Workflow demos).

Responses conform to FHIR R4 resource shapes (`resourceType`, `name[]`, `subject.reference`,
`code.coding[]`, etc.) and are suitable for direct consumption by FHIR-aware systems.

## Endpoints

- `healthcare.healthcare.api.fhir_integration.get_patient_for_fhir` — FHIR R4 Patient
- `healthcare.healthcare.api.fhir_integration.get_service_request_for_fhir` — FHIR R4 ServiceRequest
- `healthcare.healthcare.api.fhir_integration.get_observation_for_fhir` — FHIR R4 Observation
- `healthcare.healthcare.api.fhir_integration.get_imaging_study_by_service_request` — FHIR R4 ImagingStudy *(coming soon — requires dcm4chee_bridge.py)*

## Example usage

```bash
curl "http://localhost:8000/api/method/healthcare.healthcare.api.fhir_integration.get_patient_for_fhir?name=PAT-0001"
```

## dcm4chee Integration Prerequisites

For the IHE SWF demo with dcm4chee-arc-light:

- **Minimum RAM:** 8 GB (Docker Desktop: allocate ≥ 6 GB)
- **Docker images required:** `dcm4che/dcm4chee-arc-psql`, MariaDB, Redis
- **Demo compose file:** `docker-compose.imaging-demo.yml` *(coming soon)*
- **OCL API gate (required before creating Terminology DocTypes):** Run the curl test in `ciel_sync.py` docstring to verify inline mappings are returned by the OCL REST API

**Verify dcm4chee FHIR adapter creates MWL from ServiceRequest before implementing the bridge:**
```bash
curl -X POST http://localhost:8080/fhir/r4/ServiceRequest \
  -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"ServiceRequest","status":"active","intent":"order","subject":{"reference":"Patient/PAT-0001"}}'
# Verify MWL item appears: findscu -M WorklistQuery -m 0008,0050=ACC-... localhost 11112
```
