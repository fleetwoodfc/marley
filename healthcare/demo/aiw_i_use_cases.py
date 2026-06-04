"""
Demo seed script: AIW-I Use Cases §50.4.2
==========================================

Implements all seven use cases defined in Section 50.4.2 of the IHE Radiology
Technical Framework Supplement — AI Workflow for Imaging (AIW-I) Rev. 1.1.

    Spec: specs/001-ups-worklist-portal/IHE_RAD_Suppl_AIW-I.pdf

Use Case summary
----------------
UC1  Pull Workflow            Task Performer queries (polls) the Task Manager for
                              assigned workitems and claims them.
UC2  Triggered Pull Workflow  Task Performer subscribes via WebSocket; Task Manager
                              sends notification when workitem is ready; performer pulls
                              and claims the notified workitem.
UC3  Push Workflow            Task Manager pushes workitem directly to Task Performer
                              (creates Workitem Y on performer); performer processes and
                              notifies the Task Manager of completion.
UC4  Exception Management     Pre-claim rejection, post-claim cancellation, partial
                              completion, and push-workflow rejection sub-cases.
UC5  Proxied AI Models        Task Performer acts as proxy between hospital and one or
                              more AI Models; assembles medical result from proxy output.
UC6  Inference with           Two-step: inference workitem stores results in a cache;
     Verification             human-review verification workitem approves and distributes.
UC7  Reading Workflow         AI Model (as Procedure Reporter) detects an abnormality and
     Priority                 escalates reading list priority via Procedure Update [RAD-13].

Actors introduced by this demo
-------------------------------
  CT-AI-PULM   CT Pulmonology AI Model        (UC1, UC4)
  MR-AI-BRAIN  MR Brain AI Model              (UC2)
  CT-AI-ABD    CT Abdomen AI Model            (UC3)
  CXR-AI-PROX  Chest X-Ray AI Proxy           (UC5)
  LU-AI-VERFY  Lung Nodule AI Model           (UC6, inference step)
  LU-HU-VERFY  Lung Nodule Human Reviewer     (UC6, verification step)
  CT-AI-CRIT   Critical-Finding Escalation AI (UC7)

Workitems seeded (13 total)
---------------------------
  UC1 — Garcia    SCHEDULED   CT chest AI (assigned, not yet claimed)
  UC1 — Hernandez IN PROGRESS CT chest AI (claimed by CT-AI-PULM)
  UC1 — Ibrahim   COMPLETED   CT chest AI (inference done, results stored)
  UC2 — Johnson   SCHEDULED   Brain MRI AI (notification sent, claim pending)
  UC2 — Kim       IN PROGRESS Brain MRI AI (claimed after WebSocket notification)
  UC3 — Lee       COMPLETED   Abdominal CT AI (push workflow, full cycle)
  UC4a— Martinez  CANCELED    CT chest AI (pre-claim rejection by CT-AI-PULM)
  UC4b— Nelson    CANCELED    CT chest AI (post-claim, failed mid-processing)
  UC4c— Okafor    COMPLETED   CT chest AI (partial – primary results, secondary incomplete)
  UC5 — Patel     COMPLETED   CXR pneumothorax proxy (multi-model chain)
  UC6a— Quinn-I   COMPLETED   Lung nodule inference (results in verification cache)
  UC6b— Quinn-V   IN PROGRESS Lung nodule verification (human reviewer, UC6 ver. step)
  UC7 — Rodriguez COMPLETED   Critical: large pneumothorax detected, priority escalated

Usage
-----
Seed::

    bench --site development.localhost execute \\
        healthcare.demo.aiw_i_use_cases.run

Teardown::

    bench --site development.localhost execute \\
        healthcare.demo.aiw_i_use_cases.teardown
"""

from datetime import datetime, timedelta

import frappe
from frappe.utils import now_datetime

# ── Stable fixed DICOM UIDs ───────────────────────────────────────────────────
# 2.25 root + 7000 namespace (different from push_workflow_xray_clinic 9000)
_BASE   = "2.25.70000000000000000000"
_T_BASE = "2.25.60000000000000000000"

WORKITEM_UIDS = {
    # UC1
    "GARCIA":     _BASE + "0001",
    "HERNANDEZ":  _BASE + "0002",
    "IBRAHIM":    _BASE + "0003",
    # UC2
    "JOHNSON":    _BASE + "0004",
    "KIM":        _BASE + "0005",
    # UC3
    "LEE":        _BASE + "0006",
    # UC4
    "MARTINEZ":   _BASE + "0007",
    "NELSON":     _BASE + "0008",
    "OKAFOR":     _BASE + "0009",
    # UC5
    "PATEL":      _BASE + "0010",
    # UC6
    "QUINN_INF":  _BASE + "0011",   # Inference workitem Y1
    "QUINN_VER":  _BASE + "0012",   # Verification workitem Y2
    # UC7
    "RODRIGUEZ":  _BASE + "0013",
}

TRANSACTION_UIDS = {
    "HERNANDEZ": _T_BASE + "0002",
    "IBRAHIM":   _T_BASE + "0003",
    "KIM":       _T_BASE + "0005",
    "LEE":       _T_BASE + "0006",
    "NELSON":    _T_BASE + "0008",
    "OKAFOR":    _T_BASE + "0009",
    "PATEL":     _T_BASE + "0010",
    "QUINN_INF": _T_BASE + "0011",
    "QUINN_VER": _T_BASE + "0012",
    "RODRIGUEZ": _T_BASE + "0013",
}

# ── AI Performer AE Mappings ──────────────────────────────────────────────────

_AI_AE_MAPPINGS = [
    dict(
        ae_title          = "CT-AI-PULM",
        display_name      = "CT Pulmonology AI Model",
        node_type         = "Post-Processing Workstation",
        modality          = "CT",
        station_name      = "CT-AI-PULM",
        station_class_code= "3DWORKSTATION",
        host              = "192.168.20.10",
        port              = 11112,
        dicomweb_url      = "http://192.168.20.10:8080/aets/CT-AI-PULM/rs",
    ),
    dict(
        ae_title          = "MR-AI-BRAIN",
        display_name      = "MR Brain AI Model",
        node_type         = "Post-Processing Workstation",
        modality          = "MR",
        station_name      = "MR-AI-BRAIN",
        station_class_code= "3DWORKSTATION",
        host              = "192.168.20.11",
        port              = 11112,
        dicomweb_url      = "http://192.168.20.11:8080/aets/MR-AI-BRAIN/rs",
    ),
    dict(
        ae_title          = "CT-AI-ABD",
        display_name      = "CT Abdomen AI Model",
        node_type         = "Post-Processing Workstation",
        modality          = "CT",
        station_name      = "CT-AI-ABD",
        station_class_code= "3DWORKSTATION",
        host              = "192.168.20.12",
        port              = 11112,
        dicomweb_url      = "http://192.168.20.12:8080/aets/CT-AI-ABD/rs",
    ),
    dict(
        ae_title          = "CXR-AI-PROX",
        display_name      = "Chest X-Ray AI Proxy (Pneumothorax)",
        node_type         = "Post-Processing Workstation",
        modality          = "CR",
        station_name      = "CXR-AI-PROX",
        station_class_code= "3DWORKSTATION",
        host              = "192.168.20.13",
        port              = 11112,
        dicomweb_url      = "http://192.168.20.13:8080/aets/CXR-AI-PROX/rs",
    ),
    dict(
        ae_title          = "LU-AI-VERFY",
        display_name      = "Lung Nodule AI Model (Inference)",
        node_type         = "Post-Processing Workstation",
        modality          = "CT",
        station_name      = "LU-AI-VERFY",
        station_class_code= "3DWORKSTATION",
        host              = "192.168.20.14",
        port              = 11112,
        dicomweb_url      = "http://192.168.20.14:8080/aets/LU-AI-VERFY/rs",
    ),
    dict(
        ae_title          = "LU-HU-VERFY",
        display_name      = "Lung Nodule Human Reviewer (Verification)",
        node_type         = "Reporting Workstation",
        modality          = "CT",
        station_name      = "LU-HU-VERFY",
        station_class_code= "REPORTINGWS",
        host              = "192.168.20.15",
        port              = 11112,
        dicomweb_url      = "",
    ),
    dict(
        ae_title          = "CT-AI-CRIT",
        display_name      = "Critical Finding AI (Escalation)",
        node_type         = "Post-Processing Workstation",
        modality          = "CT",
        station_name      = "CT-AI-CRIT",
        station_class_code= "3DWORKSTATION",
        host              = "192.168.20.16",
        port              = 11112,
        dicomweb_url      = "http://192.168.20.16:8080/aets/CT-AI-CRIT/rs",
    ),
]

