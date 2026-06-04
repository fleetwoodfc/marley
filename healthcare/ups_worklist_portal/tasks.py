"""
Scheduled tasks for healthcare.ups_worklist_portal.

poll_ups_events() is called every 5 minutes by the Frappe scheduler
(configured in hooks.py) to sync UPS instance state from dcm4chee-arc.
"""

import json
import logging

import frappe
from frappe.utils import now_datetime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scheduler tasks
# ---------------------------------------------------------------------------


def poll_ups_events():
    """
    Fetch active workitems from dcm4chee-arc and upsert local UPS Instance
    mirror rows.  Emits realtime events for any state changes detected.

    Called by scheduler every 5 minutes via hooks.py scheduler_events.
    Uses job_id-based deduplication to prevent double-enqueuing.
    """
    settings = frappe.get_single("UPS Integration Settings")
    if not settings.enable_ups_sync:
        return

    from healthcare.integrations.dicomweb_client import (  # noqa: PLC0415
        DICOMwebClient,
        ServerError,
    )

    try:
        client = DICOMwebClient()
        workitems = client.get_worklist(
            {"00741000": "SCHEDULED,IN PROGRESS"}
        )
    except ServerError as exc:
        logger.error("poll_ups_events: failed to reach dcm4chee-arc: %s", exc)
        return
    except Exception as exc:
        logger.exception("poll_ups_events: unexpected error: %s", exc)
        return

    for item in workitems:
        try:
            _upsert_workitem(item)
        except Exception as exc:
            uid = _tag(item, "00080018") or "unknown"
            logger.exception("poll_ups_events: failed to upsert %s: %s", uid, exc)

    frappe.db.commit()


# ---------------------------------------------------------------------------
# Retry task (called by schedule_sync_retry)
# ---------------------------------------------------------------------------


