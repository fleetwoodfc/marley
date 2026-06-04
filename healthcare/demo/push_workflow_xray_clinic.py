"""
Demo seed script: Push Workflow – X-Ray Clinic
===============================================

Populates the local UPS Instance mirror with a realistic set of workitems
that illustrate the DICOM UPS Push workflow as described in slide 22 of
K-ODonnel_UPS-DICOM-Unified-Procedure-Step-Draft-V2.ppt.

Scenario
--------
The RIS (UPS-PORTAL AET) acts as the requester.  It creates (pushes)
workitems via N-CREATE for three digital radiography rooms:

  • DX-ROOM1 — DR X-Ray Room 1
  • DX-ROOM2 — DR X-Ray Room 2
  • DX-ROOM3 — DR X-Ray Room 3 (added to fixtures by this script if absent)

Six workitems are seeded to represent the worklist at different points in
the lifecycle:

  State        Room      Patient          Procedure
  ─────────── ────────── ──────────────── ──────────────────────────────────
  SCHEDULED    DX-ROOM1  Adams, James     Chest PA + Lateral
  SCHEDULED    DX-ROOM2  Baker, Sarah     Right Hand AP + Oblique + Lateral
  SCHEDULED    DX-ROOM3  Chen, Wei        Pelvis AP  (HIGH priority)
  IN PROGRESS  DX-ROOM1  Davis, Emma      Chest PA + Lateral  (exam started)
  IN PROGRESS  DX-ROOM2  Evans, Thomas    Right Wrist PA + Lateral  (all views taken)
  COMPLETED    DX-ROOM3  Foster, Grace    Right Shoulder AP + Y + Axial

Each workitem is accompanied by the UPS Events that match the sequence
shown in the push-workflow swim-lane diagram:

  RIS       → N-CREATE          (CREATE event)
  Modality  → claim workitem    (CLAIM event; N-EVENT-REPORT "Exam Started")
  Modality  → store images; progress update   (UPDATE event; N-EVENT-REPORT)
  Modality  → N-SET COMPLETED   (COMPLETE event; N-EVENT-REPORT "Exam Complete")
  RIS       → N-GET final state
  RIS       → N-ACTION UNSUBSCRIBE

Usage
-----
Seed::

    bench --site development.localhost execute \\
        healthcare.demo.push_workflow_xray_clinic.run

Teardown::

    bench --site development.localhost execute \\
        healthcare.demo.push_workflow_xray_clinic.teardown
"""

from datetime import datetime, timedelta

import frappe
from frappe.utils import now_datetime

# ── Stable fixed DICOM UIDs (reproducible / idempotent) ──────────────────────
# 2.25 root + 9-digit namespace + 2-digit serial
_BASE = "2.25.9000000000000000000000"

WORKITEM_UIDS = {
    "ADAMS":  _BASE + "01",
    "BAKER":  _BASE + "02",
    "CHEN":   _BASE + "03",
    "DAVIS":  _BASE + "04",
    "EVANS":  _BASE + "05",
    "FOSTER": _BASE + "06",
}

STUDY_UIDS = {
    "DAVIS":  _BASE + "14",
    "EVANS":  _BASE + "15",
    "FOSTER": _BASE + "16",
}

TRANSACTION_UIDS = {
    "DAVIS":  "2.25.8000000000000000000000" + "04",
    "EVANS":  "2.25.8000000000000000000000" + "05",
    "FOSTER": "2.25.8000000000000000000000" + "06",
}

# ── Internal helpers ──────────────────────────────────────────────────────────

def _today_at(hour, minute=0, offset_days=0):
    """Return a naive datetime for today at the given hour:minute."""
    base = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=offset_days)