_AI_AE_TITLES = {m["ae_title"] for m in _AI_AE_MAPPINGS}

# ── Shared helpers ────────────────────────────────────────────────────────────

def _today_at(hour, minute=0, offset_days=0):
    base = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=offset_days)


def _ensure_ai_ae_mappings():
    """Create AI performer AE Mapping records if they do not yet exist."""
    for m in _AI_AE_MAPPINGS:
        if frappe.db.exists("AE Mapping", m["ae_title"]):
            continue
        doc = frappe.new_doc("AE Mapping")
        for k, v in m.items():
            setattr(doc, k, v)
        doc.name   = m["ae_title"]
        doc.active = 1
        doc.flags.ignore_permissions = True
        doc.insert()
        print(f"  ✓  Created AE Mapping: {m['ae_title']} — {m['display_name']}")
    frappe.db.commit()


def _create_ups(
    uid, state, priority, patient_id, patient_name, patient_dob, patient_sex,
    procedure_id, accession, protocol, description, modality, aet, station_name,
    scheduled_dt, transaction_uid=None, station_class_code=None,
):
    """Insert a UPS Instance; skip silently if it already exists."""
    if frappe.db.exists("UPS Instance", uid):
        print(f"  —  Already exists: {patient_name}")
        return frappe.get_doc("UPS Instance", uid), False

    # Derive station class code from AE Mapping if not supplied.
    if station_class_code is None:
        station_class_code = (
            frappe.db.get_value("AE Mapping", aet, "station_class_code") or ""
        )

    doc = frappe.new_doc("UPS Instance")
    doc.name                          = uid
    doc.ups_state                     = state
    doc.priority                      = priority
    doc.scheduled_datetime            = scheduled_dt
    doc.modality                      = modality
    doc.scheduled_station_aet         = aet
    doc.scheduled_station_name        = station_name
    doc.scheduled_station_class_code  = station_class_code
    doc.requested_procedure_id = procedure_id
    doc.accession_number       = accession
    doc.protocol_name          = protocol
    doc.procedure_description  = description
    doc.patient_id             = patient_id
    doc.patient_name           = patient_name
    doc.patient_birth_date     = patient_dob
    doc.patient_sex            = patient_sex
    doc.transaction_uid        = transaction_uid or ""
    # Marked "pending" until a successful N-CREATE reaches dcm4chee-arc.
    # assign_workitem() performs a late push automatically on 404.
    doc.ups_sync_status        = "pending"
    doc.flags.ignore_permissions = True
    doc.flags.sync_import        = True   # bypass state-machine on initial insert
    doc.insert()
    print(f"  ✓  [{state:12s}]  {patient_name:22s}  →  {aet}")
    return doc, True


def _event_exists(ups_uid, event_type):
    return bool(frappe.db.exists(
        "UPS Event", {"ups_instance": ups_uid, "event_type": event_type}
    ))


def _add_event(doc, event_type, old_state, new_state, actor_aet,
               details, timestamp=None, http_status=200, transaction_uid=None):
    event = frappe.new_doc("UPS Event")
    event.ups_instance    = doc.name
    event.event_type      = event_type
    event.actor           = "Administrator"
    event.actor_aet       = actor_aet
    event.event_timestamp = timestamp or now_datetime()
    event.old_state       = old_state
    event.new_state       = new_state
    event.transaction_uid = transaction_uid or getattr(doc, "transaction_uid", None) or ""
    event.details         = details
    event.http_status     = http_status
    event.flags.ignore_permissions = True
    event.insert()


def _dicomweb_available():
    """Return True only when dcm4chee responds within 2 s."""
    try:
        import socket
        import urllib.parse
        import requests as _req
        url = frappe.db.get_single_value("UPS Integration Settings", "ups_rs_url")
        if not url:
            return False
        parsed = urllib.parse.urlparse(url)
        host   = parsed.hostname or "localhost"
        port   = parsed.port or 8080
        sock   = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        if result != 0:
            print(f"  ⚠  dcm4chee unreachable ({host}:{port}) — skipping DICOM push")
            return False
        return True
    except Exception:
        return False


def _build_dicom_payload(uid, priority, scheduled_dt, modality, aet,
                         patient_id, patient_name, patient_dob, patient_sex,
                         accession, proc_id, protocol,
                         station_class_code=None):
    # Build a minimal DICOM+JSON dataset for UPS N-CREATE.
    # Tag references:
    #   00741000  Procedure Step State  CS  -> SCHEDULED
    #   00741200  UPS Priority  CS
    #   00741204  Procedure Step Label  LO  (required by dcm4chee)
    #   00404041  Input Readiness State  CS  -> READY
    #   00404005  Scheduled Procedure Step Start DateTime  DT
    #   00404025  Scheduled Station Name Code Sequence  SQ  (specific station)
    #   00404026  Scheduled Station Class Code Sequence  SQ  (pool / class routing)
    #   00404018  SQ  Workitem Code Sequence
    #   001000xx  Patient demographics
    #   00080050  Accession Number
    #   00401001  Requested Procedure ID
    #   00181030  Protocol Name
    if isinstance(scheduled_dt, datetime):
        dt_str = scheduled_dt.strftime("%Y%m%d%H%M%S.000000")
    else:
        raw = str(scheduled_dt).replace("-", "").replace(":", "").replace(" ", "")
        dt_str = raw[:14].ljust(14, "0") + ".000000"
    dob_str = patient_dob.replace("-", "") if patient_dob else ""

    # Resolve station name and class code from AE Mapping.
    ae_map = frappe.db.get_value(
        "AE Mapping", aet,
        ["station_name", "display_name", "station_class_code"],
        as_dict=True,
    ) or {}
    station_code    = ae_map.get("station_name") or aet
    station_meaning = ae_map.get("display_name") or station_code
    if station_class_code is None:
        station_class_code = ae_map.get("station_class_code") or ""

    return {
        "00741000": {"vr": "CS", "Value": ["SCHEDULED"]},
        "00741200": {"vr": "CS", "Value": [priority]},
        "00741204": {"vr": "LO", "Value": [protocol]},
        "00404041": {"vr": "CS", "Value": ["READY"]},
        "00404005": {"vr": "DT", "Value": [dt_str]},
        "00404025": {                  # Scheduled Station Name Code Sequence (0040,4025)
            "vr": "SQ",
            "Value": [{
                "00080100": {"vr": "SH", "Value": [station_code]},
                "00080102": {"vr": "SH", "Value": ["LOCAL"]},
                "00080104": {"vr": "LO", "Value": [station_meaning]},
            }],
        },
        **({                           # Scheduled Station Class Code Sequence (0040,4026)
            "00404026": {
                "vr": "SQ",
                "Value": [{
                    "00080100": {"vr": "SH", "Value": [station_class_code]},
                    "00080102": {"vr": "SH", "Value": ["LOCAL"]},
                    "00080104": {"vr": "LO", "Value": [station_class_code]},
                }],
            }
        } if station_class_code else {}),
        "00404018": {
            "vr": "SQ",
            "Value": [{
                "00080100": {"vr": "SH", "Value": ["121726"]},
                "00080102": {"vr": "SH", "Value": ["DCM"]},
                "00080104": {"vr": "LO", "Value": ["Acquisition Protocol"]},
            }],
        },
        "00100020": {"vr": "LO", "Value": [patient_id]},
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": patient_name}]},
        "00100030": {"vr": "DA", "Value": [dob_str]},
        "00100040": {"vr": "CS", "Value": [patient_sex]},
        "00080050": {"vr": "SH", "Value": [accession]},
        "00401001": {"vr": "SH", "Value": [proc_id]},
        "00181030": {"vr": "LO", "Value": [protocol]},
    }


def _dicomweb_push(uid, attributes):
    from healthcare.integrations.dicomweb_client import (
        ConflictError, DICOMwebClient, ServerError, UPSClientError,
    )
    try:
        DICOMwebClient().create_workitem(uid, attributes)
        frappe.db.set_value("UPS Instance", uid, "ups_sync_status", "synced", update_modified=False)
        print(f"    -> dcm4chee N-CREATE OK  (...{uid[-10:]})")
        return True
    except ConflictError:
        frappe.db.set_value("UPS Instance", uid, "ups_sync_status", "synced", update_modified=False)
        print(f"    -> dcm4chee: workitem already exists (...{uid[-10:]})")
        return True
    except (ServerError, UPSClientError) as exc:
        print(f"    ! dcm4chee N-CREATE failed: {exc}")
        return False