def retry_sync_workitem(ups_uid, attempt=1):
    """
    Retry syncing a single workitem from dcm4chee-arc after a prior failure.

    Enqueued by dicomweb_client.schedule_sync_retry().
    """
    settings = frappe.get_single("UPS Integration Settings")
    if not settings.enable_ups_sync:
        return

    from healthcare.integrations.dicomweb_client import (  # noqa: PLC0415
        DICOMwebClient,
        ServerError,
        schedule_sync_retry,
    )

    try:
        client = DICOMwebClient()
        item = client.get_workitem(ups_uid)
        _upsert_workitem(item)
        frappe.db.commit()
    except ServerError as exc:
        logger.warning("retry_sync_workitem attempt %d failed for %s: %s", attempt, ups_uid, exc)
        schedule_sync_retry(
            "healthcare.ups_worklist_portal.tasks.retry_sync_workitem",
            ups_uid=ups_uid,
            attempt=attempt,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tag(dataset, tag, default=None):
    """Extract the first Value from a DICOM+JSON tag or return default."""
    entry = dataset.get(tag)
    if not entry:
        return default
    values = entry.get("Value")
    if not values:
        return default
    return values[0]


def _upsert_workitem(dicom_dataset):
    """
    Insert or update a UPS Instance document from a DICOM+JSON dataset.

    Emits a realtime event if the state changed.
    """
    uid = _tag(dicom_dataset, "00080018")
    if not uid:
        logger.warning("poll_ups_events: workitem missing SOP Instance UID (0008,0018); skipping")
        return

    new_state = _tag(dicom_dataset, "00741000")
    priority_map = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}
    priority = priority_map.get(_tag(dicom_dataset, "00741200", "MEDIUM"), "MEDIUM")
    scheduled_dt = _tag(dicom_dataset, "00404005")
    modality = _tag(dicom_dataset, "00080060")

    # (0040,4034) Scheduled Human Performers Sequence was previously misused as
    # a station AET carrier; it is now obsolete — the portal no longer sends it.
    # scheduled_station_aet is populated via the assign_workitem flow instead.
    scheduled_aet = None

    # Scheduled Station Class Code Sequence (0040,4026) — SQ; code value is (0008,0100)
    station_class_seq = (dicom_dataset.get("00404026") or {}).get("Value", [{}])
    scheduled_station_class_code = (
        ((station_class_seq[0] if station_class_seq else {}).get("00080100") or {}).get("Value", [None])[0]
        if station_class_seq else None
    )

    # Scheduled Station Name Code Sequence (0040,4025) — SQ; code value is (0008,0100)
    station_name_seq = (dicom_dataset.get("00404025") or {}).get("Value", [{}])
    scheduled_station_name = (
        ((station_name_seq[0] if station_name_seq else {}).get("00080100") or {}).get("Value", [None])[0]
        if station_name_seq else None
    )

    patient_id = _tag(dicom_dataset, "00100020")
    patient_name_raw = _tag(dicom_dataset, "00100010")
    # DICOM Person Name can be a dict {"Alphabetic": "Doe^John"}
    if isinstance(patient_name_raw, dict):
        patient_name = patient_name_raw.get("Alphabetic", "")
    else:
        patient_name = str(patient_name_raw or "")

    patient_dob = _tag(dicom_dataset, "00100030")
    patient_sex = _tag(dicom_dataset, "00100040")
    accession = _tag(dicom_dataset, "00080050")
    study_uid = _tag(dicom_dataset, "0020000D")
    proc_id = _tag(dicom_dataset, "00401001")
    protocol = _tag(dicom_dataset, "00181030")
    step_label = _tag(dicom_dataset, "00741204")   # (0074,1204) Procedure Step Label

    raw_payload = json.dumps(dicom_dataset, ensure_ascii=False)

    existing = frappe.db.exists("UPS Instance", uid)

    if existing:
        doc = frappe.get_doc("UPS Instance", uid)
        old_state = doc.ups_state

        # Update mirror fields
        doc.scheduled_datetime = scheduled_dt
        doc.modality = modality
        doc.scheduled_station_aet = scheduled_aet
        doc.scheduled_station_name = scheduled_station_name
        doc.scheduled_station_class_code = scheduled_station_class_code
        doc.priority = priority
        doc.patient_id = patient_id
        doc.patient_name = patient_name
        doc.patient_birth_date = patient_dob
        doc.patient_sex = patient_sex
        doc.accession_number = accession
        doc.study_instance_uid = study_uid
        doc.requested_procedure_id = proc_id
        doc.protocol_name = protocol
        doc.procedure_description = step_label
        doc.ups_sync_status = "synced"
        doc.ups_sync_at = now_datetime()
        doc.ups_sync_error = None
        doc.raw_payload = raw_payload

        # Only update ups_state if changed (respects state machine)
        if new_state and new_state != old_state:
            doc.ups_state = new_state

        doc.flags.ignore_permissions = True
        doc.save()

        if new_state and new_state != old_state:
            frappe.publish_realtime(
                "ups_state_change",
                {
                    "ups_instance_uid": uid,
                    "old_state": old_state,
                    "new_state": new_state,
                    "source": "poll",
                },
                room="ups_dashboard",
            )
    else:
        doc = frappe.new_doc("UPS Instance")
        doc.name = uid  # UPSInstanceUID becomes document name
        doc.ups_state = new_state or "SCHEDULED"
        doc.priority = priority
        doc.scheduled_datetime = scheduled_dt
        doc.modality = modality
        doc.scheduled_station_aet = scheduled_aet
        doc.scheduled_station_name = scheduled_station_name
        doc.scheduled_station_class_code = scheduled_station_class_code
        doc.patient_id = patient_id
        doc.patient_name = patient_name
        doc.patient_birth_date = patient_dob
        doc.patient_sex = patient_sex
        doc.accession_number = accession
        doc.study_instance_uid = study_uid
        doc.requested_procedure_id = proc_id
        doc.protocol_name = protocol
        doc.procedure_description = step_label
        doc.ups_sync_status = "synced"
        doc.ups_sync_at = now_datetime()
        doc.raw_payload = raw_payload
        doc.flags.ignore_permissions = True
        doc.flags.sync_import = True  # bypass state machine — dcm4chee is source of truth
        doc.insert()

        doc.append_event(
            "CREATE",
            old_state=None,
            new_state=doc.ups_state,
            details="Created by scheduler poll.",
            actor="Administrator",
        )