def _ensure_dx_room3():
    """Create the DX-ROOM3 AE Mapping fixture if it does not yet exist."""
    if frappe.db.exists("AE Mapping", "DX-ROOM3"):
        return
    doc = frappe.new_doc("AE Mapping")
    doc.name               = "DX-ROOM3"
    doc.ae_title           = "DX-ROOM3"
    doc.display_name       = "DR X-Ray Room 3"
    doc.node_type          = "Acquisition Modality"
    doc.modality           = "DX"
    doc.station_name       = "DX-ROOM3"
    doc.station_class_code = "DXSCANNER"
    doc.active             = 1
    doc.host          = "192.168.10.13"
    doc.port          = 104
    doc.dicomweb_url  = ""
    doc.flags.ignore_permissions = True
    doc.insert()
    frappe.db.commit()
    print("  ✓  Created AE Mapping: DX-ROOM3")


def _create_ups(
    uid, state, priority, patient_id, patient_name, patient_dob, patient_sex,
    procedure_id, accession, protocol, description, modality, aet, station_name,
    scheduled_dt, station_class_code=None,
):
    """Insert a UPS Instance; skip silently if it already exists."""
    if frappe.db.exists("UPS Instance", uid):
        print(f"  —  Already exists: {patient_name} ({uid[-6:]}…)")
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
    doc.ups_sync_status        = "synced"
    doc.flags.ignore_permissions = True
    doc.flags.sync_import        = True   # bypass state-machine on initial insert
    doc.insert()
    print(f"  ✓  [{state:12s}]  {patient_name:20s}  →  {aet}")
    return doc, True


def _event_exists(ups_uid, event_type):
    return bool(frappe.db.exists(
        "UPS Event", {"ups_instance": ups_uid, "event_type": event_type}
    ))


def _add_event(
    doc, event_type, old_state, new_state, actor_aet,
    details, timestamp=None, http_status=200, transaction_uid=None,
):
    """Insert a UPS Event row for *doc*."""
    event = frappe.new_doc("UPS Event")
    event.ups_instance    = doc.name
    event.event_type      = event_type
    event.actor           = "Administrator"
    event.actor_aet       = actor_aet
    event.event_timestamp = timestamp or now_datetime()
    event.old_state       = old_state
    event.new_state       = new_state
    event.transaction_uid = transaction_uid or getattr(doc, "transaction_uid", None)
    event.details         = details
    event.http_status     = http_status
    event.flags.ignore_permissions = True
    event.insert()


# ── dcm4chee-arc push helpers ─────────────────────────────────────────────────


def _dicomweb_available():
    # Return True if a UPS RS URL is configured in UPS Integration Settings.
    try:
        url = frappe.db.get_single_value("UPS Integration Settings", "ups_rs_url")
        return bool(url)
    except Exception:
        return False


def _build_dicom_payload(
    uid, priority, scheduled_dt, modality, aet,
    patient_id, patient_name, patient_dob, patient_sex,
    accession, proc_id, protocol,
    station_class_code=None,
):
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
    # Note: SOP Instance UID (00080018) is NOT sent in the body;
    #   it is conveyed via the ?workitem= query parameter only.
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
    # POST a workitem to dcm4chee-arc (N-CREATE equivalent via UPS-RS).
    # Returns True on success or 409-already-exists, False on any error.
    from healthcare.integrations.dicomweb_client import (
        ConflictError, DICOMwebClient, ServerError, UPSClientError,
    )
    try:
        DICOMwebClient().create_workitem(uid, attributes)
        print(f"    -> dcm4chee N-CREATE OK  (...{uid[-10:]})")
        return True
    except ConflictError:
        print(f"    -> dcm4chee: workitem already exists (...{uid[-10:]})")
        return True
    except (ServerError, UPSClientError) as exc:
        print(f"    ! dcm4chee N-CREATE failed: {exc}")
        return False