def _dicomweb_change_state(uid, new_state, transaction_uid):
    from healthcare.integrations.dicomweb_client import (
        BadRequestError, ConflictError, DICOMwebClient,
        NotFoundError, ServerError, UPSClientError,
    )
    try:
        DICOMwebClient().change_state(uid, new_state, transaction_uid)
        print(f"    -> dcm4chee state -> {new_state} OK  (...{uid[-10:]})")
        return True
    except (NotFoundError, ConflictError, BadRequestError):
        return True
    except (ServerError, UPSClientError) as exc:
        print(f"    ! dcm4chee state change failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# UC1 — Pull Workflow  (§50.4.2.1)
#
# Scenario: CT Chest AI Pulmonology — Task Performer polls (queries) the Task
# Manager for workitems assigned to its AET (CT-AI-PULM) and claims them.
# Steps: Create → Assign → Pull (query+get) → Claim → Retrieve Input →
#        Store Results → Update → Complete.
# ─────────────────────────────────────────────────────────────────────────────

def _seed_uc1(dcm4chee):
    print("\n── UC1: Pull Workflow — CT Pulmonology AI ───────────────────────────")

    # ── Garcia: SCHEDULED (assigned, not yet claimed by CT-AI-PULM) ─────────
    t = _today_at(8, 0)
    garcia, garcia_new = _create_ups(
        uid           = WORKITEM_UIDS["GARCIA"],
        state         = "SCHEDULED",
        priority      = "MEDIUM",
        patient_id    = "PT-20001",
        patient_name  = "Garcia^Maria",
        patient_dob   = "1982-07-14",
        patient_sex   = "F",
        procedure_id  = "AI-20001",
        accession     = "ACC-20001",
        protocol      = "CT-CHEST-AI-PULM",
        description   = "AI: CT Chest — pulmonary nodule detection (scheduled, awaiting pull)",
        modality      = "CT",
        aet           = "CT-AI-PULM",
        station_name  = "CT-AI-PULM",
        scheduled_dt  = t,
    )
    if garcia_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["GARCIA"],
            _build_dicom_payload(
                WORKITEM_UIDS["GARCIA"], "MEDIUM", t, "CT", "CT-AI-PULM",
                "PT-20001", "Garcia^Maria", "1982-07-14", "F",
                "ACC-20001", "AI-20001", "CT-CHEST-AI-PULM",
            ),
        )
    if not _event_exists(WORKITEM_UIDS["GARCIA"], "CREATE"):
        _add_event(
            garcia, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = (
                "[UC1 §50.4.2.1 Step 1] Task Requestor (RIS/UPS-PORTAL) created AI "
                "Inference Request via Create UPS Workitem [RAD-80]. "
                "Workitem code: (126100, DCM, 'Real-world value map used for RT dose'). "
                "Input: CT chest series ACC-20001, WADO-RS via [RAD-107]. "
                "Output destination: DCM4CHEE (PACS/VNA). "
                "Task Requestor subscribed to workitem events (N-ACTION SUBSCRIBE)."
            ),
            timestamp   = t - timedelta(minutes=10),
            http_status = 201,
        )
    if not _event_exists(WORKITEM_UIDS["GARCIA"], "REASSIGN"):
        _add_event(
            garcia, "REASSIGN", "SCHEDULED", "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = (
                "[UC1 §50.4.2.1 Step 2] Task Manager assigned workitem to CT-AI-PULM "
                "by setting Scheduled Station Name Code Sequence (0040,4025). "
                "Send UPS Notification [RAD-87] → Task Requestor: status=SCHEDULED. "
                "CT-AI-PULM will query via Station-Based Query [RAD-81] when ready."
            ),
            timestamp   = t - timedelta(minutes=8),
            http_status = 200,
        )

    # ── Hernandez: IN PROGRESS (claimed by CT-AI-PULM via Pull) ─────────────
    t_sched = _today_at(8, 30)
    t_pull  = t_sched + timedelta(minutes=12)
    t_claim = t_pull  + timedelta(minutes=2)
    hernandez, hern_new = _create_ups(
        uid             = WORKITEM_UIDS["HERNANDEZ"],
        state           = "IN PROGRESS",
        priority        = "HIGH",
        patient_id      = "PT-20002",
        patient_name    = "Hernandez^Carlos",
        patient_dob     = "1966-03-22",
        patient_sex     = "M",
        procedure_id    = "AI-20002",
        accession       = "ACC-20002",
        protocol        = "CT-CHEST-AI-PULM",
        description     = "AI: CT Chest — pulmonary embolism detection (in progress)",
        modality        = "CT",
        aet             = "CT-AI-PULM",
        station_name    = "CT-AI-PULM",
        scheduled_dt    = t_sched,
        transaction_uid = TRANSACTION_UIDS["HERNANDEZ"],
    )
    if hern_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["HERNANDEZ"],
            _build_dicom_payload(
                WORKITEM_UIDS["HERNANDEZ"], "HIGH", t_sched, "CT", "CT-AI-PULM",
                "PT-20002", "Hernandez^Carlos", "1966-03-22", "M",
                "ACC-20002", "AI-20002", "CT-CHEST-AI-PULM",
            ),
        )
        _dicomweb_change_state(
            WORKITEM_UIDS["HERNANDEZ"], "IN PROGRESS", TRANSACTION_UIDS["HERNANDEZ"]
        )
    if not _event_exists(WORKITEM_UIDS["HERNANDEZ"], "CREATE"):
        _add_event(
            hernandez, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = "[UC1 Step 1] Task Requestor created AI Inference Request [RAD-80]. Priority HIGH (suspected PE on CTA).",
            timestamp   = t_sched - timedelta(minutes=5),
            http_status = 201,
        )
    if not _event_exists(WORKITEM_UIDS["HERNANDEZ"], "REASSIGN"):
        _add_event(
            hernandez, "REASSIGN", "SCHEDULED", "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = "[UC1 Step 2] Task Manager assigned to CT-AI-PULM. Send UPS Notification [RAD-87] → Task Requestor.",
            timestamp   = t_sched - timedelta(minutes=3),
            http_status = 200,
        )
    if not _event_exists(WORKITEM_UIDS["HERNANDEZ"], "CLAIM"):
        _add_event(
            hernandez, "CLAIM", "SCHEDULED", "IN PROGRESS",
            actor_aet       = "CT-AI-PULM",
            details         = (
                "[UC1 §50.4.2.1 Steps 3–4] CT-AI-PULM issued Station-Based Query UPS "
                "Workitem [RAD-81] (filter: ScheduledStationNameCodeSequence=CT-AI-PULM). "
                "Workitem UID returned. Task Performer retrieved full workitem via Get UPS "
                "Workitem [RAD-83], then claimed via Claim UPS Workitem [RAD-84]. "
                "Task Manager locked workitem, set status IN PROGRESS, returned Transaction UID. "
                "CT-AI-PULM now retrieving referenced input data via WADO-RS [RAD-107]."
            ),
            timestamp       = t_claim,
            http_status     = 200,
            transaction_uid = TRANSACTION_UIDS["HERNANDEZ"],
        )

    # ── Ibrahim: COMPLETED (full cycle done) ─────────────────────────────────
    t_sched    = _today_at(7, 0)
    t_pull     = t_sched  + timedelta(minutes=5)
    t_claim    = t_pull   + timedelta(minutes=1)
    t_retrieve = t_claim  + timedelta(minutes=3)
    t_update   = t_retrieve + timedelta(minutes=8)
    t_complete = t_update + timedelta(minutes=1)
    ibrahim, ibr_new = _create_ups(
        uid             = WORKITEM_UIDS["IBRAHIM"],
        state           = "COMPLETED",
        priority        = "MEDIUM",
        patient_id      = "PT-20003",
        patient_name    = "Ibrahim^Fatima",
        patient_dob     = "1959-11-30",
        patient_sex     = "F",
        procedure_id    = "AI-20003",
        accession       = "ACC-20003",
        protocol        = "CT-CHEST-AI-PULM",
        description     = "AI: CT Chest — lung nodule characterisation (completed)",
        modality        = "CT",
        aet             = "CT-AI-PULM",
        station_name    = "CT-AI-PULM",
        scheduled_dt    = t_sched,
        transaction_uid = TRANSACTION_UIDS["IBRAHIM"],
    )
    if ibr_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["IBRAHIM"],
            _build_dicom_payload(
                WORKITEM_UIDS["IBRAHIM"], "MEDIUM", t_sched, "CT", "CT-AI-PULM",
                "PT-20003", "Ibrahim^Fatima", "1959-11-30", "F",
                "ACC-20003", "AI-20003", "CT-CHEST-AI-PULM",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["IBRAHIM"], "IN PROGRESS", TRANSACTION_UIDS["IBRAHIM"])
        _dicomweb_change_state(WORKITEM_UIDS["IBRAHIM"], "COMPLETED",   TRANSACTION_UIDS["IBRAHIM"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL", t_sched - timedelta(minutes=5),
         "[UC1 Step 1] Task Requestor created AI Inference Request [RAD-80]. Input: ACC-20003."),
        ("REASSIGN", "SCHEDULED",   "SCHEDULED",   "UPS-PORTAL", t_sched - timedelta(minutes=3),
         "[UC1 Step 2] Task Manager assigned to CT-AI-PULM."),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "CT-AI-PULM", t_claim,
         "[UC1 Step 3] CT-AI-PULM queried [RAD-81], retrieved [RAD-83], claimed [RAD-84]. "
         "Transaction UID returned. Input data retrieval started via WADO-RS [RAD-107]."),
        ("UPDATE",   "IN PROGRESS", "IN PROGRESS", "CT-AI-PULM", t_update,
         "[UC1 Step 6] CT-AI-PULM stored AI results (DICOM SR + structured report) to PACS "
         "via [RAD-108]. Updated UPS Performed Procedure Information with output location, "
         "performed AI procedure, algorithm identity. Update UPS Workitem [RAD-84]."),
        ("COMPLETE", "IN PROGRESS", "COMPLETED",   "CT-AI-PULM", t_complete,
         "[UC1 Step 7] CT-AI-PULM completed workitem [RAD-85] → status COMPLETED. "
         "Task Manager sent Send UPS Notification [RAD-87] → Task Requestor. "
         "Task Requestor retrieved final state via Get UPS Workitem [RAD-83] and "
         "unsubscribed [N-ACTION UNSUBSCRIBE]."),
    ]:
        if not _event_exists(WORKITEM_UIDS["IBRAHIM"], ev):
            _add_event(ibrahim, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["IBRAHIM"] if ev != "CREATE" else None)


