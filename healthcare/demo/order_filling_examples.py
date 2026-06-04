"""
Demo seed script: Order Filling Examples
=========================================

Seeds the healthcare app with the four worked examples documented in
/workspace/development/Order Filling.md:

  Example 1 — CT Chest with Contrast (STAT — suspected PE)
    Patient:     Garcia, Maria (DOB 1978-04-12)
    Clinician:   Dr. Okonkwo (Emergency Medicine)
    Exam:        CT Chest with Contrast — GE Revolution CT
    Priority:    STAT
    Stage:       SCHEDULED (just submitted, SPS created automatically)

  Example 2 — MRI Brain with and without Contrast (High — new seizure)
    Patient:     Ibrahim, Fatima (DOB 1991-09-03)
    Clinician:   Dr. Reyes (Neurology)
    Exam:        MRI Brain with and without Contrast — Siemens Prisma 3T
    Priority:    HIGH
    Stage:       SCHEDULED (SPS created automatically on ISR submit)

  Example 3 — Ultrasound Abdomen (ROUTINE — gallstone query)
    Patient:     Okonkwo, Emeka (DOB 1965-11-28)
    Clinician:   Dr. Santos (General Practice)
    Exam:        Ultrasound Abdomen — Standard (US-ROOM1)
    Priority:    ROUTINE
    Stage:       SCHEDULED (SPS created automatically on ISR submit)

  Example 4 — Chest X-Ray PA and Lateral (ROUTINE — pre-operative)
    Patient:     Lindqvist, Astrid (DOB 1948-07-19)
    Clinician:   Dr. Park (Anaesthesiology)
    Exam:        Chest X-Ray PA and Lateral — DR Panel (DX-ROOM1)
    Priority:    ROUTINE
    Stage:       SCHEDULED (SPS created automatically on ISR submit)

The script creates, in order:
  1. AE Mappings         — CT-MAIN, MR-3T0, MR-1T5, US-ROOM1, DX-ROOM1
  2. Procedure Types     — CT Chest with Contrast, MRI Brain w/ & w/o Contrast,
                           Ultrasound Abdomen, Chest X-Ray PA and Lateral
  3. Procedure Plans     — one CT plan (is_default), two MRI plans (3T default),
                           US Abdomen — Standard, CXR PA+Lat — DR Panel
  4. Patients            — Garcia, Maria; Ibrahim, Fatima;
                           Okonkwo, Emeka; Lindqvist, Astrid
  5. Healthcare Practitioners — Dr. Okonkwo, Dr. Reyes, Dr. Santos, Dr. Park
  6. Requested Procedures    — one per ISR
  7. Imaging Service Requests — inserted + submitted (triggers SPS creation)

Usage
-----
Seed::

    bench --site development.localhost execute \\
        healthcare.demo.order_filling_examples.run

Teardown::

    bench --site development.localhost execute \\
        healthcare.demo.order_filling_examples.teardown

Both functions are idempotent — running them multiple times is safe.
"""

from datetime import datetime, timedelta, date

import frappe
from frappe.utils import now_datetime, getdate

# ─── Stable identifiers ───────────────────────────────────────────────────────
# All names are sufficiently unique to avoid collisions with real data.

_PROCEDURE_TYPES = {
    "CT_CHEST_CONTRAST": "CT Chest with Contrast",
    "MRI_BRAIN_WW":      "MRI Brain with and without Contrast",
    "US_ABDOMEN":        "Ultrasound Abdomen",
    "CXR_PA_LAT":        "Chest X-Ray PA and Lateral",
}

_PROCEDURE_PLANS = {
    "CT_GE_REVOLUTION":   "CT Chest Contrast — GE Revolution",
    "MRI_PRISMA_3T":      "MRI Brain — Siemens Prisma 3T",
    "MRI_SIGNA_1T5":      "MRI Brain — GE Signa 1.5T",
    "US_ABDOMEN_STD":     "US Abdomen — Standard",
    "CXR_DR_PANEL":       "CXR PA+Lat — DR Panel",
}

# Map each plan key → its Procedure Type key (used in teardown name construction)
_PLAN_TO_PT_KEY = {
    "CT_GE_REVOLUTION": "CT_CHEST_CONTRAST",
    "MRI_PRISMA_3T":    "MRI_BRAIN_WW",
    "MRI_SIGNA_1T5":    "MRI_BRAIN_WW",
    "US_ABDOMEN_STD":   "US_ABDOMEN",
    "CXR_DR_PANEL":     "CXR_PA_LAT",
}