def _dicomweb_change_state(uid, new_state, transaction_uid):
    # Change UPS state on dcm4chee-arc (N-SET equivalent via UPS-RS).
    # Returns True on success or idempotent-skip, False on hard error.
    from healthcare.integrations.dicomweb_client import (
        BadRequestError, ConflictError, DICOMwebClient,
        NotFoundError, ServerError, UPSClientError,
    )
    try:
        DICOMwebClient().change_state(uid, new_state, transaction_uid)
        print(f"    -> dcm4chee state -> {new_state} OK  (...{uid[-10:]})")
        return True
    except NotFoundError:
        # Workitem not held in dcm4chee (e.g. N-CREATE was never pushed).
        # Nothing to change — treat as success for teardown purposes.
        return True
    except ConflictError:
        print(f"    -> dcm4chee: already in state {new_state} (...{uid[-10:]})")
        return True
    except BadRequestError:
        # Already in terminal state or AET not permitted — best-effort skip.
        return True
    except (ServerError, UPSClientError) as exc:
        print(f"    ! dcm4chee state change failed: {exc}")
        return False


def _dicomweb_delete(uid):
    # UPS-RS does not define a DELETE method for workitems (DICOM PS3.18 §11.7).
    # dcm4chee-arc returns 405 Method Not Allowed on any DELETE attempt.
    # The only supported cleanup for SCHEDULED workitems is to cancel them
    # (state change → CANCELED), which _dicomweb_change_state handles.
    # This stub is kept so callers compile; it does nothing.
    pass

# ── Public entry points ───────────────────────────────────────────────────────

