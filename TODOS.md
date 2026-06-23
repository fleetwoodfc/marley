# TODOS

## FHIR Integration

### P2 — RBAC on FHIR endpoints

**What:** Add `frappe.has_permission()` role check to all four FHIR integration endpoints.

**Why:** All endpoints are currently accessible to any authenticated Frappe user with no
record-level permission check. A receptionist or patient portal user can enumerate patient
demographics, clinical orders, and lab results by iterating sequential document names
(PAT-0001, PAT-0002, etc.). This is OWASP A01 - Broken Access Control.

**Pros:** Blocks cross-patient data access; limits exposure to users with Healthcare roles.

**Cons:** Requires role design decision (which Frappe roles = FHIR read access); adds
1-2 DB calls per endpoint; could break integrations that run as system-level users.

**Context:** Deferred from feature/fhir-integration-api CEO review (2026-06-20) because
the integration is currently demo-scope with no patient portal users. Must be resolved
before any production deployment. Add `frappe.has_permission("Patient", "read", doc=doc)`
pattern (and equivalent per doctype) before returning data.

**Priority:** P2, human: ~2h / CC: ~10min

**Depends on:** Role design - which Frappe roles should have FHIR read access?

## Completed
