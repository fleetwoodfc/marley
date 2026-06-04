"""
Frappe whitelisted API methods for the UPS Worklist Portal.

All methods are accessible via:
    frappe.call("healthcare.ups_worklist_portal.api.ups_actions.<method_name>", ...)

Permissions are enforced via:
 1. frappe.only_for([...roles...]) — role-based gate
 2. ups_instance_permission() hook — state-based write protection

See contracts/ups-portal-api.yaml for the full request/response schemas.
"""

import uuid
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import now_datetime

from healthcare.integrations.dicomweb_client import (
    BadRequestError,
    ConflictError,
    DICOMwebClient,
    NotFoundError,
    ServerError,
    UPSClientError,
)

# All custom roles that can access the portal
_ALL_PORTAL_ROLES = ["UPS Technologist", "UPS Supervisor", "UPS Integration Engineer"]


# ---------------------------------------------------------------------------
# Page bootstrap: AE Mappings + user context
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_ae_mappings():
    """
    Return active AE Mapping records for the dashboard.

    Called on page load to populate the Assign / Reassign dropdowns and the
    AE Title filter.  Accessible to all portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)
    return frappe.get_list(
        "AE Mapping",
        filters={"active": 1},
        fields=["ae_title", "display_name", "modality", "node_type", "assigned_user", "station_name", "station_class_code"],
        order_by="ae_title asc",
    )


@frappe.whitelist()
def get_ae_mappings_for_class(station_class_code):
    """
    Return active AE Mappings whose station_class_code matches the given value.

    Called by the Assign dialog when the workitem carries a Scheduled Station
    Class Code Sequence (0040,4026), so only compatible stations are offered.
    Falls back to all active mappings if station_class_code is blank.

    Accessible to all portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)
    filters = {"active": 1}
    if station_class_code:
        filters["station_class_code"] = station_class_code
    return frappe.get_list(
        "AE Mapping",
        filters=filters,
        fields=["ae_title", "display_name", "modality", "node_type", "station_name", "station_class_code"],
        order_by="ae_title asc",
    )


# ---------------------------------------------------------------------------
# T018: get_worklist
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_worklist(
    status=None,
    ae_title=None,
    modality=None,
    from_datetime=None,
    to_datetime=None,
    patient_name=None,
    limit=50,
    offset=0,
):
    """
    Return a paginated list of UPS Instance documents from the local mirror.

    Accessible to all three portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)

    filters = {}

    if status:
        # status may arrive as a JSON string "["SCHEDULED","IN PROGRESS"]"
        if isinstance(status, str):
            import json as _json
            try:
                status = _json.loads(status)
            except ValueError:
                status = [status]
        filters["ups_state"] = ["in", status]
    else:
        filters["ups_state"] = ["in", ["SCHEDULED", "IN PROGRESS"]]

    if ae_title:
        filters["scheduled_station_aet"] = ae_title
    if modality:
        filters["modality"] = ["like", f"%{modality}%"]
    if from_datetime:
        filters["scheduled_datetime"] = [">=", from_datetime]
    if to_datetime:
        existing_dt_filter = filters.get("scheduled_datetime")
        if existing_dt_filter:
            # Convert to between filter
            filters["scheduled_datetime"] = ["between", [from_datetime, to_datetime]]
        else:
            filters["scheduled_datetime"] = ["<=", to_datetime]
    if patient_name:
        filters["patient_name"] = ["like", f"%{patient_name}%"]

    limit = int(limit)
    offset = int(offset)

    total = frappe.db.count("UPS Instance", filters)
    items = frappe.get_list(
        "UPS Instance",
        filters=filters,
        fields=[
            "name",
            "ups_state",
            "priority",
            "scheduled_datetime",
            "modality",
            "scheduled_station_aet",
            "scheduled_station_name",
            "scheduled_station_class_code",
            "patient_id",
            "patient_name",
            "requested_procedure_id",
            "accession_number",
            "protocol_name",
            "procedure_description",
            "claimed_by",
            "claimed_at",
        ],
        order_by="scheduled_datetime asc",
        limit_page_length=limit,
        limit_start=offset,
    )

    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# T019: get_workitem
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_workitem(ups_uid):
    """
    Return full details for a single UPS Instance including event history.

    Accessible to all three portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(
            _("UPS Instance {0} not found.").format(ups_uid),
            frappe.DoesNotExistError,
        )

    doc = frappe.get_doc("UPS Instance", ups_uid)
    events = frappe.get_list(
        "UPS Event",
        filters={"ups_instance": ups_uid},
        fields=[
            "name",
            "event_type",
            "actor",
            "actor_aet",
            "event_timestamp",
            "old_state",
            "new_state",
            "transaction_uid",
            "details",
            "http_status",
        ],
        order_by="event_timestamp desc",
        limit_page_length=200,
    )

    result = doc.as_dict()
    result["events"] = events
    return result


# ---------------------------------------------------------------------------
# T020: get_dashboard_summary
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_dashboard_summary():
    """
    Return counts by UPS state plus ORPHANED and sync-error counts.

    An ORPHANED workitem is one that is IN PROGRESS and has received a
    CANCEL_REQUEST event more than 30 minutes ago with no subsequent
    COMPLETE or CANCEL event.

    Accessible to all three portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)

    counts = {
        "SCHEDULED": frappe.db.count("UPS Instance", {"ups_state": "SCHEDULED"}),
        "IN_PROGRESS": frappe.db.count("UPS Instance", {"ups_state": "IN PROGRESS"}),
        "COMPLETED": frappe.db.count("UPS Instance", {"ups_state": "COMPLETED"}),
        "CANCELED": frappe.db.count("UPS Instance", {"ups_state": "CANCELED"}),
        "SYNC_ERROR": frappe.db.count("UPS Instance", {"ups_sync_status": "error"}),
        "ORPHANED": _count_orphaned(),
    }

    return counts


def _count_orphaned():
    """
    Count IN PROGRESS workitems that received a CANCEL_REQUEST event
    more than 30 minutes ago without a subsequent COMPLETE or CANCEL event.
    """
    cutoff = now_datetime() - timedelta(minutes=30)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    result = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT ui.name)
        FROM `tabUPS Instance` ui
        WHERE ui.ups_state = 'IN PROGRESS'
          AND EXISTS (
              SELECT 1 FROM `tabUPS Event` cr
              WHERE cr.ups_instance = ui.name
                AND cr.event_type = 'CANCEL_REQUEST'
                AND cr.event_timestamp < %(cutoff)s
          )
          AND NOT EXISTS (
              SELECT 1 FROM `tabUPS Event` fin
              WHERE fin.ups_instance = ui.name
                AND fin.event_type IN ('COMPLETE', 'CANCEL')
                AND fin.event_timestamp >= %(cutoff)s
          )
        """,
        {"cutoff": cutoff_str},
    )
    return result[0][0] if result else 0