def run():
    """
    Seed the Push Workflow – X-Ray Clinic demo data.

    Idempotent: safe to call multiple times; existing records are left
    unchanged.
    """
    frappe.set_user("Administrator")
    print("\n═══ Push Workflow: X-Ray Clinic — demo seed ════════════════════════")

    # Ensure DX-ROOM3 AE Mapping is present
    _ensure_dx_room3()

    # ── 1. Adams – SCHEDULED ─────────────────────────────────────────────────
    t = _today_at(9, 0)
    adams, adams_new = _create_ups(
        uid           = WORKITEM_UIDS["ADAMS"],
        state         = "SCHEDULED",
        priority      = "MEDIUM",
        patient_id    = "PT-10001",
        patient_name  = "Adams^James",
        patient_dob   = "1978-04-12",
        patient_sex   = "M",
        procedure_id  = "RP-10001",
        accession     = "ACC-10001",
        protocol      = "CHEST-2V",
        description   = "Chest PA + Lateral",
        modality      = "DX",
        aet           = "DX-ROOM1",
        station_name  = "DX-ROOM1",
        scheduled_dt  = t,
    )
    if adams_new and _dicomweb_available():
        _dicomweb_push(
            WORKITEM_UIDS["ADAMS"],
            _build_dicom_payload(
                WORKITEM_UIDS["ADAMS"], "MEDIUM", t, "DX", "DX-ROOM1",
                "PT-10001", "Adams^James", "1978-04-12", "M",
                "ACC-10001", "RP-10001", "CHEST-2V",
            ),
        )
    if not _event_exists(WORKITEM_UIDS["ADAMS"], "CREATE"):
        _add_event(
            adams, "CREATE", None, "SCHEDULED",
            actor_aet = "UPS-PORTAL",
            details   = (
                "RIS pushed workitem via N-CREATE (UPS Push SOP Class). "
                "Patient (Mr. Adams) arrived at Reception; RIS assigned to DX-ROOM1. "
                "Global subscription active on DX-ROOM1 (N-ACTION SUBSCRIBE Well-Known UID)."
            ),
            timestamp   = t - timedelta(minutes=5),
            http_status = 201,
        )

    # ── 2. Baker – SCHEDULED ─────────────────────────────────────────────────
    t = _today_at(9, 30)
    baker, baker_new = _create_ups(
        uid           = WORKITEM_UIDS["BAKER"],
        state         = "SCHEDULED",
        priority      = "LOW",
        patient_id    = "PT-10002",
        patient_name  = "Baker^Sarah",
        patient_dob   = "1995-09-27",
        patient_sex   = "F",
        procedure_id  = "RP-10002",
        accession     = "ACC-10002",
        protocol      = "HAND-3V",
        description   = "Right Hand AP + Oblique + Lateral – trauma follow-up",
        modality      = "DX",
        aet           = "DX-ROOM2",
        station_name  = "DX-ROOM2",
        scheduled_dt  = t,
    )
    if baker_new and _dicomweb_available():
        _dicomweb_push(
            WORKITEM_UIDS["BAKER"],
            _build_dicom_payload(
                WORKITEM_UIDS["BAKER"], "LOW", t, "DX", "DX-ROOM2",
                "PT-10002", "Baker^Sarah", "1995-09-27", "F",
                "ACC-10002", "RP-10002", "HAND-3V",
            ),
        )
    if not _event_exists(WORKITEM_UIDS["BAKER"], "CREATE"):
        _add_event(
            baker, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = (
                "RIS pushed workitem via N-CREATE. "
                "Patient (Ms. Baker) assigned to DX-ROOM2."
            ),
            timestamp   = t - timedelta(minutes=3),
            http_status = 201,
        )

    # ── 3. Chen – SCHEDULED (HIGH priority) ──────────────────────────────────
    t = _today_at(10, 0)
    chen, chen_new = _create_ups(
        uid           = WORKITEM_UIDS["CHEN"],
        state         = "SCHEDULED",
        priority      = "HIGH",
        patient_id    = "PT-10003",
        patient_name  = "Chen^Wei",
        patient_dob   = "1960-01-15",
        patient_sex   = "M",
        procedure_id  = "RP-10003",
        accession     = "ACC-10003",
        protocol      = "PELVIS-1V",
        description   = "Pelvis AP – pre-operative assessment",
        modality      = "DX",
        aet           = "DX-ROOM3",
        station_name  = "DX-ROOM3",
        scheduled_dt  = t,
    )
    if chen_new and _dicomweb_available():
        _dicomweb_push(
            WORKITEM_UIDS["CHEN"],
            _build_dicom_payload(
                WORKITEM_UIDS["CHEN"], "HIGH", t, "DX", "DX-ROOM3",
                "PT-10003", "Chen^Wei", "1960-01-15", "M",
                "ACC-10003", "RP-10003", "PELVIS-1V",
            ),
        )
    if not _event_exists(WORKITEM_UIDS["CHEN"], "CREATE"):
        _add_event(
            chen, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = (
                "RIS pushed workitem via N-CREATE (HIGH priority – pre-op). "
                "Patient (Mr. Chen) assigned to DX-ROOM3."
            ),
            timestamp   = t - timedelta(minutes=2),
            http_status = 201,
        )

    # ── 4. Davis – IN PROGRESS (exam started) ────────────────────────────────
    t_sched = _today_at(8, 30)
    t_claim = _today_at(8, 35)
    davis, davis_new = _create_ups(
        uid           = WORKITEM_UIDS["DAVIS"],
        state         = "IN PROGRESS",
        priority      = "MEDIUM",
        patient_id    = "PT-10004",
        patient_name  = "Davis^Emma",
        patient_dob   = "1985-11-03",
        patient_sex   = "F",
        procedure_id  = "RP-10004",
        accession     = "ACC-10004",
        protocol      = "CHEST-2V",
        description   = "Chest PA + Lateral – routine annual",
        modality      = "DX",
        aet           = "DX-ROOM1",
        station_name  = "DX-ROOM1",
        scheduled_dt  = t_sched,
    )
    # Set claim fields directly (state machine already bypassed via sync_import on insert)
    if frappe.db.get_value("UPS Instance", WORKITEM_UIDS["DAVIS"], "transaction_uid") is None:
        frappe.db.set_value(
            "UPS Instance", WORKITEM_UIDS["DAVIS"],
            {
                "transaction_uid": TRANSACTION_UIDS["DAVIS"],
                "performing_aet":  "DX-ROOM1",
                "claimed_by":      "Administrator",
                "claimed_at":      t_claim,
            },
        )

    if davis_new and _dicomweb_available():
        if _dicomweb_push(
            WORKITEM_UIDS["DAVIS"],
            _build_dicom_payload(
                WORKITEM_UIDS["DAVIS"], "MEDIUM", t_sched, "DX", "DX-ROOM1",
                "PT-10004", "Davis^Emma", "1985-11-03", "F",
                "ACC-10004", "RP-10004", "CHEST-2V",
            ),
        ):
            _dicomweb_change_state(
                WORKITEM_UIDS["DAVIS"], "IN PROGRESS", TRANSACTION_UIDS["DAVIS"]
            )
    if not _event_exists(WORKITEM_UIDS["DAVIS"], "CREATE"):
        _add_event(
            davis, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = "RIS pushed workitem via N-CREATE.",
            timestamp   = t_sched - timedelta(minutes=10),
            http_status = 201,
        )
    if not _event_exists(WORKITEM_UIDS["DAVIS"], "CLAIM"):
        _add_event(
            davis, "CLAIM", "SCHEDULED", "IN PROGRESS",
            actor_aet       = "DX-ROOM1",
            details         = (
                "DX-ROOM1 claimed workitem (N-SET → IN PROGRESS). "
                "Tech confirmed identity of Ms. Davis and began procedure. "
                "N-EVENT-REPORT sent to global subscriber: 'Exam Started'."
            ),
            timestamp       = t_claim,
            http_status     = 200,
            transaction_uid = TRANSACTION_UIDS["DAVIS"],
        )

    # ── 5. Evans – IN PROGRESS (all views taken) ──────────────────────────────
    t_sched  = _today_at(8, 0)
    t_claim  = _today_at(8, 5)
    t_update = _today_at(8, 22)
    evans, evans_new = _create_ups(
        uid           = WORKITEM_UIDS["EVANS"],
        state         = "IN PROGRESS",
        priority      = "LOW",
        patient_id    = "PT-10005",
        patient_name  = "Evans^Thomas",
        patient_dob   = "2001-06-18",
        patient_sex   = "M",
        procedure_id  = "RP-10005",
        accession     = "ACC-10005",
        protocol      = "WRIST-2V",
        description   = "Right Wrist PA + Lateral – sports injury",
        modality      = "DX",
        aet           = "DX-ROOM2",
        station_name  = "DX-ROOM2",
        scheduled_dt  = t_sched,
    )
    if frappe.db.get_value("UPS Instance", WORKITEM_UIDS["EVANS"], "transaction_uid") is None:
        frappe.db.set_value(
            "UPS Instance", WORKITEM_UIDS["EVANS"],
            {
                "transaction_uid": TRANSACTION_UIDS["EVANS"],
                "performing_aet":  "DX-ROOM2",
                "claimed_by":      "Administrator",
                "claimed_at":      t_claim,
            },
        )

    if evans_new and _dicomweb_available():
        if _dicomweb_push(
            WORKITEM_UIDS["EVANS"],
            _build_dicom_payload(
                WORKITEM_UIDS["EVANS"], "LOW", t_sched, "DX", "DX-ROOM2",
                "PT-10005", "Evans^Thomas", "2001-06-18", "M",
                "ACC-10005", "RP-10005", "WRIST-2V",
            ),
        ):
            _dicomweb_change_state(
                WORKITEM_UIDS["EVANS"], "IN PROGRESS", TRANSACTION_UIDS["EVANS"]
            )
    if not _event_exists(WORKITEM_UIDS["EVANS"], "CREATE"):
        _add_event(
            evans, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = "RIS pushed workitem via N-CREATE.",
            timestamp   = t_sched - timedelta(minutes=15),
            http_status = 201,
        )
    if not _event_exists(WORKITEM_UIDS["EVANS"], "CLAIM"):
        _add_event(
            evans, "CLAIM", "SCHEDULED", "IN PROGRESS",
            actor_aet       = "DX-ROOM2",
            details         = (
                "DX-ROOM2 claimed workitem (N-SET → IN PROGRESS). "
                "Exam started. "
                "N-EVENT-REPORT sent to global subscriber: 'Exam Started'."
            ),
            timestamp       = t_claim,
            http_status     = 200,
            transaction_uid = TRANSACTION_UIDS["EVANS"],
        )
    if not _event_exists(WORKITEM_UIDS["EVANS"], "UPDATE"):
        _add_event(
            evans, "UPDATE", "IN PROGRESS", "IN PROGRESS",
            actor_aet       = "DX-ROOM2",
            details         = (
                "UPS progress updated: 'All Views Taken'. "
                "Images stored to PACS (DCM4CHEE). "
                "N-EVENT-REPORT sent to global subscriber — "
                "RIS/Dashboard display updated to 'All Views Taken'."
            ),
            timestamp       = t_update,
            http_status     = 200,
            transaction_uid = TRANSACTION_UIDS["EVANS"],
        )

    # ── 6. Foster – COMPLETED (full workflow) ────────────────────────────────
    t_sched    = _today_at(7, 30)
    t_claim    = _today_at(7, 38)
    t_update   = _today_at(7, 55)
    t_complete = _today_at(8, 0)
    foster, foster_new = _create_ups(
        uid           = WORKITEM_UIDS["FOSTER"],
        state         = "COMPLETED",
        priority      = "MEDIUM",
        patient_id    = "PT-10006",
        patient_name  = "Foster^Grace",
        patient_dob   = "1970-03-22",
        patient_sex   = "F",
        procedure_id  = "RP-10006",
        accession     = "ACC-10006",
        protocol      = "SHOULDER-3V",
        description   = "Right Shoulder AP + Y-view + Axial – rotator cuff assessment",
        modality      = "DX",
        aet           = "DX-ROOM3",
        station_name  = "DX-ROOM3",
        scheduled_dt  = t_sched,
    )
    # Set performer / study fields (transaction_uid cleared on COMPLETED per controller)
    frappe.db.set_value(
        "UPS Instance", WORKITEM_UIDS["FOSTER"],
        {
            "performing_aet":      "DX-ROOM3",
            "claimed_by":          "Administrator",
            "claimed_at":          t_claim,
            "performed_study_uid": STUDY_UIDS["FOSTER"],
            "transaction_uid":     None,   # cleared on COMPLETED per UPSInstance.before_save
        },
    )

    if foster_new and _dicomweb_available():
        if _dicomweb_push(
            WORKITEM_UIDS["FOSTER"],
            _build_dicom_payload(
                WORKITEM_UIDS["FOSTER"], "MEDIUM", t_sched, "DX", "DX-ROOM3",
                "PT-10006", "Foster^Grace", "1970-03-22", "F",
                "ACC-10006", "RP-10006", "SHOULDER-3V",
            ),
        ):
            if _dicomweb_change_state(
                WORKITEM_UIDS["FOSTER"], "IN PROGRESS", TRANSACTION_UIDS["FOSTER"]
            ):
                _dicomweb_change_state(
                    WORKITEM_UIDS["FOSTER"], "COMPLETED", TRANSACTION_UIDS["FOSTER"]
                )
    if not _event_exists(WORKITEM_UIDS["FOSTER"], "CREATE"):
        _add_event(
            foster, "CREATE", None, "SCHEDULED",
            actor_aet   = "UPS-PORTAL",
            details     = (
                "RIS pushed workitem via N-CREATE (UPS Push SOP Class). "
                "Global subscription active on DX-ROOM3 "
                "(N-ACTION SUBSCRIBE Well-Known Instance UID)."
            ),
            timestamp   = t_sched - timedelta(minutes=5),
            http_status = 201,
        )
    if not _event_exists(WORKITEM_UIDS["FOSTER"], "CLAIM"):
        _add_event(
            foster, "CLAIM", "SCHEDULED", "IN PROGRESS",
            actor_aet       = "DX-ROOM3",
            details         = (
                "DX-ROOM3 claimed workitem (N-SET → IN PROGRESS). "
                "Tech confirmed identity of Ms. Foster. Procedure begun. "
                "N-EVENT-REPORT → RIS/Dashboard: 'Exam Started'."
            ),
            timestamp       = t_claim,
            http_status     = 200,
            transaction_uid = TRANSACTION_UIDS["FOSTER"],
        )
    if not _event_exists(WORKITEM_UIDS["FOSTER"], "UPDATE"):
        _add_event(
            foster, "UPDATE", "IN PROGRESS", "IN PROGRESS",
            actor_aet       = "DX-ROOM3",
            details         = (
                "Images stored to PACS (DCM4CHEE). "
                "UPS progress updated: 'All Views Taken'. "
                "N-EVENT-REPORT → RIS/Dashboard: display updated."
            ),
            timestamp       = t_update,
            http_status     = 200,
            transaction_uid = TRANSACTION_UIDS["FOSTER"],
        )
    if not _event_exists(WORKITEM_UIDS["FOSTER"], "COMPLETE"):
        _add_event(
            foster, "COMPLETE", "IN PROGRESS", "COMPLETED",
            actor_aet       = "DX-ROOM3",
            details         = (
                "Task completed (N-SET → COMPLETED). "
                "N-EVENT-REPORT → RIS/Dashboard: 'Exam Complete'. "
                "RIS retrieved final state details (N-GET). "
                "RIS unsubscribed from Task-specific events "
                "(N-ACTION UNSUBSCRIBE [Task Foster])."
            ),
            timestamp       = t_complete,
            http_status     = 200,
            transaction_uid = TRANSACTION_UIDS["FOSTER"],
        )

    frappe.db.commit()

    print("\n────────────────────────────────────────────────────────────────────")
    print("  SCHEDULED   : Adams (DX-ROOM1)  ·  Baker (DX-ROOM2)  ·  Chen (DX-ROOM3)")
    print("  IN PROGRESS : Davis – exam started (DX-ROOM1)")
    print("                Evans – all views taken (DX-ROOM2)")
    print("  COMPLETED   : Foster – full push workflow (DX-ROOM3)")
    print("════════════════════════════════════════════════════════════════════\n")