_AE_MAPPINGS = [
    dict(
        ae_title     = "CT-MAIN",
        display_name = "GE Revolution CT (Main Suite)",
        node_type    = "Acquisition Modality",
        modality     = "CT",
        station_name = "CT-MAIN",
        host         = "192.168.10.20",
        port         = 104,
        dicomweb_url = "",
    ),
    dict(
        ae_title     = "MR-3T0",
        display_name = "Siemens Prisma 3T — MRI Suite 1",
        node_type    = "Acquisition Modality",
        modality     = "MR",
        station_name = "MR-3T0",
        host         = "192.168.10.21",
        port         = 104,
        dicomweb_url = "",
    ),
    dict(
        ae_title     = "MR-1T5",
        display_name = "GE Signa 1.5T — MRI Suite 2",
        node_type    = "Acquisition Modality",
        modality     = "MR",
        station_name = "MR-1T5",
        host         = "192.168.10.22",
        port         = 104,
        dicomweb_url = "",
    ),
    dict(
        ae_title     = "US-ROOM1",
        display_name = "Ultrasound Room 1 — General US",
        node_type    = "Acquisition Modality",
        modality     = "US",
        station_name = "US-ROOM1",
        host         = "192.168.10.23",
        port         = 104,
        dicomweb_url = "",
    ),
    dict(
        ae_title     = "DX-ROOM1",
        display_name = "DR Panel Room 1 — Chest X-Ray",
        node_type    = "Acquisition Modality",
        modality     = "DX",
        station_name = "DX-ROOM1",
        host         = "192.168.10.24",
        port         = 104,
        dicomweb_url = "",
    ),
]

# ─── Step 1: AE Mappings ─────────────────────────────────────────────────────

def _ensure_ae_mappings():
    created = 0
    for m in _AE_MAPPINGS:
        if frappe.db.exists("AE Mapping", m["ae_title"]):
            print(f"  —  AE Mapping already exists: {m['ae_title']}")
            continue
        doc = frappe.new_doc("AE Mapping")
        for k, v in m.items():
            setattr(doc, k, v)
        doc.name   = m["ae_title"]
        doc.active = 1
        doc.flags.ignore_permissions = True
        doc.insert()
        print(f"  ✓  Created AE Mapping: {m['ae_title']}  ({m['display_name']})")
        created += 1
    if created:
        frappe.db.commit()


# ─── Step 2: Procedure Types ─────────────────────────────────────────────────

def _ensure_procedure_types():
    _ensure_ct_chest_with_contrast()
    _ensure_mri_brain_ww()
    _ensure_us_abdomen()
    _ensure_cxr_pa_lat()
    frappe.db.commit()