# ---------------------------------------------------------------------------
# T021: claim_workitem
# ---------------------------------------------------------------------------


@frappe.whitelist()
def claim_workitem(ups_uid, performing_aet=None):
    """
    Claim a SCHEDULED workitem (atomic claim + state transition to IN PROGRESS).

    Generates a Transaction UID, calls dcm4chee-arc, then updates the local
    mirror.  On 409 Conflict returns success=False (no exception raised) so
    the UI can display a friendly message and refresh the row.

    Accessible to: UPS Technologist, UPS Supervisor.
    """
    frappe.only_for(["UPS Technologist", "UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)
    if doc.ups_state != "SCHEDULED":
        return {
            "success": False,
            "message": _("Workitem is not SCHEDULED (current state: {0}).").format(doc.ups_state),
        }

    transaction_uid = "2.25." + str(uuid.uuid4().int)
    settings = frappe.get_single("UPS Integration Settings")
    aet = performing_aet or settings.dicom_aet

    # Build raw request for audit
    raw_req = {
        "00741000": {"vr": "CS", "Value": ["IN PROGRESS"]},
        "00081195": {"vr": "UI", "Value": [transaction_uid]},
    }
    import json as _json

    raw_req_str = _json.dumps(raw_req)
    http_status = None
    raw_resp_str = None

    try:
        resp = DICOMwebClient().change_state(ups_uid, "IN PROGRESS", transaction_uid)
        http_status = resp.status_code
        raw_resp_str = resp.text or ""
    except ConflictError as exc:
        return {
            "success": False,
            "message": _("This step has already been claimed by another user."),
            "http_status": exc.http_status,
        }
    except (BadRequestError, ServerError, UPSClientError) as exc:
        frappe.log_error(
            title="UPS claim_workitem error",
            message=f"ups_uid={ups_uid} error={exc}",
        )
        frappe.throw(_("dcm4chee-arc error: {0}").format(str(exc)))

    # Persist to local mirror
    doc.transaction_uid = transaction_uid
    doc.performing_aet = aet
    doc.claimed_by = frappe.session.user
    doc.claimed_at = now_datetime()
    doc.ups_state = "IN PROGRESS"
    doc.flags.ignore_permissions = True
    doc.save()

    doc.append_event(
        "CLAIM",
        old_state="SCHEDULED",
        new_state="IN PROGRESS",
        details=f"Claimed by {frappe.session.user} via portal",
        http_status=http_status,
        raw_request=raw_req_str,
        raw_response=raw_resp_str,
        transaction_uid=transaction_uid,
    )

    frappe.publish_realtime(
        "ups_state_change",
        {
            "ups_instance_uid": ups_uid,
            "old_state": "SCHEDULED",
            "new_state": "IN PROGRESS",
            "claimed_by": frappe.session.user,
        },
        room="ups_dashboard",
    )

    return {"success": True, "transaction_uid": transaction_uid}


# ---------------------------------------------------------------------------
# T022: complete_workitem
# ---------------------------------------------------------------------------


@frappe.whitelist()
def complete_workitem(ups_uid, performed_study_uid=None):
    """
    Complete an IN PROGRESS workitem (transition to COMPLETED).

    The calling user must be the one who claimed the workitem, or a Supervisor.

    Accessible to: UPS Technologist, UPS Supervisor.
    """
    frappe.only_for(["UPS Technologist", "UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)

    if doc.ups_state != "IN PROGRESS":
        frappe.throw(
            _("Workitem is not IN PROGRESS (current state: {0}).").format(doc.ups_state),
            frappe.ValidationError,
        )

    # Non-supervisors can only complete workitems they claimed
    is_supervisor = "UPS Supervisor" in frappe.get_roles(frappe.session.user)
    if not is_supervisor and doc.claimed_by != frappe.session.user:
        frappe.throw(
            _("You can only complete workitems you have claimed."),
            frappe.PermissionError,
        )

    if not doc.transaction_uid:
        frappe.throw(
            _("Transaction UID missing — this workitem cannot be completed. Contact your supervisor."),
            frappe.ValidationError,
        )

    import json as _json

    raw_req = {
        "00741000": {"vr": "CS", "Value": ["COMPLETED"]},
        "00081195": {"vr": "UI", "Value": [doc.transaction_uid]},
    }
    raw_req_str = _json.dumps(raw_req)
    http_status = None
    raw_resp_str = None

    try:
        resp = DICOMwebClient().change_state(ups_uid, "COMPLETED", doc.transaction_uid)
        http_status = resp.status_code
        raw_resp_str = resp.text or ""
    except BadRequestError as exc:
        frappe.throw(
            _("Transaction UID mismatch — this workitem may have changed. Contact your supervisor."),
            frappe.ValidationError,
        )
    except (ServerError, UPSClientError) as exc:
        frappe.log_error(title="UPS complete_workitem error", message=f"ups_uid={ups_uid} error={exc}")
        frappe.throw(_("dcm4chee-arc error: {0}").format(str(exc)))

    old_state = doc.ups_state
    if performed_study_uid:
        doc.performed_study_uid = performed_study_uid
    doc.ups_state = "COMPLETED"
    doc.flags.ignore_permissions = True
    doc.save()

    doc.append_event(
        "COMPLETE",
        old_state=old_state,
        new_state="COMPLETED",
        details=f"Completed by {frappe.session.user}",
        http_status=http_status,
        raw_request=raw_req_str,
        raw_response=raw_resp_str,
    )

    frappe.publish_realtime(
        "ups_state_change",
        {"ups_instance_uid": ups_uid, "old_state": old_state, "new_state": "COMPLETED"},
        room="ups_dashboard",
    )

    return {"success": True}


# ---------------------------------------------------------------------------
# US2 actions (T026-T028) — Supervisor cancel / reassign / reschedule
# ---------------------------------------------------------------------------


@frappe.whitelist()
def cancel_workitem(ups_uid, reason=None):
    """
    Cancel a UPS workitem (Supervisor only).

    For SCHEDULED workitems: sends advisory `cancelrequest` first, then
    directly transitions state to CANCELED.
    For IN PROGRESS workitems: directly transitions state using the stored
    Transaction UID.

    Accessible to: UPS Supervisor.
    """
    frappe.only_for(["UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)
    reason = reason or "Supervisor cancellation"
    old_state = doc.ups_state

    if old_state not in ("SCHEDULED", "IN PROGRESS"):
        frappe.throw(
            _("Cannot cancel a workitem in state {0}.").format(old_state),
            frappe.ValidationError,
        )

    client = DICOMwebClient()
    http_status = None
    raw_resp_str = None

    try:
        if old_state == "SCHEDULED":
            # Advisory cancel request
            try:
                client.request_cancel(ups_uid, reason)
            except UPSClientError:
                pass  # cancelrequest is advisory; continue to direct state change

            # Direct state transition (no transaction_uid for SCHEDULED → CANCELED)
            resp = client.change_state(ups_uid, "CANCELED", transaction_uid=None, reason=reason)
            http_status = resp.status_code
            raw_resp_str = resp.text or ""

        else:  # IN PROGRESS
            resp = client.change_state(ups_uid, "CANCELED", doc.transaction_uid, reason=reason)
            http_status = resp.status_code
            raw_resp_str = resp.text or ""

    except (BadRequestError, ConflictError, UPSClientError) as exc:
        frappe.log_error(title="UPS cancel_workitem error", message=f"ups_uid={ups_uid} error={exc}")
        frappe.throw(_("dcm4chee-arc error while cancelling: {0}").format(str(exc)))

    doc.ups_state = "CANCELED"
    doc.flags.ignore_permissions = True
    doc.save()

    doc.append_event(
        "CANCEL",
        old_state=old_state,
        new_state="CANCELED",
        details=f"Cancelled by supervisor {frappe.session.user}: {reason}",
        http_status=http_status,
        raw_response=raw_resp_str,
    )

    frappe.publish_realtime(
        "ups_state_change",
        {"ups_instance_uid": ups_uid, "old_state": old_state, "new_state": "CANCELED"},
        room="ups_dashboard",
    )

    return {"success": True}


@frappe.whitelist()
def reassign_workitem(ups_uid, new_aet):
    """
    Reassign a workitem to a different AE Title (Supervisor only).

    Accessible to: UPS Supervisor.
    """
    frappe.only_for(["UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("AE Mapping", new_aet):
        frappe.throw(_("AE Mapping {0} not found.").format(new_aet), frappe.ValidationError)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)
    old_aet = doc.scheduled_station_aet

    import json as _json

    # Resolve station name code from AE Mapping (FR-001 / SC-002: use Station Name Code,
    # not the legacy Scheduled Human Performers Sequence tag)
    ae_map = frappe.db.get_value(
        "AE Mapping", new_aet,
        ["station_name", "display_name"],
        as_dict=True,
    ) or {}
    station_code    = ae_map.get("station_name") or new_aet
    station_meaning = ae_map.get("display_name") or station_code

    attributes = {
        "00404025": {          # Scheduled Station Name Code Sequence (0040,4025)
            "vr": "SQ",
            "Value": [{
                "00080100": {"vr": "SH", "Value": [station_code]},
                "00080102": {"vr": "SH", "Value": ["LOCAL"]},
                "00080104": {"vr": "LO", "Value": [station_meaning]},
            }],
        }
    }

    try:
        resp = DICOMwebClient().update_workitem(
            ups_uid, attributes, transaction_uid=doc.transaction_uid
        )
        http_status = resp.status_code
        raw_resp_str = resp.text or ""
    except NotFoundError:
        # Workitem missing from dcm4chee — push it first, then retry.
        try:
            _push_doc_to_dcm4chee(doc)
            resp = DICOMwebClient().update_workitem(
                ups_uid, attributes, transaction_uid=doc.transaction_uid
            )
            http_status = resp.status_code
            raw_resp_str = resp.text or ""
        except (BadRequestError, ConflictError, ServerError, UPSClientError) as exc:
            frappe.log_error(title="UPS reassign_workitem error (after push)", message=f"ups_uid={ups_uid} error={exc}")
            frappe.throw(_("dcm4chee-arc error while reassigning: {0}").format(str(exc)))
    except (BadRequestError, ServerError, UPSClientError) as exc:
        frappe.log_error(title="UPS reassign_workitem error", message=f"ups_uid={ups_uid} error={exc}")
        frappe.throw(_("dcm4chee-arc error while reassigning: {0}").format(str(exc)))

    doc.scheduled_station_aet = new_aet
    doc.flags.ignore_permissions = True
    doc.save()

    doc.append_event(
        "REASSIGN",
        old_state=doc.ups_state,
        new_state=doc.ups_state,
        details=f"Reassigned from {old_aet} to {new_aet} by {frappe.session.user}",
        http_status=http_status,
        raw_request=_json.dumps(attributes),
        raw_response=raw_resp_str,
    )

    frappe.publish_realtime(
        "ups_state_change",
        {"ups_instance_uid": ups_uid, "new_aet": new_aet},
        room="ups_dashboard",
    )

    return {"success": True}


@frappe.whitelist()
def reschedule_workitem(ups_uid):
    """
    Reschedule a CANCELED workitem back to SCHEDULED (Supervisor only).

    Uses the dcm4chee-arc proprietary reschedule endpoint.

    Accessible to: UPS Supervisor.
    """
    frappe.only_for(["UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)

    try:
        resp = DICOMwebClient().reschedule_workitem(ups_uid)
        http_status = resp.status_code
        raw_resp_str = resp.text or ""
    except (BadRequestError, ServerError, UPSClientError) as exc:
        frappe.log_error(title="UPS reschedule_workitem error", message=f"ups_uid={ups_uid} error={exc}")
        frappe.throw(_("dcm4chee-arc error while rescheduling: {0}").format(str(exc)))

    old_state = doc.ups_state
    doc.ups_state = "SCHEDULED"
    doc.transaction_uid = None
    doc.performing_aet = None
    doc.claimed_by = None
    doc.claimed_at = None
    doc.flags.ignore_permissions = True
    doc.save()

    doc.append_event(
        "RECONCILE",
        old_state=old_state,
        new_state="SCHEDULED",
        details=f"Rescheduled by {frappe.session.user} via dcm4chee proprietary endpoint",
        http_status=http_status,
        raw_response=raw_resp_str,
    )

    frappe.publish_realtime(
        "ups_state_change",
        {"ups_instance_uid": ups_uid, "old_state": old_state, "new_state": "SCHEDULED"},
        room="ups_dashboard",
    )

    return {"success": True}


# ---------------------------------------------------------------------------
# US3 actions (T031-T034) — Audit / Reconciliation
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_event_history(ups_uid):
    """
    Return the full event history for a workitem in ascending chronological order.

    Accessible to all three portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)
    _validate_dicom_uid(ups_uid)

    is_auditor = any(r in frappe.get_roles() for r in ["UPS Supervisor", "UPS Integration Engineer"])

    fields = [
        "name",
        "event_type",
        "actor",
        "actor_aet",
        "event_timestamp",
        "old_state",
        "new_state",
        "transaction_uid",
        "details",
        "http_status",
    ]
    if is_auditor:
        fields.append("raw_request")

    events = frappe.get_list(
        "UPS Event",
        filters={"ups_instance": ups_uid},
        fields=fields,
        order_by="event_timestamp asc",
        limit_page_length=500,
    )

    return {"events": events}


@frappe.whitelist()
def export_audit_log(from_date=None, to_date=None, event_type=None, ups_uid=None, fmt="csv"):
    """
    Export UPS Event records as CSV or JSON for a date/filter range.

    Target: 10,000 rows in under 60 seconds (SC-004).

    Accessible to: UPS Supervisor, UPS Integration Engineer.
    """
    frappe.only_for(["UPS Supervisor", "UPS Integration Engineer"])

    conditions = []
    params = {}

    if from_date:
        conditions.append("event_timestamp >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("event_timestamp <= %(to_date)s")
        params["to_date"] = to_date
    if event_type:
        conditions.append("event_type = %(event_type)s")
        params["event_type"] = event_type
    if ups_uid:
        conditions.append("ups_instance = %(ups_uid)s")
        params["ups_uid"] = ups_uid

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = frappe.db.sql(
        f"""
        SELECT ups_instance, event_type, actor, actor_aet, event_timestamp,
               old_state, new_state, transaction_uid, details, http_status
        FROM `tabUPS Event`
        {where}
        ORDER BY event_timestamp ASC
        LIMIT 50000
        """,
        params,
        as_dict=True,
    )

    if fmt == "json":
        return rows

    # CSV export
    import csv
    import io

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        writer = csv.writer(output)
        writer.writerow(["ups_instance", "event_type", "actor", "actor_aet",
                         "event_timestamp", "old_state", "new_state",
                         "transaction_uid", "details", "http_status"])

    frappe.local.response["type"] = "download"
    frappe.local.response["doctype"] = "UPS Audit Log"
    frappe.local.response["filetype"] = "csv"
    frappe.local.response["filename"] = "ups_audit_log.csv"
    frappe.local.response.update(
        {
            "type": "download",
            "filename": "ups_audit_log.csv",
            "filecontent": output.getvalue(),
            "content_type": "text/csv; charset=utf-8",
        }
    )


@frappe.whitelist()
def get_reconciliation_diff():
    """
    Compare the local UPS mirror against live dcm4chee-arc state.

    Returns a list of discrepancies with issue types:
    - STATE_MISMATCH: local and remote states differ
    - MISSING_LOCALLY: workitem exists in dcm4chee but not in local DB
    - ORPHANED_CLAIM: local IN PROGRESS with cancel_request > 30 min, no final event
    - PENDING_CANCEL_IGNORED: CANCEL_REQUEST event without subsequent CANCEL within 30 min

    Accessible to: UPS Supervisor, UPS Integration Engineer.
    """
    frappe.only_for(["UPS Supervisor", "UPS Integration Engineer"])

    try:
        remote_items = DICOMwebClient().get_worklist({})
    except (ServerError, UPSClientError) as exc:
        frappe.throw(_("Could not reach dcm4chee-arc: {0}").format(str(exc)))

    remote_by_uid = {}
    for item in remote_items:
        uid = (item.get("00080018") or {}).get("Value", [None])[0]
        state = (item.get("00741000") or {}).get("Value", [None])[0]
        if uid:
            remote_by_uid[uid] = state

    discrepancies = []
    cutoff = now_datetime() - timedelta(minutes=30)

    # Check all local active records against remote
    local_items = frappe.get_list(
        "UPS Instance",
        filters={"ups_state": ["in", ["SCHEDULED", "IN PROGRESS"]]},
        fields=["name", "ups_state"],
    )

    for local in local_items:
        uid = local["name"]
        local_state = local["ups_state"]

        remote_state = remote_by_uid.get(uid)
        if remote_state is None:
            discrepancies.append(
                {
                    "ups_uid": uid,
                    "issue_type": "MISSING_LOCALLY",
                    "local_state": local_state,
                    "remote_state": None,
                    "recommended_action": "accept_remote or disregard if workitem completed externally",
                }
            )
            continue

        if remote_state != local_state:
            discrepancies.append(
                {
                    "ups_uid": uid,
                    "issue_type": "STATE_MISMATCH",
                    "local_state": local_state,
                    "remote_state": remote_state,
                    "recommended_action": "accept_remote to pull fresh state from dcm4chee-arc",
                }
            )

        # Check for orphaned claim
        if local_state == "IN PROGRESS":
            cancel_req = frappe.db.exists(
                "UPS Event",
                {
                    "ups_instance": uid,
                    "event_type": "CANCEL_REQUEST",
                    "event_timestamp": ["<", cutoff],
                },
            )
            if cancel_req:
                final = frappe.db.exists(
                    "UPS Event",
                    {
                        "ups_instance": uid,
                        "event_type": ["in", ["COMPLETE", "CANCEL"]],
                        "event_timestamp": [">=", cutoff],
                    },
                )
                if not final:
                    discrepancies.append(
                        {
                            "ups_uid": uid,
                            "issue_type": "ORPHANED_CLAIM",
                            "local_state": local_state,
                            "remote_state": remote_state,
                            "recommended_action": "reschedule or cancel workitem via supervisor panel",
                        }
                    )

    # Check for workitems present in dcm4chee but not locally
    local_uids = {item["name"] for item in local_items}
    for remote_uid, remote_state in remote_by_uid.items():
        if remote_uid not in local_uids:
            discrepancies.append(
                {
                    "ups_uid": remote_uid,
                    "issue_type": "MISSING_LOCALLY",
                    "local_state": None,
                    "remote_state": remote_state,
                    "recommended_action": "accept_remote to create local mirror entry",
                }
            )

    return {"discrepancies": discrepancies, "total": len(discrepancies)}


@frappe.whitelist()
def accept_reconciliation_item(ups_uid, action):
    """
    Accept a reconciliation discrepancy by applying the suggested resolution.

    ``action`` must be one of:
    - ``"accept_remote"``: pull latest state from dcm4chee-arc and overwrite local
    - ``"accept_local"``: push local state to dcm4chee-arc (limited cases)

    Accessible to: UPS Supervisor, UPS Integration Engineer.
    """
    frappe.only_for(["UPS Supervisor", "UPS Integration Engineer"])
    _validate_dicom_uid(ups_uid)

    if action == "accept_remote":
        client = DICOMwebClient()
        try:
            remote_item = client.get_workitem(ups_uid)
        except NotFoundError:
            frappe.throw(_("Workitem {0} not found in dcm4chee-arc.").format(ups_uid))
        except (ServerError, UPSClientError) as exc:
            frappe.throw(_("dcm4chee-arc error: {0}").format(str(exc)))

        # Import the upsert helper from tasks
        from healthcare.ups_worklist_portal.tasks import _upsert_workitem  # noqa: PLC0415

        _upsert_workitem(remote_item)
        frappe.db.commit()

        doc = frappe.get_doc("UPS Instance", ups_uid)
        doc.append_event(
            "RECONCILE",
            old_state=None,
            new_state=doc.ups_state,
            details=f"Reconciliation: accepted remote state from dcm4chee-arc by {frappe.session.user}",
        )

        frappe.publish_realtime(
            "ups_state_change",
            {"ups_instance_uid": ups_uid, "new_state": doc.ups_state, "source": "reconciliation"},
            room="ups_dashboard",
        )

        return {"success": True, "new_state": doc.ups_state}

    elif action == "accept_local":
        if not frappe.db.exists("UPS Instance", ups_uid):
            frappe.throw(_("Workitem {0} not found locally.").format(ups_uid), frappe.DoesNotExistError)

        doc = frappe.get_doc("UPS Instance", ups_uid)
        # Only supervisors can push local state back to dcm4chee
        frappe.only_for(["UPS Supervisor"])

        frappe.throw(
            _("accept_local is not yet implemented — contact integration engineer to resolve manually."),
            frappe.ValidationError,
        )

    else:
        frappe.throw(_("Unknown reconciliation action: {0}. Use 'accept_remote' or 'accept_local'.").format(action))


# ---------------------------------------------------------------------------
# IHE RRR-WF §40.4.2 Use-Case specific worklist views
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_worklist_by_type(worklist_type="open", limit=50, offset=0):
    """
    Return a paginated worklist segmented by IHE RRR-WF §40.4.2 use case.

    worklist_type:
      ``open``             — UC1: SCHEDULED, no scheduled_performer_aet (community pool).
      ``assigned``         — UC2/UC4: SCHEDULED, scheduled_performer_aet is set (assigned reads).
      ``in_progress``      — UC3/UC5/UC6: IN PROGRESS (all claimed items).
      ``cancel_requested`` — UC5: IN PROGRESS with a pending cancel request.
      ``addendum``         — UC3: COMPLETED within the last 7 days (addendum candidates).

    Accessible to all three portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)

    limit = int(limit)
    offset = int(offset)

    if worklist_type == "open":
        # UC1 — unassigned SCHEDULED items (community pool, first-come first-served)
        filters = {
            "ups_state": "SCHEDULED",
            "scheduled_performer_aet": ["in", ["", None]],
        }
        fields = [
            "name", "ups_state", "priority", "scheduled_datetime",
            "modality", "scheduled_station_aet", "scheduled_station_name",
            "patient_name", "patient_id", "accession_number", "protocol_name", "procedure_description",
            "scheduled_station_class_code",
        ]
        order_by = "priority asc, scheduled_datetime asc"

    elif worklist_type == "assigned":
        # UC2/UC4 — SCHEDULED items that have been assigned to a specific performer.
        # NOTE: ["not in", ["", None]] generates SQL `NOT IN ('', NULL)` which
        # evaluates to UNKNOWN for every row due to NULL comparison rules.
        # Use list-based filters with "is set" to generate correct IS NOT NULL SQL.
        filters = [
            ["ups_state", "=", "SCHEDULED"],
            ["scheduled_performer_aet", "is", "set"],
            ["scheduled_performer_aet", "!=", ""],
        ]
        fields = [
            "name", "ups_state", "priority", "scheduled_datetime",
            "modality", "scheduled_station_aet", "scheduled_station_name",
            "scheduled_performer_aet",
            "patient_name", "patient_id", "accession_number", "protocol_name", "procedure_description",
            "scheduled_station_class_code",
        ]
        order_by = "scheduled_datetime asc"

    elif worklist_type == "in_progress":
        # UC3/UC5/UC6 — all claimed (IN PROGRESS) items
        filters = {"ups_state": "IN PROGRESS"}
        fields = [
            "name", "ups_state", "priority", "scheduled_datetime",
            "modality", "scheduled_station_aet", "scheduled_station_name",
            "patient_name", "patient_id", "accession_number", "protocol_name", "procedure_description",
            "claimed_by", "claimed_at", "cancel_requested_at", "cancel_request_reason",
        ]
        order_by = "claimed_at asc"

    elif worklist_type == "cancel_requested":
        # UC5 — IN PROGRESS items with a pending cancel request
        filters = {
            "ups_state": "IN PROGRESS",
            "cancel_requested_at": ["is", "set"],
        }
        fields = [
            "name", "ups_state", "priority", "scheduled_datetime",
            "modality", "scheduled_station_name",
            "patient_name", "patient_id", "accession_number",
            "protocol_name", "procedure_description",
            "claimed_by", "claimed_at", "cancel_requested_at",
            "cancel_request_reason",
        ]
        order_by = "cancel_requested_at asc"

    elif worklist_type == "addendum":
        # UC3 — COMPLETED items within the last 7 days (candidates for addendum)
        from frappe.utils import add_days

        cutoff = add_days(frappe.utils.now_datetime(), -7)
        filters = {
            "ups_state": "COMPLETED",
            "modified": [">=", cutoff],
        }
        fields = [
            "name", "ups_state", "priority", "scheduled_datetime",
            "modality", "scheduled_station_name",
            "patient_name", "patient_id", "accession_number",
            "protocol_name", "procedure_description",
            "claimed_by", "performed_study_uid", "addendum_for",
        ]
        order_by = "modified desc"

    else:
        frappe.throw(
            _("Unknown worklist_type: {0}. Use open|assigned|in_progress|cancel_requested|addendum.").format(
                worklist_type
            ),
            frappe.ValidationError,
        )

    # frappe.db.count() mishandles filters like ["in", ["", None]] that need
    # NULL-safe SQL (field = '' OR field IS NULL). frappe.get_list generates the
    # correct SQL, so we use it for an accurate total count too.
    total = len(frappe.get_list("UPS Instance", filters=filters, fields=["name"]))
    items = frappe.get_list(
        "UPS Instance",
        filters=filters,
        fields=fields,
        order_by=order_by,
        limit_page_length=limit,
        limit_start=offset,
    )

    return {"total": total, "items": items, "worklist_type": worklist_type}


# ---------------------------------------------------------------------------
# UC2/UC4 — Assign workitem to a specific Task Performer
# ---------------------------------------------------------------------------


def _push_doc_to_dcm4chee(doc):
    """
    Push a UPS Instance doc to dcm4chee-arc via N-CREATE (UPS-RS POST).

    Called automatically when an assign/reassign operation receives a 404,
    meaning the workitem was seeded locally (e.g. by a demo script) but was
    never pushed to dcm4chee (typically because it was offline at seed time).

    Returns the Location URL returned by dcm4chee, or raises on failure.
    """
    ups_uid = doc.name

    dt = doc.scheduled_datetime
    if hasattr(dt, "strftime"):
        dt_str = dt.strftime("%Y%m%d%H%M%S.000000")
    else:
        raw = str(dt).replace("-", "").replace(":", "").replace(" ", "")
        dt_str = raw[:14].ljust(14, "0") + ".000000"

    dob_str = (doc.patient_birth_date or "").replace("-", "")

    # Look up AE Mapping to get station name code and class code for DICOM payload.
    ae_map = frappe.db.get_value(
        "AE Mapping",
        doc.scheduled_station_aet,
        ["station_name", "station_class_code", "display_name"],
        as_dict=True,
    ) if doc.scheduled_station_aet else None

    station_code    = (ae_map.station_name    or doc.scheduled_station_aet or "") if ae_map else (doc.scheduled_station_aet or "")
    station_meaning = (ae_map.display_name    or station_code)                     if ae_map else station_code
    station_class   = (ae_map.station_class_code or "")                            if ae_map else (doc.scheduled_station_class_code or "")

    payload = {
        "00741000": {"vr": "CS", "Value": ["SCHEDULED"]},
        "00741200": {"vr": "CS", "Value": [doc.priority or "MEDIUM"]},
        "00741204": {"vr": "LO", "Value": [doc.protocol_name or doc.procedure_description or ""]},
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
        **({                           # Scheduled Station Class Code Sequence (0040,4026) — omit if empty
            "00404026": {
                "vr": "SQ",
                "Value": [{
                    "00080100": {"vr": "SH", "Value": [station_class]},
                    "00080102": {"vr": "SH", "Value": ["LOCAL"]},
                    "00080104": {"vr": "LO", "Value": [station_class]},
                }],
            }
        } if station_class else {}),
        "00404018": {            "vr": "SQ",
            "Value": [{
                "00080100": {"vr": "SH", "Value": ["121726"]},
                "00080102": {"vr": "SH", "Value": ["DCM"]},
                "00080104": {"vr": "LO", "Value": ["Acquisition Protocol"]},
            }],
        },
        "00100020": {"vr": "LO", "Value": [doc.patient_id or ""]},
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": doc.patient_name or ""}]},
        "00100030": {"vr": "DA", "Value": [dob_str]},
        "00100040": {"vr": "CS", "Value": [doc.patient_sex or ""]},
        "00080050": {"vr": "SH", "Value": [doc.accession_number or ""]},
        "00401001": {"vr": "SH", "Value": [doc.requested_procedure_id or ""]},
        "00181030": {"vr": "LO", "Value": [doc.protocol_name or ""]},
    }

    location = DICOMwebClient().create_workitem(ups_uid, payload)
    frappe.log_error(
        title="UPS _push_doc_to_dcm4chee: late push OK",
        message=f"ups_uid={ups_uid} location={location}",
    )
    return location


@frappe.whitelist()
def assign_workitem(ups_uid, performer_aet, reason=None):
    """
    Assign (or re-assign) a SCHEDULED workitem to a specific Task Performer AET.

    Maps to the IHE RRR-WF Assigned Read (UC2) and Re-assignment (UC4) use cases.
    The scheduled_performer_aet is set; the Task Performer must still *claim*
    the workitem to begin work (sets transaction_uid + IN PROGRESS state).

    Accessible to: UPS Supervisor.
    """
    frappe.only_for(["UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)

    if doc.ups_state != "SCHEDULED":
        frappe.throw(
            _("Only SCHEDULED workitems can be assigned (current state: {0}).").format(doc.ups_state),
            frappe.ValidationError,
        )

    import json as _json

    old_performer = doc.scheduled_performer_aet or ""

    # Look up the station name code from the AE Mapping so we can populate
    # Scheduled Station Name Code Sequence (0040,4025) correctly.
    ae_map = frappe.db.get_value(
        "AE Mapping", performer_aet, ["station_name", "display_name"], as_dict=True
    )
    station_code    = (ae_map.station_name or performer_aet) if ae_map else performer_aet
    station_meaning = (ae_map.display_name or performer_aet) if ae_map else performer_aet

    attributes = {
        "00404025": {          # Scheduled Station Name Code Sequence
            "vr": "SQ",
            "Value": [{
                "00080100": {"vr": "SH", "Value": [station_code]},
                "00080102": {"vr": "SH", "Value": ["LOCAL"]},
                "00080104": {"vr": "LO", "Value": [station_meaning]},
            }],
        }
    }
    raw_req_str = _json.dumps(attributes)
    http_status = None
    raw_resp_str = None

    try:
        resp = DICOMwebClient().update_workitem(ups_uid, attributes, transaction_uid=None)
        http_status = resp.status_code
        raw_resp_str = resp.text or ""
    except NotFoundError:
        # Workitem exists locally but was never pushed to dcm4chee (e.g. seeded
        # while dcm4chee was offline).  Push it now, then retry the update.
        try:
            _push_doc_to_dcm4chee(doc)
            resp = DICOMwebClient().update_workitem(ups_uid, attributes, transaction_uid=None)
            http_status = resp.status_code
            raw_resp_str = resp.text or ""
        except (BadRequestError, ConflictError, ServerError, UPSClientError) as exc:
            frappe.log_error(title="UPS assign_workitem error (after push)", message=f"ups_uid={ups_uid} error={exc}")
            frappe.throw(_("dcm4chee-arc error while assigning: {0}").format(str(exc)))
    except (BadRequestError, ServerError, UPSClientError) as exc:
        frappe.log_error(title="UPS assign_workitem error", message=f"ups_uid={ups_uid} error={exc}")
        frappe.throw(_("dcm4chee-arc error while assigning: {0}").format(str(exc)))

    doc.scheduled_performer_aet = performer_aet
    doc.flags.ignore_permissions = True
    doc.save()

    event_type = "REASSIGN"
    detail_msg = (
        f"Re-assigned from {old_performer} to {performer_aet}"
        if old_performer
        else f"Assigned to {performer_aet}"
    )
    if reason:
        detail_msg += f": {reason}"

    doc.append_event(
        event_type,
        old_state="SCHEDULED",
        new_state="SCHEDULED",
        details=f"{detail_msg} by {frappe.session.user}",
        http_status=http_status,
        raw_request=raw_req_str,
        raw_response=raw_resp_str,
    )

    frappe.publish_realtime(
        "ups_state_change",
        {
            "ups_instance_uid": ups_uid,
            "old_state": "SCHEDULED",
            "new_state": "SCHEDULED",
            "scheduled_performer_aet": performer_aet,
            "event": event_type,
        },
        room="ups_dashboard",
    )

    return {"success": True, "scheduled_performer_aet": performer_aet}


# ---------------------------------------------------------------------------
# UC5 — Request workitem cancellation (Task Requester perspective)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def request_workitem_cancel(ups_uid, reason=None, contact_uri=None, contact_display_name=None):
    """
    Record a cancellation request for a UPS workitem (IHE RRR-WF §40.4.2.5).

    For SCHEDULED workitems: transitions directly to CANCELED (no performer to notify).
    For IN PROGRESS workitems: sends a cancel-request advisory to the Task Performer
    via dcm4chee-arc and flags the workitem locally so the performer can act on it.
    The workitem remains IN PROGRESS until the performer completes or cancels it.

    Accessible to: UPS Technologist, UPS Supervisor.
    """
    frappe.only_for(["UPS Technologist", "UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)
    reason = reason or "Cancellation requested by Task Requester"

    # Build the DICOM+JSON N-EVENT-REPORT payload for local audit storage
    # (mirrors what is sent to dcm4chee so EventReportInfo can render it)
    def _build_cancel_request_payload(reason, contact_uri=None, contact_display_name=None):
        import json as _json
        # (0074,1238) Reason For Cancellation — VR: LT (Long Text)
        payload = {
            "00741238": {"vr": "LT", "Value": [reason]},
        }
        if contact_uri:
            payload["0074100A"] = {"vr": "UR", "Value": [contact_uri]}
        if contact_display_name:
            payload["0074100C"] = {"vr": "LO", "Value": [contact_display_name]}
        return _json.dumps(payload)

    if doc.ups_state not in ("SCHEDULED", "IN PROGRESS"):
        frappe.throw(
            _("Cannot request cancellation for workitem in state {0}.").format(doc.ups_state),
            frappe.ValidationError,
        )

    client = DICOMwebClient()
    http_status = None
    raw_resp_str = None

    if doc.ups_state == "SCHEDULED":
        # No performer yet — cancel directly (Use Case #5 simple path)
        try:
            resp = client.request_cancel(ups_uid, reason,
                                         contact_uri=contact_uri,
                                         contact_display_name=contact_display_name)
            http_status = resp.status_code if hasattr(resp, "status_code") else None
            raw_resp_str = getattr(resp, "text", "") or ""
        except UPSClientError:
            pass  # advisory; continue

        try:
            resp2 = client.change_state(ups_uid, "CANCELED", transaction_uid=None, reason=reason)
            http_status = resp2.status_code
            raw_resp_str = resp2.text or ""
        except (BadRequestError, ConflictError, UPSClientError) as exc:
            frappe.log_error(
                title="UPS request_workitem_cancel (SCHEDULED) error",
                message=f"ups_uid={ups_uid} error={exc}",
            )
            frappe.throw(_("dcm4chee-arc error: {0}").format(str(exc)))

        old_state = doc.ups_state
        doc.ups_state = "CANCELED"
        doc.flags.ignore_permissions = True
        doc.save()

        doc.append_event(
            "CANCEL",
            old_state=old_state,
            new_state="CANCELED",
            details=f"Cancel requested by {frappe.session.user}: {reason}",
            http_status=http_status,
            raw_request=_build_cancel_request_payload(reason, contact_uri, contact_display_name),
            raw_response=raw_resp_str,
        )

        frappe.publish_realtime(
            "ups_state_change",
            {"ups_instance_uid": ups_uid, "old_state": old_state, "new_state": "CANCELED"},
            room="ups_dashboard",
        )

        return {"success": True, "new_state": "CANCELED"}

    else:
        # IN PROGRESS — send advisory cancel request; performer decides (Use Case #5 main path)
        try:
            resp = client.request_cancel(ups_uid, reason,
                                         contact_uri=contact_uri,
                                         contact_display_name=contact_display_name)
            http_status = resp.status_code if hasattr(resp, "status_code") else None
            raw_resp_str = getattr(resp, "text", "") or ""
        except UPSClientError as exc:
            frappe.log_error(
                title="UPS request_workitem_cancel (IN PROGRESS) advisory error",
                message=f"ups_uid={ups_uid} error={exc}",
            )
            # Non-fatal: record locally even if advisory failed

        doc.cancel_requested_at = now_datetime()
        doc.cancel_request_reason = reason
        doc.flags.ignore_permissions = True
        doc.save()

        doc.append_event(
            "CANCEL_REQUEST",
            old_state="IN PROGRESS",
            new_state="IN PROGRESS",
            details=f"Cancel requested by {frappe.session.user}: {reason}",
            http_status=http_status,
            raw_request=_build_cancel_request_payload(reason, contact_uri, contact_display_name),
            raw_response=raw_resp_str,
        )

        frappe.publish_realtime(
            "ups_state_change",
            {
                "ups_instance_uid": ups_uid,
                "old_state": "IN PROGRESS",
                "new_state": "IN PROGRESS",
                "cancel_requested": True,
                "reason": reason,
            },
            room="ups_dashboard",
        )

        return {
            "success": True,
            "new_state": "IN PROGRESS",
            "cancel_requested": True,
            "message": _(
                "Cancel request sent to Task Performer. "
                "The workitem remains IN PROGRESS until the performer acts on it."
            ),
        }


# ---------------------------------------------------------------------------
# UC6 — Task Performer self-cancels due to local failure
# ---------------------------------------------------------------------------


@frappe.whitelist()
def performer_cancel_workitem(ups_uid, reason=None):
    """
    Task Performer cancels their own claimed workitem due to a local failure
    (IHE RRR-WF §40.4.2.6 Failure Use Case).

    The calling user must be the performer who claimed the workitem (or a Supervisor).
    After cancellation the Task Requester is notified and may create a replacement task.

    Accessible to: UPS Technologist, UPS Supervisor.
    """
    frappe.only_for(["UPS Technologist", "UPS Supervisor"])
    _validate_dicom_uid(ups_uid)

    if not frappe.db.exists("UPS Instance", ups_uid):
        frappe.throw(_("Workitem {0} not found.").format(ups_uid), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Instance", ups_uid)

    if doc.ups_state != "IN PROGRESS":
        frappe.throw(
            _("Only IN PROGRESS workitems can be self-cancelled (current state: {0}).").format(
                doc.ups_state
            ),
            frappe.ValidationError,
        )

    is_supervisor = "UPS Supervisor" in frappe.get_roles(frappe.session.user)
    if not is_supervisor and doc.claimed_by != frappe.session.user:
        frappe.throw(
            _("You can only cancel workitems you have claimed."),
            frappe.PermissionError,
        )

    if not doc.transaction_uid:
        frappe.throw(
            _("Transaction UID missing — cannot cancel. Contact your supervisor."),
            frappe.ValidationError,
        )

    reason = reason or "Task Performer cancelled due to local failure"
    import json as _json

    raw_req = {
        "00741000": {"vr": "CS", "Value": ["CANCELED"]},
        "00081195": {"vr": "UI", "Value": [doc.transaction_uid]},
    }
    raw_req_str = _json.dumps(raw_req)
    http_status = None
    raw_resp_str = None

    try:
        resp = DICOMwebClient().change_state(ups_uid, "CANCELED", doc.transaction_uid, reason=reason)
        http_status = resp.status_code
        raw_resp_str = resp.text or ""
    except (BadRequestError, ConflictError, UPSClientError) as exc:
        frappe.log_error(
            title="UPS performer_cancel_workitem error",
            message=f"ups_uid={ups_uid} error={exc}",
        )
        frappe.throw(_("dcm4chee-arc error while cancelling: {0}").format(str(exc)))

    old_state = doc.ups_state
    doc.ups_state = "CANCELED"
    doc.flags.ignore_permissions = True
    doc.save()

    doc.append_event(
        "CANCEL",
        old_state=old_state,
        new_state="CANCELED",
        details=f"Performer self-cancel by {frappe.session.user} (Failure UC6): {reason}",
        http_status=http_status,
        raw_request=raw_req_str,
        raw_response=raw_resp_str,
    )

    frappe.publish_realtime(
        "ups_state_change",
        {
            "ups_instance_uid": ups_uid,
            "old_state": old_state,
            "new_state": "CANCELED",
            "failure_reason": reason,
            "event": "PERFORMER_CANCEL",
        },
        room="ups_dashboard",
    )

    return {"success": True, "new_state": "CANCELED"}


# ---------------------------------------------------------------------------
# UC3 — Create an addendum workitem
# ---------------------------------------------------------------------------


@frappe.whitelist()
def create_addendum_workitem(original_uid, reason=None, priority="MEDIUM"):
    """
    Create a new UPS workitem as an addendum to a completed original workitem
    (IHE RRR-WF §40.4.2.3 Report Addendum Use Case).

    The new workitem:
    - has SCHEDULED state
    - references the original via ``addendum_for``
    - copies patient / study / modality details from the original
    - is immediately claimed by the creating performer

    Accessible to: UPS Technologist, UPS Supervisor.
    """
    frappe.only_for(["UPS Technologist", "UPS Supervisor"])
    _validate_dicom_uid(original_uid)

    if not frappe.db.exists("UPS Instance", original_uid):
        frappe.throw(_("Original workitem {0} not found.").format(original_uid), frappe.DoesNotExistError)

    original = frappe.get_doc("UPS Instance", original_uid)

    if original.ups_state != "COMPLETED":
        frappe.throw(
            _("Addendums can only be created for COMPLETED workitems (current state: {0}).").format(
                original.ups_state
            ),
            frappe.ValidationError,
        )

    if priority not in ("HIGH", "MEDIUM", "LOW"):
        priority = "MEDIUM"

    # Generate a new DICOM UID for the addendum workitem
    addendum_uid = "2.25." + str(uuid.uuid4().int)

    # Build DICOM+JSON payload for the new workitem
    import json as _json

    reason_text = reason or "Addendum to original read"
    payload = {
        "00080018": {"vr": "UI", "Value": [addendum_uid]},
        "00741000": {"vr": "CS", "Value": ["SCHEDULED"]},
        "00741200": {"vr": "CS", "Value": [priority]},
        "00404005": {
            "vr": "DT",
            "Value": [now_datetime().strftime("%Y%m%d%H%M%S")],
        },
        "00400100": {
            "vr": "SQ",
            "Value": [
                {
                    "00080060": {"vr": "CS", "Value": [original.modality or ""]},
                    "00400009": {
                        "vr": "SH",
                        "Value": [original.requested_procedure_id or ""],
                    },
                }
            ],
        },
        "00404021": {"vr": "CS", "Value": ["ADDENDUM"]},
        "00081030": {"vr": "LO", "Value": [reason_text]},
    }

    raw_payload_str = _json.dumps(payload)
    http_status = None
    raw_resp_str = None

    try:
        location_url = DICOMwebClient().create_workitem(addendum_uid, payload)
        http_status = 201
        raw_resp_str = location_url or ""
    except (BadRequestError, ConflictError, ServerError, UPSClientError) as exc:
        frappe.log_error(
            title="UPS create_addendum_workitem error",
            message=f"original_uid={original_uid} addendum_uid={addendum_uid} error={exc}",
        )
        frappe.throw(_("dcm4chee-arc error creating addendum workitem: {0}").format(str(exc)))

    settings = frappe.get_single("UPS Integration Settings")

    addendum_doc = frappe.get_doc(
        {
            "doctype": "UPS Instance",
            "name": addendum_uid,
            "ups_state": "SCHEDULED",
            "priority": priority,
            "scheduled_datetime": now_datetime(),
            "modality": original.modality,
            "scheduled_station_aet": original.scheduled_station_aet,
            "scheduled_station_name": original.scheduled_station_name,
            "requested_procedure_id": original.requested_procedure_id,
            "accession_number": original.accession_number,
            "study_instance_uid": original.study_instance_uid,
            "protocol_name": original.protocol_name,
            "procedure_description": reason_text,
            "patient_id": original.patient_id,
            "patient_name": original.patient_name,
            "patient_birth_date": original.patient_birth_date,
            "patient_sex": original.patient_sex,
            "addendum_for": original_uid,
            "ups_sync_status": "synced",
            "ups_sync_at": now_datetime(),
            "raw_payload": raw_payload_str,
        }
    )
    addendum_doc.flags.ignore_permissions = True
    addendum_doc.insert()

    addendum_doc.append_event(
        "CREATE",
        old_state=None,
        new_state="SCHEDULED",
        details=f"Addendum workitem created by {frappe.session.user} for original {original_uid}: {reason_text}",
        http_status=http_status,
        raw_request=raw_payload_str,
        raw_response=raw_resp_str,
    )

    # Also log on the original that an addendum was raised
    original.append_event(
        "ADDENDUM",
        old_state="COMPLETED",
        new_state="COMPLETED",
        details=f"Addendum raised by {frappe.session.user}: {reason_text} → new UID {addendum_uid}",
    )

    frappe.publish_realtime(
        "ups_state_change",
        {
            "ups_instance_uid": addendum_uid,
            "old_state": None,
            "new_state": "SCHEDULED",
            "addendum_for": original_uid,
            "event": "ADDENDUM_CREATED",
        },
        room="ups_dashboard",
    )

    return {"success": True, "addendum_uid": addendum_uid}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_dicom_uid(uid):
    """Raise ValidationError if uid is not a valid DICOM UID format."""
    import re

    if not uid or not re.match(r"^[0-2](\.[0-9]+)+$", str(uid)):
        frappe.throw(
            _("Invalid DICOM UID format: {0}").format(uid),
            frappe.ValidationError,
        )
