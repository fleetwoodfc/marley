# FHIR Integration API

This module exposes normalized Marley payloads for an external FastAPI/HAPI FHIR integration layer.

## Endpoints

- `healthcare.healthcare.api.fhir_integration.get_patient_for_fhir`
- `healthcare.healthcare.api.fhir_integration.get_service_request_for_fhir`
- `healthcare.healthcare.api.fhir_integration.get_observation_for_fhir`

## Example usage

```bash
curl "http://localhost:8000/api/method/healthcare.healthcare.api.fhir_integration.get_patient_for_fhir?name=PAT-0001"