def teardown():
    """
    Remove all demo workitems and their UPS Events.

    Idempotent: missing records are silently skipped.
    """
    frappe.set_user("Administrator")
    print("\n═══ Push Workflow: X-Ray Clinic — teardown ════════════════════════")

    dcm4chee = _dicomweb_available()

    for key, uid in WORKITEM_UIDS.items():
        # -- dcm4chee-arc cleanup
        if dcm4chee:
            state = frappe.db.get_value("UPS Instance", uid, "ups_state")
            # Cancel non-terminal workitems in dcm4chee so they don't block
            # future N-CREATE on re-seed.  DICOM UPS-RS has no DELETE; the only
            # cleanup available is transitioning to CANCELED.
            if state == "SCHEDULED":
                _dicomweb_change_state(uid, "CANCELED", None)
            elif state == "IN PROGRESS":
                txn = frappe.db.get_value("UPS Instance", uid, "transaction_uid")
                _dicomweb_change_state(uid, "CANCELED", txn)

        # -- local mirror cleanup
        if not frappe.db.exists("UPS Instance", uid):
            print(f"  —  Not found: {key}")
            continue
        events = frappe.get_list("UPS Event", filters={"ups_instance": uid}, pluck="name")
        for evt in events:
            frappe.delete_doc("UPS Event", evt, force=True, ignore_permissions=True)
        frappe.delete_doc("UPS Instance", uid, force=True, ignore_permissions=True)
        print(f"  ✗  Deleted {key} ({uid[-6:]}… + {len(events)} events)")

    frappe.db.commit()
    print("════════════════════════════════════════════════════════════════════\n")
