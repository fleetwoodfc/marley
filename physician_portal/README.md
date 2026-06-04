# Physician Portal

A Vue 3 + Vite-based portal for physicians, modeled after the patient portal. Includes tabs for Orders (FHIR ServiceRequest) and Patients (search, registration, management).

## Development

```sh
cd physician_portal
npm install
npm run dev
```

## Structure
- `src/PhysicianPortal.vue`: Main entry
- `src/components/OrderModel.vue`: Orders tab (FHIR ServiceRequest)
- `src/components/PatientModel.vue`: Patients tab
