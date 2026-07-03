<div align="center">
<a href="https://frappehealth.com">
    <img src="https://raw.githubusercontent.com/frappe/healthcare/develop/healthcare/public/images/healthcare.svg" height="128" alt="Marley Health Logo">
  </a>
  <h2>Marley Health</h2>
  <p align="center">
    <p>Open source & easy-to-use hospital information system(HIS) for all healthcare organisations.</p>
  </p>

  [Marley Health](https://marleyhealth.io)

 <div align="center" style="max-height: 40px;">
    <a href="https://frappecloud.com/marley/signup">
        <img src=".github/try-on-f-cloud-button.svg" height="40">
    </a>
 </div>

</div>

### Introduction

Marley Health enables the health domain in ERPNext and has various features that will help healthcare practitioners, clinics and hospitals to leverage the power of Frappe and ERPNext. It is built on Frappe, a full-stack, meta-data driven, web framework, and integrates seamlessly with ERPNext, the most agile ERP software. Marley Health helps to manage healthcare workflows efficiently and most of the design is based on HL7 FHIR (Fast Health Interoperability Resources).


### Key Features

![Key Features](https://raw.githubusercontent.com/frappe/health/develop/key-features.png)

Key feature sets include Patient management, Outpatient / Inpatient management, Clinical Procedures, Rehabilitation and Physiotherapy, Laboratory management etc. and supports configuring multiple Medical Code Standards. It allows mapping any healthcare facility as Service Units and specialities as Medical Departments.

By integrating with ERPNext, features of ERPNext can also be utilized to manage Pharmacy and supplies, Purchases, Human Resources, Accounts and Finance, Asset Management, Quality etc. Along with authentication and role based access permissions, RESTfullness, extensibility, responsiveness and other goodies, the framework also allows setting up Website, payment integration and Patient portal.


### Installation

Using bench, [install ERPNext](https://github.com/frappe/bench#installation) as mentioned here.

Once ERPNext is installed, add health app to your bench by running

```sh
$ bench get-app healthcare
```

After that, you can install health app on required site by running

```sh
$ bench --site demo.com install-app healthcare
```


### Documentation

Complete documentation for Marley Health is available at https://marleyhealth.io/docs


---

## CIEL Terminology – Architecture & Operations

### Design decision: import-first, OCL as upstream

Marley uses CIEL (Columbia International eHealth Laboratory) concept codes stored
**locally** in the Marley database.  OpenConceptLab (OCL) acts as the canonical
upstream source; no user-facing lookup has a runtime dependency on the OCL API.

```
                ┌────────────┐       scheduled / on-demand
                │    OCL     │ ─────────────────────────────►  bench sync-ciel
                │  (CIEL)    │                                       │
                └────────────┘                                       │
                                                                     ▼
                                                         ┌─────────────────────┐
                                                         │  CIEL Terminology   │
                                                         │  Version  (Frappe)  │
                                                         │  CIEL Concept       │
                                                         │  CIEL Concept Name  │
                                                         │  CIEL Concept Mapping│
                                                         └────────┬────────────┘
                                                                  │
                                             ┌────────────────────┴───────────────────┐
                                             │         Marley runtime lookups          │
                                             │  /api/method/…terminology.search_concepts
                                             │  /api/method/…terminology.validate_code
                                             │  /api/method/…terminology.get_mappings  │
                                             └────────────────────────────────────────┘
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `OCL_BASE_URL` | `https://api.openconceptlab.org` | OCL REST API base URL |
| `OCL_TOKEN` | *(empty)* | OCL API token (required for private sources) |
| `OCL_ORG` | `CIEL` | OCL organisation slug |
| `OCL_SOURCE` | `CIEL` | OCL source slug |

Variables can also be set in `site_config.json` (lower-case keys):
```json
{
  "ocl_base_url": "https://api.openconceptlab.org",
  "ocl_token": "your-token-here",
  "ocl_org": "CIEL",
  "ocl_source": "CIEL"
}
```

### Import / promotion workflow

#### One-time manual import

```sh
# Import the latest CIEL release and immediately promote it to default
bench --site demo.com sync-ciel --version latest --make-default

# Import a specific version without promoting
bench --site demo.com sync-ciel --version 2024-01-01

# Dry-run: resolve version, print what would be imported, make no changes
bench --site demo.com sync-ciel --version latest --dry-run

# Re-import a version that is already marked 'ready'
bench --site demo.com sync-ciel --version 2024-01-01 --force
```

#### Nightly auto-sync (optional)

Enable in **Healthcare Settings** by checking *CIEL Auto Sync Enabled*.
The scheduler will fetch the latest version daily.  Auto-sync does **not**
promote the new version automatically – an administrator must review and
promote it.

#### Promoting / rolling back a version

```sh
# Promote via CLI
bench --site demo.com execute \
  healthcare.healthcare.doctype.ciel_terminology_version.ciel_terminology_version.CIELTerminologyVersion.promote_to_default \
  --args '["CIEL-VER-2024-01-01"]'
```

Or open the **CIEL Terminology Version** doctype in the Desk, select the
desired version, and click **Promote to Default**.

Up to N historical versions are retained; only one is `is_default=1` at any
given time.

### Internal API endpoints

All endpoints require an authenticated Frappe session.

| Endpoint | Description |
|---|---|
| `GET /api/method/healthcare.healthcare.api.terminology.search_concepts?query=malaria&locale=en` | Full-text concept search |
| `GET /api/method/healthcare.healthcare.api.terminology.get_concept?external_id=116128` | Concept detail by CIEL ID |
| `GET /api/method/healthcare.healthcare.api.terminology.validate_code?system=CIEL&code=116128` | Code existence check |
| `GET /api/method/healthcare.healthcare.api.terminology.get_mappings?target_system=ICD-10&code=B54` | Mappings by target system/code |

### FHIR terminology stubs (phase 2)

| Endpoint | FHIR operation |
|---|---|
| `GET …/fhir_lookup?system=…&code=116128` | `CodeSystem/$lookup` |
| `POST …/fhir_validate_code` | `ValueSet/$validate-code` |
| `GET …/fhir_expand?filter=malaria` | `ValueSet/$expand` |

All responses are backed by local CIEL data; no live OCL calls at request time.

### License

GNU GPL V3. See [license.txt](https://github.com/earthians/marley/blob/develop/license.txt) for more information.