# ─────────────────────────────────────────────────────────────────────────────
# UC2 — Triggered Pull Workflow  (§50.4.2.2)
#
# Scenario: MR Brain AI — Task Performer subscribes via WebSocket (Open Event
# Channel [RAD-109]); Task Manager notifies (Send UPS Notification [RAD-87])
# when workitem is assigned; performer pulls and claims the notified workitem.
# ─────────────────────────────────────────────────────────────────────────────

def _seed_uc2(dcm4chee):
    print("\n── UC2: Triggered Pull Workflow — MR Brain AI ───────────────────────")

    # ── Johnson: SCHEDULED (notification sent, claim pending) ────────────────
    t = _today_at(9, 0)
    johnson, john_new = _create_ups(
        uid          = WORKITEM_UIDS["JOHNSON"],
        state        = "SCHEDULED",
        priority     = "MEDIUM",
        patient_id   = "PT-20004",
        patient_name = "Johnson^Kevin",
        patient_dob  = "1974-05-18",
        patient_sex  = "M",
        procedure_id = "AI-20004",
        accession    = "ACC-20004",
        protocol     = "MR-BRAIN-AI-STROKE",
        description  = "AI: Brain MRI — stroke lesion segmentation (notified, awaiting claim)",
        modality     = "MR",
        aet          = "MR-AI-BRAIN",
        station_name = "MR-AI-BRAIN",
        scheduled_dt = t,
    )
    if john_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["JOHNSON"],
            _build_dicom_payload(
                WORKITEM_UIDS["JOHNSON"], "MEDIUM", t, "MR", "MR-AI-BRAIN",
                "PT-20004", "Johnson^Kevin", "1974-05-18", "M",
                "ACC-20004", "AI-20004", "MR-BRAIN-AI-STROKE",
            ),
        )
    if not _event_exists(WORKITEM_UIDS["JOHNSON"], "CREATE"):
        _add_event(
            johnson, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = (
                "[UC2 §50.4.2.2 Step 1] Task Requestor created AI Inference Request [RAD-80] "
                "for stroke lesion segmentation. Input: DWI + ADC series from ACC-20004."
            ),
            timestamp   = t - timedelta(minutes=8),
            http_status = 201,
        )
    if not _event_exists(WORKITEM_UIDS["JOHNSON"], "REASSIGN"):
        _add_event(
            johnson, "REASSIGN", "SCHEDULED", "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = (
                "[UC2 Step 2] Task Manager assigned to MR-AI-BRAIN. "
                "[UC2 §50.4.2.2 Step 3: Triggered Pull] MR-AI-BRAIN has an open WebSocket "
                "(Open Event Channel [RAD-109]). Task Manager delivered Send UPS Notification "
                "[RAD-87] via WebSocket with workitem UID and assigned AETitle. "
                "MR-AI-BRAIN acknowledged notification; Get UPS Workitem [RAD-83] in progress. "
                "Claim expected imminently."
            ),
            timestamp   = t - timedelta(minutes=5),
            http_status = 200,
        )

    # ── Kim: IN PROGRESS (claimed after WebSocket notification) ──────────────
    t_sched = _today_at(8, 0)
    t_notif = t_sched + timedelta(minutes=3)
    t_claim = t_notif + timedelta(seconds=15)
    kim, kim_new = _create_ups(
        uid             = WORKITEM_UIDS["KIM"],
        state           = "IN PROGRESS",
        priority        = "HIGH",
        patient_id      = "PT-20005",
        patient_name    = "Kim^Jin",
        patient_dob     = "1977-09-04",
        patient_sex     = "F",
        procedure_id    = "AI-20005",
        accession       = "ACC-20005",
        protocol        = "MR-BRAIN-AI-TUMOR",
        description     = "AI: Brain MRI — glioma grading (claimed after triggered pull)",
        modality        = "MR",
        aet             = "MR-AI-BRAIN",
        station_name    = "MR-AI-BRAIN",
        scheduled_dt    = t_sched,
        transaction_uid = TRANSACTION_UIDS["KIM"],
    )
    if kim_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["KIM"],
            _build_dicom_payload(
                WORKITEM_UIDS["KIM"], "HIGH", t_sched, "MR", "MR-AI-BRAIN",
                "PT-20005", "Kim^Jin", "1977-09-04", "F",
                "ACC-20005", "AI-20005", "MR-BRAIN-AI-TUMOR",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["KIM"], "IN PROGRESS", TRANSACTION_UIDS["KIM"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL", t_sched - timedelta(minutes=5),
         "[UC2 Step 1] Task Requestor created AI Inference Request [RAD-80]. Glioma grading task. Input: T1+T2+FLAIR ACC-20005."),
        ("REASSIGN", "SCHEDULED",   "SCHEDULED",   "UPS-PORTAL", t_sched - timedelta(minutes=2),
         "[UC2 Step 2] Task Manager assigned to MR-AI-BRAIN, triggered WebSocket notification (phase: Subscribe+Notify)."),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "MR-AI-BRAIN", t_claim,
         (
             "[UC2 §50.4.2.2 Step 3] MR-AI-BRAIN received Send UPS Notification [RAD-87] "
             "via open WebSocket (Open Event Channel [RAD-109]) within 15 s of assignment. "
             "MR-AI-BRAIN invoked Get UPS Workitem [RAD-83] using the notified UID, then "
             "claimed via Claim UPS Workitem [RAD-82]. Task Manager locked workitem, set "
             "status IN PROGRESS, returned Transaction UID. "
             "Task Requestor notified: status=IN PROGRESS via [RAD-87]."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["KIM"], ev):
            _add_event(kim, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["KIM"] if ev != "CREATE" else None)


# ─────────────────────────────────────────────────────────────────────────────
# UC3 — Push Workflow  (§50.4.2.3)
#
# Scenario: Abdominal CT AI — Task Manager assigns and pushes the workitem
# directly to the Task Performer (Create UPS Workitem [RAD-80] on performer's
# endpoint).  The local Frappe record mirrors Workitem X (at Task Manager).
# Workitem Y (created on CT-AI-ABD) is referenced in event details.
# ─────────────────────────────────────────────────────────────────────────────

def _seed_uc3(dcm4chee):
    print("\n── UC3: Push Workflow — Abdominal CT AI ─────────────────────────────")

    t_create   = _today_at(7, 0)
    t_push_y   = t_create  + timedelta(minutes=2)
    t_update   = t_push_y  + timedelta(minutes=15)
    t_complete = t_update  + timedelta(minutes=2)
    # Workitem Y UID — the copy pushed directly to CT-AI-ABD
    uid_y = _BASE + "0006Y"

    lee, lee_new = _create_ups(
        uid             = WORKITEM_UIDS["LEE"],
        state           = "COMPLETED",
        priority        = "MEDIUM",
        patient_id      = "PT-20006",
        patient_name    = "Lee^Thomas",
        patient_dob     = "1961-02-17",
        patient_sex     = "M",
        procedure_id    = "AI-20006",
        accession       = "ACC-20006",
        protocol        = "CT-ABD-AI-ORGAN-SEG",
        description     = "AI: CT Abdomen — organ segmentation for RT planning (push workflow, completed)",
        modality        = "CT",
        aet             = "CT-AI-ABD",
        station_name    = "CT-AI-ABD",
        scheduled_dt    = t_create,
        transaction_uid = TRANSACTION_UIDS["LEE"],
    )
    if lee_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["LEE"],
            _build_dicom_payload(
                WORKITEM_UIDS["LEE"], "MEDIUM", t_create, "CT", "CT-AI-ABD",
                "PT-20006", "Lee^Thomas", "1961-02-17", "M",
                "ACC-20006", "AI-20006", "CT-ABD-AI-ORGAN-SEG",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["LEE"], "IN PROGRESS", TRANSACTION_UIDS["LEE"])
        _dicomweb_change_state(WORKITEM_UIDS["LEE"], "COMPLETED",   TRANSACTION_UIDS["LEE"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL", t_create,
         (
             "[UC3 §50.4.2.3 Create Workitem] Task Requestor sent Create UPS Workitem [RAD-80] "
             f"→ Task Manager. Task Manager created Workitem X ({WORKITEM_UIDS['LEE'][-6:]}…). "
             "Workitem UID returned to Task Requestor."
         )),
        ("REASSIGN", "SCHEDULED",   "SCHEDULED",   "UPS-PORTAL", t_create + timedelta(seconds=30),
         (
             f"[UC3 Assign Workitem] Task Manager assigned Workitem X to CT-AI-ABD. "
             f"[Push Workitem] Task Manager pushed copy as Workitem Y (UID …{uid_y[-6:]}) "
             "directly to CT-AI-ABD via Create UPS Workitem [RAD-80] on CT-AI-ABD's endpoint. "
             "Task Manager opened Optional Event Channel [RAD-109] on CT-AI-ABD to monitor Y. "
             "Send UPS Notification [RAD-87] → Task Requestor: Workitem X claimed."
         )),
        ("UPDATE",   "IN PROGRESS", "IN PROGRESS", "CT-AI-ABD",  t_update,
         (
             "[UC3 Step 4–6] CT-AI-ABD retrieved input CT series via WADO-RS [RAD-107]. "
             "Organ segmentation complete (liver, kidneys, spleen, bowel). "
             "AI results stored to PACS via STOW-RS [RAD-108]. "
             f"CT-AI-ABD updated Workitem Y ({uid_y[-6:]}…) with output location and "
             "Performed Workitem Code via Update UPS Workitem [RAD-84]."
         )),
        ("COMPLETE", "IN PROGRESS", "COMPLETED",   "CT-AI-ABD",  t_complete,
         (
             f"[UC3 Complete UPS Workitem] CT-AI-ABD completed Workitem Y ({uid_y[-6:]}…) "
             "via Send UPS Notification [RAD-87] → Task Manager. "
             "Task Manager retrieved Workitem Y results via Get UPS Workitem [RAD-83], "
             f"populated Workitem X ({WORKITEM_UIDS['LEE'][-6:]}…) with results, "
             "set Workitem X status to COMPLETED. "
             "Send UPS Notification [RAD-87] → Task Requestor: Workitem X complete."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["LEE"], ev):
            _add_event(lee, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["LEE"] if ev != "CREATE" else None)


# ─────────────────────────────────────────────────────────────────────────────
# UC4 — Exception Management  (§50.4.2.4)
#
# Sub-cases seeded:
#  4a — Pre-claim rejection  (Martinez — CT-AI-PULM rejects: no resources)
#  4b — Post-claim CANCELED  (Nelson    — CT-AI-PULM failed mid-processing)
#  4c — Partial completion   (Okafor    — primary results OK, secondary incomplete)
# ─────────────────────────────────────────────────────────────────────────────

def _seed_uc4(dcm4chee):
    print("\n── UC4: Exception Management ────────────────────────────────────────")

    # ── UC4a — Pre-claim rejection (Martinez) ────────────────────────────────
    t = _today_at(10, 0)
    martinez, mart_new = _create_ups(
        uid          = WORKITEM_UIDS["MARTINEZ"],
        state        = "CANCELED",
        priority     = "MEDIUM",
        patient_id   = "PT-20007",
        patient_name = "Martinez^Elena",
        patient_dob  = "1987-12-03",
        patient_sex  = "F",
        procedure_id = "AI-20007",
        accession    = "ACC-20007",
        protocol     = "CT-CHEST-AI-PULM",
        description  = "AI: CT Chest — pre-claim rejection (no computational resources)",
        modality     = "CT",
        aet          = "CT-AI-PULM",
        station_name = "CT-AI-PULM",
        scheduled_dt = t,
    )
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,        "SCHEDULED", "UPS-PORTAL",  t - timedelta(minutes=10),
         "[UC4a §50.4.2.4(1)] Task Requestor created AI Inference Request [RAD-80]."),
        ("REASSIGN", "SCHEDULED", "SCHEDULED", "UPS-PORTAL",  t - timedelta(minutes=8),
         "[UC4a Step 2] Task Manager assigned to CT-AI-PULM. Performer notified via [RAD-87] / query."),
        ("CANCEL",   "SCHEDULED", "CANCELED",  "CT-AI-PULM",  t - timedelta(minutes=5),
         (
             "[UC4a §50.4.2.4(1) Workitem Rejection — before claiming] "
             "CT-AI-PULM retrieved workitem [RAD-83] but determined it cannot process: "
             "insufficient GPU memory for this scan size. "
             "CT-AI-PULM sent Request UPS Workitem Cancellation [RAD-88] with "
             "Procedure Step Discontinuation Reason (110530, DCM, 'Workitem assignment "
             "rejected by assigned resource'). "
             "Task Manager acted: no other CT-AI performer available → cancelled workitem. "
             "Send UPS Notification [RAD-87] → Watcher/Task Requestor: status=CANCELED."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["MARTINEZ"], ev):
            _add_event(martinez, ev, os, ns, aet_, det, timestamp=ts)

    # ── UC4b — Post-claim CANCELED (Nelson) ──────────────────────────────────
    t_sched    = _today_at(10, 30)
    t_claim    = t_sched + timedelta(minutes=5)
    t_fail     = t_claim + timedelta(minutes=12)
    nelson, nel_new = _create_ups(
        uid             = WORKITEM_UIDS["NELSON"],
        state           = "CANCELED",
        priority        = "MEDIUM",
        patient_id      = "PT-20008",
        patient_name    = "Nelson^David",
        patient_dob     = "1952-06-09",
        patient_sex     = "M",
        procedure_id    = "AI-20008",
        accession       = "ACC-20008",
        protocol        = "CT-CHEST-AI-PULM",
        description     = "AI: CT Chest — post-claim cancellation (objects incorrectly formatted)",
        modality        = "CT",
        aet             = "CT-AI-PULM",
        station_name    = "CT-AI-PULM",
        scheduled_dt    = t_sched,
        transaction_uid = TRANSACTION_UIDS["NELSON"],
    )
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL",  t_sched - timedelta(minutes=5),
         "[UC4b §50.4.2.4(2)] Task Requestor created AI Inference Request [RAD-80]."),
        ("REASSIGN", "SCHEDULED",   "SCHEDULED",   "UPS-PORTAL",  t_sched - timedelta(minutes=3),
         "[UC4b] Task Manager assigned to CT-AI-PULM. Notification sent."),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "CT-AI-PULM",  t_claim,
         "[UC4b] CT-AI-PULM queried [RAD-81], retrieved [RAD-83], claimed [RAD-84]. Processing started."),
        ("CANCEL",   "IN PROGRESS", "CANCELED",    "CT-AI-PULM",  t_fail,
         (
             "[UC4b §50.4.2.4(2) Workitem Cancellation — after claiming] "
             "CT-AI-PULM retrieved DICOM series from PACS but encountered encoding errors: "
             "CT series stored with non-standard private tags incompatible with inference pipeline. "
             "CT-AI-PULM sent Complete UPS Workitem [RAD-85] with CANCELLED state and "
             "Procedure Step Discontinuation Reason (110521, DCM, "
             "'Objects incorrectly formatted'). "
             "Task Manager updated workitem to CANCELED state and sent notifications [RAD-87]. "
             "A new workitem may be created after re-encoding the source images."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["NELSON"], ev):
            _add_event(nelson, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["NELSON"] if ev not in ("CREATE", "REASSIGN") else None)

    # ── UC4c — Partial completion (Okafor) ───────────────────────────────────
    t_sched    = _today_at(11, 0)
    t_claim    = t_sched    + timedelta(minutes=4)
    t_update   = t_claim    + timedelta(minutes=10)
    t_complete = t_update   + timedelta(minutes=1)
    okafor, oka_new = _create_ups(
        uid             = WORKITEM_UIDS["OKAFOR"],
        state           = "COMPLETED",
        priority        = "LOW",
        patient_id      = "PT-20009",
        patient_name    = "Okafor^Amara",
        patient_dob     = "1980-08-25",
        patient_sex     = "F",
        procedure_id    = "AI-20009",
        accession       = "ACC-20009",
        protocol        = "CT-CHEST-AI-PULM",
        description     = "AI: CT Chest — partial completion (primary nodule map OK, CAD score incomplete)",
        modality        = "CT",
        aet             = "CT-AI-PULM",
        station_name    = "CT-AI-PULM",
        scheduled_dt    = t_sched,
        transaction_uid = TRANSACTION_UIDS["OKAFOR"],
    )
    if oka_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["OKAFOR"],
            _build_dicom_payload(
                WORKITEM_UIDS["OKAFOR"], "LOW", t_sched, "CT", "CT-AI-PULM",
                "PT-20009", "Okafor^Amara", "1980-08-25", "F",
                "ACC-20009", "AI-20009", "CT-CHEST-AI-PULM",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["OKAFOR"], "IN PROGRESS", TRANSACTION_UIDS["OKAFOR"])
        _dicomweb_change_state(WORKITEM_UIDS["OKAFOR"], "COMPLETED",   TRANSACTION_UIDS["OKAFOR"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL",  t_sched - timedelta(minutes=5),
         "[UC4c §50.4.2.4(3)] Task Requestor created AI Inference Request [RAD-80]."),
        ("REASSIGN", "SCHEDULED",   "SCHEDULED",   "UPS-PORTAL",  t_sched - timedelta(minutes=3),
         "[UC4c] Task Manager assigned to CT-AI-PULM."),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "CT-AI-PULM",  t_claim,
         "[UC4c] CT-AI-PULM claimed workitem [RAD-84]. Processing started."),
        ("UPDATE",   "IN PROGRESS", "IN PROGRESS", "CT-AI-PULM",  t_update,
         (
             "[UC4c §50.4.2.4(3) Workitem Complete — primary results available, some secondary missing] "
             "Primary output (nodule segmentation overlay DICOM SEG) stored to PACS [RAD-108]. "
             "Secondary output (CAD malignancy score) could not be generated: "
             "insufficient contrast phase in this study. "
             "CT-AI-PULM communicated partial results via Update UPS Workitem [RAD-84]: "
             "Performed Workitem Code Sequence (0040,4019) reflects what was actually performed "
             "(nodule detection only, not full characterisation as originally scheduled). "
             "Output Information Sequence populated with the nodule overlay reference."
         )),
        ("COMPLETE", "IN PROGRESS", "COMPLETED",   "CT-AI-PULM",  t_complete,
         (
             "[UC4c] CT-AI-PULM sent Complete UPS Workitem [RAD-85] with COMPLETE state "
             "(not CANCELLED) because the primary requested output was produced. "
             "Task Manager sent Send UPS Notification [RAD-87] → Task Requestor."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["OKAFOR"], ev):
            _add_event(okafor, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["OKAFOR"] if ev not in ("CREATE", "REASSIGN") else None)


# ─────────────────────────────────────────────────────────────────────────────
# UC5 — Proxied AI Models  (§50.4.2.5)
#
# Scenario: Chest X-ray pneumothorax detection — Task Performer "CXR-AI-PROX"
# acts as proxy, unwrapping DICOM inputs and orchestrating a chain of three
# proxied AI models: (1) image quality check, (2) pneumothorax detector,
# (3) size classifier.  Proxy assembles results into a DICOM SR + annotation.
# ─────────────────────────────────────────────────────────────────────────────

def _seed_uc5(dcm4chee):
    print("\n── UC5: Proxied AI Models — CXR Pneumothorax Proxy ─────────────────")

    t_sched    = _today_at(9, 30)
    t_claim    = t_sched    + timedelta(minutes=3)
    t_prox1    = t_claim    + timedelta(minutes=1)
    t_prox2    = t_prox1   + timedelta(minutes=2)
    t_prox3    = t_prox2   + timedelta(minutes=1)
    t_update   = t_prox3   + timedelta(minutes=1)
    t_complete = t_update   + timedelta(minutes=1)

    patel, pat_new = _create_ups(
        uid             = WORKITEM_UIDS["PATEL"],
        state           = "COMPLETED",
        priority        = "HIGH",
        patient_id      = "PT-20010",
        patient_name    = "Patel^Raj",
        patient_dob     = "1968-03-11",
        patient_sex     = "M",
        procedure_id    = "AI-20010",
        accession       = "ACC-20010",
        protocol        = "CXR-AI-PNEUMO-PROXY",
        description     = "AI: CXR — pneumothorax detection via proxy (3-model chain, completed)",
        modality        = "CR",
        aet             = "CXR-AI-PROX",
        station_name    = "CXR-AI-PROX",
        scheduled_dt    = t_sched,
        transaction_uid = TRANSACTION_UIDS["PATEL"],
    )
    if pat_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["PATEL"],
            _build_dicom_payload(
                WORKITEM_UIDS["PATEL"], "HIGH", t_sched, "CR", "CXR-AI-PROX",
                "PT-20010", "Patel^Raj", "1968-03-11", "M",
                "ACC-20010", "AI-20010", "CXR-AI-PNEUMO-PROXY",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["PATEL"], "IN PROGRESS", TRANSACTION_UIDS["PATEL"])
        _dicomweb_change_state(WORKITEM_UIDS["PATEL"], "COMPLETED",   TRANSACTION_UIDS["PATEL"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL",   t_sched - timedelta(minutes=8),
         "[UC5 §50.4.2.5] Task Requestor created AI Inference Request [RAD-80] for pneumothorax detection. Input: PA chest radiograph ACC-20010."),
        ("REASSIGN", "SCHEDULED",   "SCHEDULED",   "UPS-PORTAL",   t_sched - timedelta(minutes=5),
         "[UC5] Task Manager assigned to CXR-AI-PROX (proxy Task Performer)."),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "CXR-AI-PROX",  t_claim,
         "[UC5] CXR-AI-PROX claimed workitem [RAD-84]. Retrieving input CXR via WADO-RS [RAD-107]."),
        ("UPDATE",   "IN PROGRESS", "IN PROGRESS", "CXR-AI-PROX",  t_update,
         (
             "[UC5 §50.4.2.5 Proxied AI Models] CXR-AI-PROX orchestrated three-model chain: "
             f"(1) @{t_prox1.strftime('%H:%M:%S')} Image Quality Check model → 'adequate quality, PA view confirmed'. "
             f"(2) @{t_prox2.strftime('%H:%M:%S')} Pneumothorax Detector model → 'PRESENT, right-sided, 2.1 cm apical separation'. "
             f"(3) @{t_prox3.strftime('%H:%M:%S')} Size Classifier model → 'moderate (>2 cm), tension signs absent'. "
             "CXR-AI-PROX assembled DICOM SR (TID 1500) + DICOM SEG annotation, "
             "stored to PACS via STOW-RS [RAD-108]. "
             "Output Information Sequence (0040,4033) populated with SR + SEG references."
         )),
        ("COMPLETE", "IN PROGRESS", "COMPLETED",   "CXR-AI-PROX",  t_complete,
         (
             "[UC5] CXR-AI-PROX completed workitem [RAD-85]. "
             "Result: moderate right pneumothorax detected. "
             "Task Manager sent notification [RAD-87] → Task Requestor. "
             "STAT flag to be set by UC7 Reading Priority workflow."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["PATEL"], ev):
            _add_event(patel, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["PATEL"] if ev not in ("CREATE", "REASSIGN") else None)


# ─────────────────────────────────────────────────────────────────────────────
# UC6 — Inference with Verification  (§50.4.2.6)
#
# Scenario: Lung nodule CT — Task Manager decomposes the original workitem X
# into two sub-tasks: Y1 (inference by LU-AI-VERFY → results go to cache)
# and Y2 (verification by a human radiologist LU-HU-VERFY → results go to PACS).
# Both workitems are in the local mirror.  Y1=Quinn-Inference=COMPLETED, Y2=Quinn-Verify=IN PROGRESS.
# ─────────────────────────────────────────────────────────────────────────────

def _seed_uc6(dcm4chee):
    print("\n── UC6: Inference with Verification — Lung Nodule CT ────────────────")

    # ── Quinn-INF (Y1): Inference workitem — COMPLETED ────────────────────────
    t_y1_sched    = _today_at(8, 0)
    t_y1_claim    = t_y1_sched    + timedelta(minutes=2)
    t_y1_update   = t_y1_claim    + timedelta(minutes=25)
    t_y1_complete = t_y1_update   + timedelta(minutes=1)

    quinn_inf, qi_new = _create_ups(
        uid             = WORKITEM_UIDS["QUINN_INF"],
        state           = "COMPLETED",
        priority        = "MEDIUM",
        patient_id      = "PT-20011",
        patient_name    = "Quinn^Lisa",
        patient_dob     = "1964-10-08",
        patient_sex     = "F",
        procedure_id    = "AI-20011-INF",
        accession       = "ACC-20011",
        protocol        = "CT-LUNG-AI-NODULE-INF",
        description     = (
            f"AI: CT Lung Nodule — inference step Y1 (dest=VerificationCache; "
            f"ver. workitem Y2={WORKITEM_UIDS['QUINN_VER'][-6:]}…)"
        ),
        modality        = "CT",
        aet             = "LU-AI-VERFY",
        station_name    = "LU-AI-VERFY",
        scheduled_dt    = t_y1_sched,
        transaction_uid = TRANSACTION_UIDS["QUINN_INF"],
    )
    if qi_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["QUINN_INF"],
            _build_dicom_payload(
                WORKITEM_UIDS["QUINN_INF"], "MEDIUM", t_y1_sched, "CT", "LU-AI-VERFY",
                "PT-20011", "Quinn^Lisa", "1964-10-08", "F",
                "ACC-20011", "AI-20011-INF", "CT-LUNG-AI-NODULE-INF",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["QUINN_INF"], "IN PROGRESS", TRANSACTION_UIDS["QUINN_INF"])
        _dicomweb_change_state(WORKITEM_UIDS["QUINN_INF"], "COMPLETED",   TRANSACTION_UIDS["QUINN_INF"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL",  t_y1_sched - timedelta(minutes=5),
         (
             f"[UC6 §50.4.2.6] Task Manager created Inference Workitem Y1 "
             f"({WORKITEM_UIDS['QUINN_INF'][-6:]}…) by copying original request X. "
             "Output Destination revised → Verification Cache (IDC) instead of main PACS. "
             "Assigned inference step to LU-AI-VERFY."
         )),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "LU-AI-VERFY", t_y1_claim,
         "[UC6] LU-AI-VERFY claimed Y1. Retrieving CT lung series via WADO-RS [RAD-107]."),
        ("UPDATE",   "IN PROGRESS", "IN PROGRESS", "LU-AI-VERFY", t_y1_update,
         (
             "[UC6 Step 5] LU-AI-VERFY completed lung nodule detection: "
             "4 nodules found (3–9 mm range, Fleischner category III/IV). "
             "Results stored to Verification Cache [RAD-108]; "
             "results NOT yet available in main PACS. "
             "Output Information Sequence (0040,4033) → Verification Cache references."
         )),
        ("COMPLETE", "IN PROGRESS", "COMPLETED",   "LU-AI-VERFY", t_y1_complete,
         (
             "[UC6] LU-AI-VERFY completed Y1 [RAD-85]. "
             "Task Manager received completion notification [RAD-87]. "
             f"Task Manager created Verification Workitem Y2 ({WORKITEM_UIDS['QUINN_VER'][-6:]}…): "
             "Input = outputs of Y1 (from Verification Cache), "
             "Output Destination = main PACS, "
             "Assigned to LU-HU-VERFY (human radiologist)."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["QUINN_INF"], ev):
            _add_event(quinn_inf, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["QUINN_INF"] if ev != "CREATE" else None)

    # ── Quinn-VER (Y2): Verification workitem — IN PROGRESS ──────────────────
    t_y2_sched = t_y1_complete + timedelta(seconds=30)
    t_y2_claim = t_y2_sched   + timedelta(minutes=8)

    quinn_ver, qv_new = _create_ups(
        uid             = WORKITEM_UIDS["QUINN_VER"],
        state           = "IN PROGRESS",
        priority        = "MEDIUM",
        patient_id      = "PT-20011",
        patient_name    = "Quinn^Lisa",
        patient_dob     = "1964-10-08",
        patient_sex     = "F",
        procedure_id    = "AI-20011-VER",
        accession       = "ACC-20011",
        protocol        = "CT-LUNG-AI-NODULE-VER",
        description     = (
            f"AI: CT Lung Nodule — verification step Y2 (human reviewer; "
            f"source=VerificationCache; inf. workitem Y1={WORKITEM_UIDS['QUINN_INF'][-6:]}…)"
        ),
        modality        = "CT",
        aet             = "LU-HU-VERFY",
        station_name    = "LU-HU-VERFY",
        scheduled_dt    = t_y2_sched,
        transaction_uid = TRANSACTION_UIDS["QUINN_VER"],
    )
    if qv_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["QUINN_VER"],
            _build_dicom_payload(
                WORKITEM_UIDS["QUINN_VER"], "MEDIUM", t_y2_sched, "CT", "LU-HU-VERFY",
                "PT-20011", "Quinn^Lisa", "1964-10-08", "F",
                "ACC-20011", "AI-20011-VER", "CT-LUNG-AI-NODULE-VER",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["QUINN_VER"], "IN PROGRESS", TRANSACTION_UIDS["QUINN_VER"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL",   t_y2_sched,
         (
             f"[UC6 §50.4.2.6] Task Manager created Verification Workitem Y2 "
             f"({WORKITEM_UIDS['QUINN_VER'][-6:]}…) after Y1 completion. "
             "Input Information Sequence (0040,4021) = Output Information Sequence of Y1 "
             "(Verification Cache references). "
             "Output Destination = main PACS/VNA. "
             "Workitem code = 'Human review of AI-generated lung nodule annotations'. "
             "Assigned to LU-HU-VERFY (radiologist)."
         )),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "LU-HU-VERFY",  t_y2_claim,
         (
             "[UC6] Human reviewer (LU-HU-VERFY) claimed Y2 [RAD-84]. "
             "Reviewing AI-generated nodule annotations from Verification Cache. "
             "Will accept, edit, or reject each annotation before distributing to main PACS."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["QUINN_VER"], ev):
            _add_event(quinn_ver, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["QUINN_VER"] if ev != "CREATE" else None)


# ─────────────────────────────────────────────────────────────────────────────
# UC7 — Reading Workflow Priority  (§50.4.2.7)
#
# Scenario: Critical finding — CT-AI-CRIT (Task Performer, grouped with
# Procedure Reporter) detects a large right pneumothorax.  It escalates the
# reading worklist priority via Procedure Update [RAD-13] and stores the result.
# ─────────────────────────────────────────────────────────────────────────────

def _seed_uc7(dcm4chee):
    print("\n── UC7: Reading Workflow Priority — Critical Finding Escalation ──────")

    t_sched    = _today_at(11, 20)
    t_claim    = t_sched    + timedelta(minutes=2)
    t_update   = t_claim    + timedelta(minutes=4)
    t_complete = t_update   + timedelta(minutes=1)
    t_escalate = t_complete + timedelta(seconds=10)

    rodriguez, rod_new = _create_ups(
        uid             = WORKITEM_UIDS["RODRIGUEZ"],
        state           = "COMPLETED",
        priority        = "HIGH",
        patient_id      = "PT-20013",
        patient_name    = "Rodriguez^Ana",
        patient_dob     = "1957-04-22",
        patient_sex     = "F",
        procedure_id    = "AI-20013",
        accession       = "ACC-20013",
        protocol        = "CT-CHEST-AI-CRIT",
        description     = "AI: CT Chest — critical finding: large right pneumothorax; priority escalated STAT",
        modality        = "CT",
        aet             = "CT-AI-CRIT",
        station_name    = "CT-AI-CRIT",
        scheduled_dt    = t_sched,
        transaction_uid = TRANSACTION_UIDS["RODRIGUEZ"],
    )
    if rod_new and dcm4chee:
        _dicomweb_push(
            WORKITEM_UIDS["RODRIGUEZ"],
            _build_dicom_payload(
                WORKITEM_UIDS["RODRIGUEZ"], "HIGH", t_sched, "CT", "CT-AI-CRIT",
                "PT-20013", "Rodriguez^Ana", "1957-04-22", "F",
                "ACC-20013", "AI-20013", "CT-CHEST-AI-CRIT",
            ),
        )
        _dicomweb_change_state(WORKITEM_UIDS["RODRIGUEZ"], "IN PROGRESS", TRANSACTION_UIDS["RODRIGUEZ"])
        _dicomweb_change_state(WORKITEM_UIDS["RODRIGUEZ"], "COMPLETED",   TRANSACTION_UIDS["RODRIGUEZ"])
    for ev, os, ns, aet_, ts, det in [
        ("CREATE",   None,          "SCHEDULED",   "UPS-PORTAL",  t_sched - timedelta(minutes=5),
         "[UC7 §50.4.2.7] Task Requestor created AI critical-finding Inference Request [RAD-80]."),
        ("REASSIGN", "SCHEDULED",   "SCHEDULED",   "UPS-PORTAL",  t_sched - timedelta(minutes=3),
         "[UC7] Task Manager assigned to CT-AI-CRIT."),
        ("CLAIM",    "SCHEDULED",   "IN PROGRESS", "CT-AI-CRIT",  t_claim,
         "[UC7] CT-AI-CRIT claimed workitem [RAD-84] via triggered-pull notification."),
        ("UPDATE",   "IN PROGRESS", "IN PROGRESS", "CT-AI-CRIT",  t_update,
         (
             "[UC7 §50.4.2.7 Reading Workflow Priority] CT-AI-CRIT completed inference. "
             "Finding: large right pneumothorax (>3 cm rim, 42% lung collapse). "
             "Result stored to PACS as DICOM SR (TID 1500) + DICOM annotation. "
             "CT-AI-CRIT, grouped with Procedure Reporter [RAD-13], sent "
             "Procedure Update [RAD-13] → Report Manager (RIS/worklist): "
             "abnormality=CRITICAL, category=PNEUMOTHORAX, "
             "ScheduledProcedureStepPriority escalated to STAT. "
             "Additional field: ActionableFindingCategory = (174730008, SCT, 'Pneumothorax'). "
             "Report Manager updated radiology reading worklist: Ms. Rodriguez moved to top. "
             "Attending physician paged via alerting system."
         )),
        ("COMPLETE", "IN PROGRESS", "COMPLETED",   "CT-AI-CRIT",  t_complete,
         (
             "[UC7] CT-AI-CRIT completed workitem [RAD-85]. "
             f"Total inference time: {(t_complete - t_claim).seconds}s. "
             "Task Requestor notified [RAD-87]. "
             "Radiologist on-call has STAT item at top of reading list."
         )),
    ]:
        if not _event_exists(WORKITEM_UIDS["RODRIGUEZ"], ev):
            _add_event(rodriguez, ev, os, ns, aet_, det, timestamp=ts,
                       transaction_uid=TRANSACTION_UIDS["RODRIGUEZ"] if ev not in ("CREATE", "REASSIGN") else None)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

def run():
    """
    Seed all 7 AIW-I §50.4.2 use cases.

    Idempotent — safe to call multiple times; existing records are left
    unchanged.
    """
    frappe.set_user("Administrator")
    print("\n═══ AIW-I §50.4.2 Use Cases — demo seed ════════════════════════════")

    _ensure_ai_ae_mappings()
    dcm4chee = _dicomweb_available()

    _seed_uc1(dcm4chee)
    _seed_uc2(dcm4chee)
    _seed_uc3(dcm4chee)
    _seed_uc4(dcm4chee)
    _seed_uc5(dcm4chee)
    _seed_uc6(dcm4chee)
    _seed_uc7(dcm4chee)

    frappe.db.commit()

    print("\n────────────────────────────────────────────────────────────────────")
    print("  UC1 Pull           Garcia   SCHEDULED  CT-AI-PULM (assigned, awaiting pull)")
    print("                     Hernandez IN PROGRESS CT-AI-PULM (claimed)")
    print("                     Ibrahim  COMPLETED  CT-AI-PULM (full cycle done)")
    print("  UC2 Triggered Pull Johnson  SCHEDULED  MR-AI-BRAIN (notification sent)")
    print("                     Kim      IN PROGRESS MR-AI-BRAIN (claimed via WebSocket)")
    print("  UC3 Push           Lee      COMPLETED  CT-AI-ABD  (push cycle done)")
    print("  UC4 Exception")
    print("    4a pre-claim     Martinez CANCELED   CT-AI-PULM (rejected: no resources)")
    print("    4b post-claim    Nelson   CANCELED   CT-AI-PULM (failed: bad encoding)")
    print("    4c partial       Okafor   COMPLETED  CT-AI-PULM (primary OK, secondary missing)")
    print("  UC5 Proxied AI     Patel    COMPLETED  CXR-AI-PROX (3-model chain)")
    print("  UC6 Verification")
    print("    inference Y1     Quinn    COMPLETED  LU-AI-VERFY (results in cache)")
    print("    verification Y2  Quinn    IN PROGRESS LU-HU-VERFY (human review)")
    print("  UC7 Priority       Rodriguez COMPLETED CT-AI-CRIT (STAT escalated)")
    print("════════════════════════════════════════════════════════════════════\n")


def teardown():
    """
    Remove all AIW-I §50.4.2 demo workitems, events, and AI AE Mappings.

    Idempotent — missing records are silently skipped.
    """
    frappe.set_user("Administrator")
    print("\n═══ AIW-I §50.4.2 Use Cases — teardown ════════════════════════════")

    dcm4chee = _dicomweb_available()

    for key, uid in WORKITEM_UIDS.items():
        if dcm4chee:
            state = frappe.db.get_value("UPS Instance", uid, "ups_state")
            if state == "SCHEDULED":
                _dicomweb_change_state(uid, "CANCELED", None)
            elif state == "IN PROGRESS":
                txn = frappe.db.get_value("UPS Instance", uid, "transaction_uid")
                _dicomweb_change_state(uid, "CANCELED", txn)

        if not frappe.db.exists("UPS Instance", uid):
            print(f"  —  Not found: {key}")
            continue
        events = frappe.get_list("UPS Event", filters={"ups_instance": uid}, pluck="name")
        for evt in events:
            frappe.delete_doc("UPS Event", evt, force=True, ignore_permissions=True)
        frappe.delete_doc("UPS Instance", uid, force=True, ignore_permissions=True)
        print(f"  ✗  Deleted {key} ({uid[-6:]}… + {len(events)} events)")

    # Remove AI AE Mappings seeded by this demo
    for ae in _AI_AE_TITLES:
        if frappe.db.exists("AE Mapping", ae):
            frappe.delete_doc("AE Mapping", ae, force=True, ignore_permissions=True)
            print(f"  ✗  Deleted AE Mapping: {ae}")

    frappe.db.commit()
    print("════════════════════════════════════════════════════════════════════\n")