def _ensure_ct_chest_with_contrast():
    name = _PROCEDURE_TYPES["CT_CHEST_CONTRAST"]
    if frappe.db.exists("Procedure Type", name):
        print(f"  —  Procedure Type already exists: {name}")
        return

    doc = frappe.get_doc({
        "doctype":                  "Procedure Type",
        "procedure_name":           name,
        "default_modality":         "CT",
        "typical_duration":         30,
        "contrast_required":        "Required",
        "radlex_rpid":              "RID10321",
        "radlex_name":              "CT of chest with contrast",
        "preparation_instructions": (
            "NPO 4 hours before. Creatinine check required. "
            "Obtain eGFR if age > 60 or renal history."
        ),
        "is_active": 1,
        # Note: codification_table omitted — requires pre-existing Code Value Link docs.
        # CPT 71250 / LOINC 36643-5 can be added manually via the UI.
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Type: {name}")


def _ensure_mri_brain_ww():
    name = _PROCEDURE_TYPES["MRI_BRAIN_WW"]
    if frappe.db.exists("Procedure Type", name):
        print(f"  —  Procedure Type already exists: {name}")
        return

    doc = frappe.get_doc({
        "doctype":                  "Procedure Type",
        "procedure_name":           name,
        "default_modality":         "MR",
        "typical_duration":         60,
        "contrast_required":        "Required",
        "radlex_rpid":              "RID10312",
        "radlex_name":              "MRI brain with and without contrast",
        "preparation_instructions": (
            "Remove all metal jewellery. MRI safety screening form required. "
            "Gadolinium: eGFR > 30 required."
        ),
        "is_active": 1,
        # Note: codification_table omitted — requires pre-existing Code Value Link docs.
        # CPT 70553 can be added manually via the UI.
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Type: {name}")

def _ensure_us_abdomen():
    name = _PROCEDURE_TYPES["US_ABDOMEN"]
    if frappe.db.exists("Procedure Type", name):
        print(f"  —  Procedure Type already exists: {name}")
        return

    doc = frappe.get_doc({
        "doctype":                  "Procedure Type",
        "procedure_name":           name,
        "default_modality":         "US",
        "typical_duration":         20,
        "contrast_required":        "No",
        "radlex_rpid":              "RID10335",
        "radlex_name":              "ultrasound of abdomen",
        "preparation_instructions": (
            "NPO 6 hours before (water permitted). "
            "Wear loose, comfortable clothing. Empty bladder 1 hour prior."
        ),
        "is_active": 1,
        # Note: codification_table omitted — CPT 76700 / LOINC 45036-8
        # can be added manually via the UI once Code Value records exist.
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Type: {name}")


def _ensure_cxr_pa_lat():
    name = _PROCEDURE_TYPES["CXR_PA_LAT"]
    if frappe.db.exists("Procedure Type", name):
        print(f"  —  Procedure Type already exists: {name}")
        return

    doc = frappe.get_doc({
        "doctype":                  "Procedure Type",
        "procedure_name":           name,
        "default_modality":         "DX",
        "typical_duration":         10,
        "contrast_required":        "No",
        "radlex_rpid":              "RID10399",
        "radlex_name":              "radiograph of chest",
        "preparation_instructions": (
            "Remove jewellery and clothing above waist. Wear gown provided. "
            "Bring any prior chest films if available."
        ),
        "is_active": 1,
        # Note: codification_table omitted — CPT 71046 / LOINC 36643-5-CXR
        # can be added manually via the UI once Code Value records exist.
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Type: {name}")

# ─── Step 3: Procedure Plans ─────────────────────────────────────────────────

def _ensure_procedure_plans():
    _ensure_ct_plan_ge_revolution()
    _ensure_mri_plan_prisma_3t()
    _ensure_mri_plan_signa_1t5()
    _ensure_us_abdomen_std_plan()
    _ensure_cxr_dr_panel_plan()
    frappe.db.commit()


def _ensure_ct_plan_ge_revolution():
    """CT Chest Contrast — GE Revolution (is_default = 1)"""
    plan_name = _PROCEDURE_PLANS["CT_GE_REVOLUTION"]
    pt_name   = _PROCEDURE_TYPES["CT_CHEST_CONTRAST"]
    # autoname: {plan_name}-{procedure_type}
    doc_name = f"{plan_name}-{pt_name}"
    if frappe.db.exists("Procedure Plan", doc_name):
        print(f"  —  Procedure Plan already exists: {plan_name}")
        return

    doc = frappe.get_doc({
        "doctype":               "Procedure Plan",
        "plan_name":             plan_name,
        "procedure_type":        pt_name,
        "is_default":            1,
        "equipment_requirements": "GE Revolution CT, power injector, 18G IV access",
        "consumables":           "Iohexol 350 mg/mL, 80 mL",
        "plan_items": [
            {
                "sequence":              1,
                "step_label":            "IV Access & Scout",
                "protocol_code":         "LOCAL-001",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Scout and IV placement",
                "modality":              "CT",
                "expected_duration":     5,
            },
            {
                "sequence":              2,
                "step_label":            "Non-contrast acquisition",
                "protocol_code":         "36643-5-NC",
                "protocol_code_system":  "LOINC",
                "protocol_code_meaning": "CT chest without contrast",
                "modality":              "CT",
                "expected_duration":     5,
            },
            {
                "sequence":              3,
                "step_label":            "Contrast injection + bolus tracking",
                "protocol_code":         "LOCAL-002",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Power injector bolus chase",
                "modality":              "CT",
                "expected_duration":     5,
            },
            {
                "sequence":              4,
                "step_label":            "Arterial phase acquisition",
                "protocol_code":         "36643-5",
                "protocol_code_system":  "LOINC",
                "protocol_code_meaning": "CT chest with contrast",
                "modality":              "CT",
                "expected_duration":     10,
            },
            {
                "sequence":              5,
                "step_label":            "Post-processing — MIP/MPR",
                "protocol_code":         "LOCAL-003",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Coronal/sagittal reformats",
                "modality":              "CT",
                "expected_duration":     5,
            },
        ],
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Plan: {plan_name}  (is_default=1)")


def _ensure_mri_plan_prisma_3t():
    """MRI Brain — Siemens Prisma 3T (is_default = 1)"""
    plan_name = _PROCEDURE_PLANS["MRI_PRISMA_3T"]
    pt_name   = _PROCEDURE_TYPES["MRI_BRAIN_WW"]
    doc_name  = f"{plan_name}-{pt_name}"
    if frappe.db.exists("Procedure Plan", doc_name):
        print(f"  —  Procedure Plan already exists: {plan_name}")
        return

    doc = frappe.get_doc({
        "doctype":                "Procedure Plan",
        "plan_name":              plan_name,
        "procedure_type":         pt_name,
        "is_default":             1,
        "equipment_requirements": "Siemens Prisma 3T, 20-ch head coil",
        "consumables":            "Gadolinium (Gadavist) 0.1 mmol/kg",
        "plan_items": [
            {
                "sequence":              1,
                "step_label":            "Localizer",
                "protocol_code":         "LOCAL-MR-001",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "3-plane localizer",
                "modality":              "MR",
                "expected_duration":     3,
            },
            {
                "sequence":              2,
                "step_label":            "T1 MPRAGE pre-contrast",
                "protocol_code":         "LOCAL-MR-002",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "3D T1 MPRAGE 1mm isotropic",
                "modality":              "MR",
                "expected_duration":     8,
            },
            {
                "sequence":              3,
                "step_label":            "T2 FLAIR",
                "protocol_code":         "LOCAL-MR-003",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Axial T2 FLAIR 5mm",
                "modality":              "MR",
                "expected_duration":     5,
            },
            {
                "sequence":              4,
                "step_label":            "DWI",
                "protocol_code":         "LOCAL-MR-004",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Axial DWI b0/b1000",
                "modality":              "MR",
                "expected_duration":     4,
            },
            {
                "sequence":              5,
                "step_label":            "Contrast injection",
                "protocol_code":         "LOCAL-MR-005",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "IV Gadolinium push",
                "modality":              "MR",
                "expected_duration":     2,
            },
            {
                "sequence":              6,
                "step_label":            "T1 MPRAGE post-contrast",
                "protocol_code":         "LOCAL-MR-006",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "3D T1 MPRAGE post-Gd",
                "modality":              "MR",
                "expected_duration":     8,
            },
            {
                "sequence":              7,
                "step_label":            "T1 axial + coronal post",
                "protocol_code":         "LOCAL-MR-007",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "2D T1 post-Gd multiplane",
                "modality":              "MR",
                "expected_duration":     5,
            },
        ],
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Plan: {plan_name}  (is_default=1)")


def _ensure_mri_plan_signa_1t5():
    """MRI Brain — GE Signa 1.5T (is_default = 0)"""
    plan_name = _PROCEDURE_PLANS["MRI_SIGNA_1T5"]
    pt_name   = _PROCEDURE_TYPES["MRI_BRAIN_WW"]
    doc_name  = f"{plan_name}-{pt_name}"
    if frappe.db.exists("Procedure Plan", doc_name):
        print(f"  —  Procedure Plan already exists: {plan_name}")
        return

    doc = frappe.get_doc({
        "doctype":                "Procedure Plan",
        "plan_name":              plan_name,
        "procedure_type":         pt_name,
        "is_default":             0,
        "equipment_requirements": "GE Signa 1.5T, 8-ch head coil",
        "consumables":            "Gadolinium (Gadavist) 0.1 mmol/kg",
        "plan_items": [
            {
                "sequence":              1,
                "step_label":            "Localizer",
                "protocol_code":         "LOCAL-MR-101",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "3-plane localizer",
                "modality":              "MR",
                "expected_duration":     3,
            },
            {
                "sequence":              2,
                "step_label":            "T1 BRAVO pre-contrast",
                "protocol_code":         "LOCAL-MR-102",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "3D T1 BRAVO 1.2mm",
                "modality":              "MR",
                "expected_duration":     10,
            },
            {
                "sequence":              3,
                "step_label":            "T2 FLAIR",
                "protocol_code":         "LOCAL-MR-103",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Axial FLAIR 5mm",
                "modality":              "MR",
                "expected_duration":     7,
            },
            {
                "sequence":              4,
                "step_label":            "DWI",
                "protocol_code":         "LOCAL-MR-104",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Axial DWI b0/b1000",
                "modality":              "MR",
                "expected_duration":     5,
            },
            {
                "sequence":              5,
                "step_label":            "Contrast injection",
                "protocol_code":         "LOCAL-MR-105",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "IV Gadolinium push",
                "modality":              "MR",
                "expected_duration":     2,
            },
            {
                "sequence":              6,
                "step_label":            "T1 BRAVO post-contrast",
                "protocol_code":         "LOCAL-MR-106",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "3D T1 BRAVO post-Gd",
                "modality":              "MR",
                "expected_duration":     10,
            },
            {
                "sequence":              7,
                "step_label":            "T1 axial post",
                "protocol_code":         "LOCAL-MR-107",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "2D T1 post-Gd axial",
                "modality":              "MR",
                "expected_duration":     6,
            },
        ],
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Plan: {plan_name}  (is_default=0 — fallback 1.5T)")


def _ensure_us_abdomen_std_plan():
    """US Abdomen — Standard (is_default = 1, no contrast)"""
    plan_name = _PROCEDURE_PLANS["US_ABDOMEN_STD"]
    pt_name   = _PROCEDURE_TYPES["US_ABDOMEN"]
    doc_name  = f"{plan_name}-{pt_name}"
    if frappe.db.exists("Procedure Plan", doc_name):
        print(f"  —  Procedure Plan already exists: {plan_name}")
        return

    doc = frappe.get_doc({
        "doctype":                "Procedure Plan",
        "plan_name":              plan_name,
        "procedure_type":         pt_name,
        "is_default":             1,
        "equipment_requirements": "Any US unit with curvilinear (3–5 MHz) probe",
        "consumables":            "Ultrasound gel",
        "plan_items": [
            {
                "sequence":              1,
                "step_label":            "Scout / subxiphoid survey",
                "protocol_code":         "LOCAL-US-001",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Initial orientation and organ identification",
                "modality":              "US",
                "expected_duration":     4,
            },
            {
                "sequence":              2,
                "step_label":            "Gallbladder and biliary tree",
                "protocol_code":         "LOCAL-US-002",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "GB wall, lumen, CBD diameter, stones/sludge",
                "modality":              "US",
                "expected_duration":     8,
            },
            {
                "sequence":              3,
                "step_label":            "Abdominal survey",
                "protocol_code":         "LOCAL-US-003",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Liver, spleen, kidneys, aorta, free fluid",
                "modality":              "US",
                "expected_duration":     8,
            },
        ],
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Plan: {plan_name}  (is_default=1)")


def _ensure_cxr_dr_panel_plan():
    """CXR PA+Lat — DR Panel (is_default = 1, no contrast)"""
    plan_name = _PROCEDURE_PLANS["CXR_DR_PANEL"]
    pt_name   = _PROCEDURE_TYPES["CXR_PA_LAT"]
    doc_name  = f"{plan_name}-{pt_name}"
    if frappe.db.exists("Procedure Plan", doc_name):
        print(f"  —  Procedure Plan already exists: {plan_name}")
        return

    doc = frappe.get_doc({
        "doctype":                "Procedure Plan",
        "plan_name":              plan_name,
        "procedure_type":         pt_name,
        "is_default":             1,
        "equipment_requirements": "Digital Radiography (DR) wall bucky + chest stand",
        "consumables":            "None",
        "plan_items": [
            {
                "sequence":              1,
                "step_label":            "Patient positioning",
                "protocol_code":         "LOCAL-DX-001",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Erect PA positioning, chin raised, arms rotated",
                "modality":              "DX",
                "expected_duration":     2,
            },
            {
                "sequence":              2,
                "step_label":            "PA chest exposure",
                "protocol_code":         "LOCAL-DX-002",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "PA projection, full inspiration, 180 cm FFD",
                "modality":              "DX",
                "expected_duration":     3,
            },
            {
                "sequence":              3,
                "step_label":            "Lateral chest exposure",
                "protocol_code":         "LOCAL-DX-003",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Left lateral, arms above head, full inspiration",
                "modality":              "DX",
                "expected_duration":     3,
            },
            {
                "sequence":              4,
                "step_label":            "Technical QC / image release",
                "protocol_code":         "LOCAL-DX-004",
                "protocol_code_system":  "LOCAL",
                "protocol_code_meaning": "Check exposure, edge sharpness, release to PACS",
                "modality":              "DX",
                "expected_duration":     2,
            },
        ],
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    print(f"  ✓  Created Procedure Plan: {plan_name}  (is_default=1)")


# ─── Step 4: Patients ─────────────────────────────────────────────────────────

def _ensure_patient(first_name, last_name, dob_str, sex, blood_group=None, allergies=None):
    """
    Find or create a Patient. Matches on (first_name, last_name, dob).
    Returns the Patient document.
    """
    match = frappe.db.get_value(
        "Patient",
        {"first_name": first_name, "last_name": last_name, "dob": dob_str},
        "name",
    )
    if match:
        print(f"  —  Patient already exists: {first_name} {last_name}")
        return frappe.get_doc("Patient", match)

    doc = frappe.get_doc({
        "doctype":     "Patient",
        "first_name":  first_name,
        "last_name":   last_name,
        "dob":         getdate(dob_str),
        "sex":         sex,
        "blood_group": blood_group or "",
    })
    if allergies:
        doc.allergies = allergies
    doc.flags.ignore_permissions = True
    doc.insert()
    frappe.db.commit()
    print(f"  ✓  Created Patient: {first_name} {last_name}  ({doc.name})")
    return doc


def _ensure_patients():
    garcia    = _ensure_patient("Maria",  "Garcia",    "1978-04-12", "Female", blood_group="A Positive")
    ibrahim   = _ensure_patient("Fatima", "Ibrahim",   "1991-09-03", "Female")
    emeka     = _ensure_patient("Emeka",  "Okonkwo",   "1965-11-28", "Male")
    lindqvist = _ensure_patient("Astrid", "Lindqvist", "1948-07-19", "Female", blood_group="O Positive")
    return garcia, ibrahim, emeka, lindqvist


# ─── Step 5: Healthcare Practitioners ────────────────────────────────────────

def _ensure_practitioner(first_name, last_name):
    """Find or create a Healthcare Practitioner by full name."""
    match = frappe.db.get_value(
        "Healthcare Practitioner",
        {"first_name": first_name, "last_name": last_name},
        "name",
    )
    if match:
        print(f"  —  Practitioner already exists: {first_name} {last_name}")
        return frappe.get_doc("Healthcare Practitioner", match)

    doc = frappe.get_doc({
        "doctype":    "Healthcare Practitioner",
        "first_name": first_name,
        "last_name":  last_name,
        "status":     "Active",
        # department / speciality are Links (Medical Department / Speciality)
        # and may not exist; set via UI after seeding if needed.
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    frappe.db.commit()
    print(f"  ✓  Created Practitioner: {first_name} {last_name}  ({doc.name})")
    return doc


def _ensure_practitioners():
    okonkwo = _ensure_practitioner("Chidi",   "Okonkwo")   # ED / Pulmonology
    reyes   = _ensure_practitioner("Elena",   "Reyes")     # Neurology
    santos  = _ensure_practitioner("Miguel",  "Santos")    # General Practice
    park    = _ensure_practitioner("Ji-yeon", "Park")      # Anaesthesiology
    return okonkwo, reyes, santos, park


# ─── Step 6 + 7: Requested Procedures + Imaging Service Requests ─────────────

def _isr_already_seeded(patient_name, procedure_type_name):
    """Return True if an ISR for this patient+procedure already exists."""
    rp = frappe.db.get_value(
        "Requested Procedure",
        {"procedure_type": procedure_type_name},
        "name",
    )
    if not rp:
        return False
    # Check the RP belongs to an ISR for this patient
    isr = frappe.db.get_value(
        "Imaging Service Request",
        {"patient": patient_name},
        "name",
    )
    return bool(isr)


def _seed_garcia_isr(garcia, okonkwo):
    """Example 1 — Garcia, Maria — CT Chest with Contrast (STAT)."""
    pt_name = _PROCEDURE_TYPES["CT_CHEST_CONTRAST"]

    if _isr_already_seeded(garcia.name, pt_name):
        print(f"  —  ISR already exists: Garcia / {pt_name}")
        return

    # Create the Requested Procedure first (standalone doctype)
    rp = frappe.get_doc({
        "doctype":              "Requested Procedure",
        "procedure_type":       pt_name,
        "procedure_description": "CT Chest with Contrast",
        "modality":             "CT",
        "scheduled_datetime":   _offset_datetime(days=0, hour=14, minute=30),
        "reason_for_request":   "Suspected PE. D-dimer 4.2. Acute dyspnea, pleuritic chest pain.",
    })
    rp.flags.ignore_permissions = True
    rp.insert()
    frappe.db.commit()
    print(f"  ✓  Created Requested Procedure: {rp.name}  ({pt_name})")

    # Create and submit the Imaging Service Request
    isr = frappe.get_doc({
        "doctype":                      "Imaging Service Request",
        "patient":                      garcia.name,
        "priority":                     "STAT",
        "order_datetime":               _offset_datetime(days=0, hour=10, minute=22),
        "requesting_practitioner":      okonkwo.name,
        "clinical_indication":          (
            "Suspected PE. D-dimer 4.2 µg/mL (elevated). "
            "Acute dyspnea, pleuritic chest pain. eGFR > 60 — contrast safe."
        ),
        "requested_procedures": [
            {"requested_procedure": rp.name},
        ],
    })
    isr.flags.ignore_permissions = True
    isr.insert()
    frappe.db.commit()
    print(f"  ✓  Created ISR: {isr.name}  (STAT — Garcia)")

    # Submit triggers create_scheduled_procedure_steps()
    isr.flags.ignore_permissions = True
    isr.submit()
    frappe.db.commit()
    print(f"  ✓  Submitted ISR: {isr.name}  → SPS created automatically")

    # Report the SPS that was created
    rp.reload()
    if rp.scheduled_procedure_step:
        sps = frappe.get_doc("Scheduled Procedure Step", rp.scheduled_procedure_step)
        print(f"  ✓  Scheduled Procedure Step: {sps.name}")
        print(f"       modality={sps.modality}  duration={sps.expected_duration}min"
              f"  state={sps.ups_state}  protocol_codes={len(sps.protocol_codes)}")


def _seed_ibrahim_isr(ibrahim, reyes):
    """Example 2 — Ibrahim, Fatima — MRI Brain w/ & w/o Contrast (HIGH)."""
    pt_name = _PROCEDURE_TYPES["MRI_BRAIN_WW"]

    if _isr_already_seeded(ibrahim.name, pt_name):
        print(f"  —  ISR already exists: Ibrahim / {pt_name}")
        return

    # Create the Requested Procedure
    rp = frappe.get_doc({
        "doctype":               "Requested Procedure",
        "procedure_type":        pt_name,
        "procedure_description": "MRI Brain with and without Contrast",
        "modality":              "MR",
        "scheduled_datetime":    _offset_datetime(days=1, hour=9, minute=0),
        "reason_for_request":    "New onset seizure, r/o structural lesion. PA-2026-8821.",
    })
    rp.flags.ignore_permissions = True
    rp.insert()
    frappe.db.commit()
    print(f"  ✓  Created Requested Procedure: {rp.name}  ({pt_name})")

    # Create and submit the ISR
    isr = frappe.get_doc({
        "doctype":                  "Imaging Service Request",
        "patient":                  ibrahim.name,
        "priority":                 "HIGH",
        "order_datetime":           _offset_datetime(days=-1, hour=16, minute=45),
        "requesting_practitioner":  reyes.name,
        "clinical_indication":      (
            "New onset generalised tonic-clonic seizure. "
            "R/O structural lesion (tumour, cavernoma, cortical dysplasia). "
            "Prior auth PA-2026-8821. eGFR 95 — gadolinium safe."
        ),
        "requested_procedures": [
            {"requested_procedure": rp.name},
        ],
    })
    isr.flags.ignore_permissions = True
    isr.insert()
    frappe.db.commit()
    print(f"  ✓  Created ISR: {isr.name}  (HIGH — Ibrahim)")

    isr.flags.ignore_permissions = True
    isr.submit()
    frappe.db.commit()
    print(f"  ✓  Submitted ISR: {isr.name}  → SPS created automatically")

    rp.reload()
    if rp.scheduled_procedure_step:
        sps = frappe.get_doc("Scheduled Procedure Step", rp.scheduled_procedure_step)
        print(f"  ✓  Scheduled Procedure Step: {sps.name}")
        print(f"       modality={sps.modality}  duration={sps.expected_duration}min"
              f"  state={sps.ups_state}  protocol_codes={len(sps.protocol_codes)}")


def _seed_okonkwo_isr(emeka, santos):
    """Example 3 — Okonkwo, Emeka — Ultrasound Abdomen (ROUTINE — gallstone query)."""
    pt_name = _PROCEDURE_TYPES["US_ABDOMEN"]

    if _isr_already_seeded(emeka.name, pt_name):
        print(f"  —  ISR already exists: Okonkwo / {pt_name}")
        return

    # Create the Requested Procedure
    rp = frappe.get_doc({
        "doctype":               "Requested Procedure",
        "procedure_type":        pt_name,
        "procedure_description": "Ultrasound Abdomen",
        "modality":              "US",
        "scheduled_datetime":    _offset_datetime(days=3, hour=11, minute=0),
        "reason_for_request":    "RUQ pain, fatty food intolerance. Suspected cholelithiasis. BMI 28.",
    })
    rp.flags.ignore_permissions = True
    rp.insert()
    frappe.db.commit()
    print(f"  ✓  Created Requested Procedure: {rp.name}  ({pt_name})")

    # Create and submit the ISR
    isr = frappe.get_doc({
        "doctype":                 "Imaging Service Request",
        "patient":                 emeka.name,
        "priority":                "ROUTINE",
        "order_datetime":          _offset_datetime(days=0, hour=9, minute=10),
        "requesting_practitioner": santos.name,
        "clinical_indication":     (
            "6-week history of intermittent RUQ pain exacerbated by fatty foods. "
            "Murphy's sign equivocal on examination. "
            "Query cholelithiasis / biliary colic. eGFR normal — no contrast required."
        ),
        "requested_procedures": [
            {"requested_procedure": rp.name},
        ],
    })
    isr.flags.ignore_permissions = True
    isr.insert()
    frappe.db.commit()
    print(f"  ✓  Created ISR: {isr.name}  (ROUTINE — Okonkwo)")

    isr.flags.ignore_permissions = True
    isr.submit()
    frappe.db.commit()
    print(f"  ✓  Submitted ISR: {isr.name}  → SPS created automatically")

    rp.reload()
    if rp.scheduled_procedure_step:
        sps = frappe.get_doc("Scheduled Procedure Step", rp.scheduled_procedure_step)
        print(f"  ✓  Scheduled Procedure Step: {sps.name}")
        print(f"       modality={sps.modality}  duration={sps.expected_duration}min"
              f"  state={sps.ups_state}  protocol_codes={len(sps.protocol_codes)}")


def _seed_lindqvist_isr(lindqvist, park):
    """Example 4 — Lindqvist, Astrid — Chest X-Ray PA and Lateral (ROUTINE — pre-operative)."""
    pt_name = _PROCEDURE_TYPES["CXR_PA_LAT"]

    if _isr_already_seeded(lindqvist.name, pt_name):
        print(f"  —  ISR already exists: Lindqvist / {pt_name}")
        return

    # Create the Requested Procedure
    rp = frappe.get_doc({
        "doctype":               "Requested Procedure",
        "procedure_type":        pt_name,
        "procedure_description": "Chest X-Ray PA and Lateral",
        "modality":              "DX",
        "scheduled_datetime":    _offset_datetime(days=5, hour=8, minute=30),
        "reason_for_request":    "Pre-operative workup for elective right hip replacement. Anaesthesia assessment.",
    })
    rp.flags.ignore_permissions = True
    rp.insert()
    frappe.db.commit()
    print(f"  ✓  Created Requested Procedure: {rp.name}  ({pt_name})")

    # Create and submit the ISR
    isr = frappe.get_doc({
        "doctype":                 "Imaging Service Request",
        "patient":                 lindqvist.name,
        "priority":                "ROUTINE",
        "order_datetime":          _offset_datetime(days=-2, hour=14, minute=20),
        "requesting_practitioner": park.name,
        "clinical_indication":     (
            "Pre-operative chest assessment prior to elective right total hip replacement. "
            "Known 40-pack-year smoking history, ex-smoker since 2010. "
            "Baseline cardiorespiratory status required by anaesthesia team."
        ),
        "requested_procedures": [
            {"requested_procedure": rp.name},
        ],
    })
    isr.flags.ignore_permissions = True
    isr.insert()
    frappe.db.commit()
    print(f"  ✓  Created ISR: {isr.name}  (ROUTINE — Lindqvist)")

    isr.flags.ignore_permissions = True
    isr.submit()
    frappe.db.commit()
    print(f"  ✓  Submitted ISR: {isr.name}  → SPS created automatically")

    rp.reload()
    if rp.scheduled_procedure_step:
        sps = frappe.get_doc("Scheduled Procedure Step", rp.scheduled_procedure_step)
        print(f"  ✓  Scheduled Procedure Step: {sps.name}")
        print(f"       modality={sps.modality}  duration={sps.expected_duration}min"
              f"  state={sps.ups_state}  protocol_codes={len(sps.protocol_codes)}")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _offset_datetime(days=0, hour=9, minute=0):
    """Return a datetime relative to today at the requested time."""
    base = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=days)


# ─── Public entry points ─────────────────────────────────────────────────────

def run():
    """
    Seed the Order Filling demo data.

    Idempotent: skips any record that already exists.
    """
    print("\n── Order Filling Examples — Seed ────────────────────────────────")

    print("\n[1/5] AE Mappings (CT-MAIN, MR-3T0, MR-1T5, US-ROOM1, DX-ROOM1)")
    _ensure_ae_mappings()

    print("\n[2/5] Procedure Types")
    _ensure_procedure_types()

    print("\n[3/5] Procedure Plans")
    _ensure_procedure_plans()

    print("\n[4/5] Patients & Practitioners")
    garcia, ibrahim, emeka, lindqvist = _ensure_patients()
    okonkwo, reyes, santos, park      = _ensure_practitioners()

    print("\n[5/5] Imaging Service Requests (creates SPS on submit)")
    _seed_garcia_isr(garcia, okonkwo)
    _seed_ibrahim_isr(ibrahim, reyes)
    _seed_okonkwo_isr(emeka, santos)
    _seed_lindqvist_isr(lindqvist, park)

    print("\n── Done ─────────────────────────────────────────────────────────\n")
    print("  Verify in the browser:")
    print("   • Imaging Service Request list → four submitted ISRs")
    print("   • Scheduled Procedure Step list → four SCHEDULED workitems")
    print("   • Procedure Plan list → CT (1) + MRI (2) + US (1) + CXR (1) plans")
    print()


def teardown():
    """
    Remove all records created by run().

    Idempotent: safe to run multiple times.
    Deletes in reverse dependency order.
    """
    print("\n── Order Filling Examples — Teardown ────────────────────────────")

    # 1. Cancel + delete Imaging Service Requests (and their child SPS via cascade)
    print("\n[1] Imaging Service Requests")
    for patient_name in [
        frappe.db.get_value("Patient", {"first_name": "Maria",  "last_name": "Garcia"},    "name"),
        frappe.db.get_value("Patient", {"first_name": "Fatima", "last_name": "Ibrahim"},   "name"),
        frappe.db.get_value("Patient", {"first_name": "Emeka",  "last_name": "Okonkwo"},   "name"),
        frappe.db.get_value("Patient", {"first_name": "Astrid", "last_name": "Lindqvist"}, "name"),
    ]:
        if not patient_name:
            continue
        isrs = frappe.get_all("Imaging Service Request", filters={"patient": patient_name}, pluck="name")
        for isr_name in isrs:
            isr = frappe.get_doc("Imaging Service Request", isr_name)
            if isr.docstatus == 1:
                try:
                    isr.flags.ignore_permissions = True
                    isr.cancel()
                    frappe.db.commit()
                except Exception as e:
                    print(f"  ⚠  Could not cancel ISR {isr_name}: {e}")
            frappe.delete_doc("Imaging Service Request", isr_name, force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✓  Deleted ISR: {isr_name}")

    # 2. Delete Scheduled Procedure Steps (may already be cascade-deleted)
    # Look up via Requested Procedure → scheduled_procedure_step link.
    print("\n[2] Scheduled Procedure Steps")
    for pt in [
        _PROCEDURE_TYPES["CT_CHEST_CONTRAST"],
        _PROCEDURE_TYPES["MRI_BRAIN_WW"],
        _PROCEDURE_TYPES["US_ABDOMEN"],
        _PROCEDURE_TYPES["CXR_PA_LAT"],
    ]:
        rp_names = frappe.get_all("Requested Procedure", filters={"procedure_type": pt}, pluck="name")
        for rp_name in rp_names:
            sps_name = frappe.db.get_value("Requested Procedure", rp_name, "scheduled_procedure_step")
            if sps_name and frappe.db.exists("Scheduled Procedure Step", sps_name):
                frappe.delete_doc("Scheduled Procedure Step", sps_name, force=True, ignore_permissions=True)
                frappe.db.commit()
                print(f"  ✓  Deleted SPS: {sps_name}")

    # 3. Delete Requested Procedures
    print("\n[3] Requested Procedures")
    for pt in [
        _PROCEDURE_TYPES["CT_CHEST_CONTRAST"],
        _PROCEDURE_TYPES["MRI_BRAIN_WW"],
        _PROCEDURE_TYPES["US_ABDOMEN"],
        _PROCEDURE_TYPES["CXR_PA_LAT"],
    ]:
        rps = frappe.get_all("Requested Procedure", filters={"procedure_type": pt}, pluck="name")
        for rp_name in rps:
            frappe.delete_doc("Requested Procedure", rp_name, force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✓  Deleted Requested Procedure: {rp_name}")

    # 4. Delete Procedure Plans
    print("\n[4] Procedure Plans")
    for plan_key, plan_name in _PROCEDURE_PLANS.items():
        # autoname is {plan_name}-{procedure_type}
        pt_key   = _PLAN_TO_PT_KEY[plan_key]
        doc_name = f"{plan_name}-{_PROCEDURE_TYPES[pt_key]}"
        if frappe.db.exists("Procedure Plan", doc_name):
            frappe.delete_doc("Procedure Plan", doc_name, force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✓  Deleted Procedure Plan: {plan_name}")

    # 5. Delete Procedure Types
    print("\n[5] Procedure Types")
    for key, name in _PROCEDURE_TYPES.items():
        if frappe.db.exists("Procedure Type", name):
            frappe.delete_doc("Procedure Type", name, force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✓  Deleted Procedure Type: {name}")

    # 6. Delete Patients
    print("\n[6] Patients")
    for first, last in [
        ("Maria",  "Garcia"),
        ("Fatima", "Ibrahim"),
        ("Emeka",  "Okonkwo"),
        ("Astrid", "Lindqvist"),
    ]:
        pt = frappe.db.get_value("Patient", {"first_name": first, "last_name": last}, "name")
        if pt:
            frappe.delete_doc("Patient", pt, force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✓  Deleted Patient: {first} {last}")

    # 7. Delete Healthcare Practitioners
    print("\n[7] Practitioners")
    for first, last in [
        ("Chidi",   "Okonkwo"),
        ("Elena",   "Reyes"),
        ("Miguel",  "Santos"),
        ("Ji-yeon", "Park"),
    ]:
        hp = frappe.db.get_value("Healthcare Practitioner", {"first_name": first, "last_name": last}, "name")
        if hp:
            frappe.delete_doc("Healthcare Practitioner", hp, force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✓  Deleted Practitioner: {first} {last}")

    # 8. Delete AE Mappings created by this script
    print("\n[8] AE Mappings")
    for m in _AE_MAPPINGS:
        if frappe.db.exists("AE Mapping", m["ae_title"]):
            frappe.delete_doc("AE Mapping", m["ae_title"], force=True, ignore_permissions=True)
            frappe.db.commit()
            print(f"  ✓  Deleted AE Mapping: {m['ae_title']}")

    print("\n── Teardown complete ─────────────────────────────────────────────\n")
