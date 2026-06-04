"""
Frappe whitelisted API methods for the Event Reports SPA.

All methods are accessible via:
    frappe.call("healthcare.ups_worklist_portal.api.event_reports.<method_name>", ...)

Access control:
 - get_event_list / get_event / get_event_summary: all portal roles
 - export_events_csv: Supervisor + Integration Engineer only
"""

import csv
import io
import json as _json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

try:
    from ups_worklist_portal.integrations.dicomweb_client import (
        DICOMwebClient as _DICOMwebClient,
        UPSClientError as _UPSClientError,
    )
    _HAS_UPS_CLIENT = True
except ImportError:
    _HAS_UPS_CLIENT = False

_ALL_PORTAL_ROLES = ["UPS Technologist", "UPS Supervisor", "UPS Integration Engineer"]
_AUDIT_ROLES = ["UPS Supervisor", "UPS Integration Engineer"]

# Event types exactly as stored in UPS Event
EVENT_TYPES = [
    "CREATE",
    "CLAIM",
    "UPDATE",
    "COMPLETE",
    "CANCEL",
    "CANCEL_REQUEST",
    "REASSIGN",
    "RECONCILE",
]

_EVENT_LIST_FIELDS = [
    "name",
    "ups_instance",
    "event_type",
    "event_timestamp",
    "actor",
    "actor_aet",
    "old_state",
    "new_state",
    "transaction_uid",
    "details",
    "http_status",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_filters(event_types, actor, ups_instance, actor_aet, from_datetime, to_datetime):
    filters = {}

    if event_types:
        if isinstance(event_types, str):
            try:
                event_types = _json.loads(event_types)
            except (ValueError, TypeError):
                event_types = [event_types]
        # Validate against known types to prevent injection
        safe = [t for t in event_types if t in EVENT_TYPES]
        if safe:
            filters["event_type"] = ["in", safe]

    if actor:
        filters["actor"] = ["like", f"%{frappe.db.escape(actor, percent=False)}%"]

    if ups_instance:
        filters["ups_instance"] = ["like", f"%{frappe.db.escape(ups_instance, percent=False)}%"]

    if actor_aet:
        filters["actor_aet"] = ["like", f"%{frappe.db.escape(actor_aet, percent=False)}%"]

    if from_datetime and to_datetime:
        filters["event_timestamp"] = ["between", [from_datetime, to_datetime]]
    elif from_datetime:
        filters["event_timestamp"] = [">=", from_datetime]
    elif to_datetime:
        filters["event_timestamp"] = ["<=", to_datetime]

    return filters


# ---------------------------------------------------------------------------
# get_event_list
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_event_list(
    event_types=None,
    actor=None,
    ups_instance=None,
    actor_aet=None,
    from_datetime=None,
    to_datetime=None,
    limit=50,
    offset=0,
):
    """
    Return a paginated list of UPS Event records with optional filters.

    Accessible to all portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    filters = _build_filters(event_types, actor, ups_instance, actor_aet, from_datetime, to_datetime)

    total = frappe.db.count("UPS Event", filters)
    items = frappe.get_list(
        "UPS Event",
        filters=filters,
        fields=_EVENT_LIST_FIELDS,
        order_by="event_timestamp desc",
        limit_page_length=limit,
        limit_start=offset,
    )

    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# get_event
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_event(name):
    """
    Return full details for a single UPS Event, including raw audit data
    when the caller has perm level 1 access.

    Accessible to all portal roles; raw_request / raw_response are
    perm-level-1 fields (Frappe enforces visibility automatically).
    """
    frappe.only_for(_ALL_PORTAL_ROLES)

    if not frappe.db.exists("UPS Event", name):
        frappe.throw(_("UPS Event {0} not found.").format(name), frappe.DoesNotExistError)

    doc = frappe.get_doc("UPS Event", name)
    result = doc.as_dict()

    # Include raw data only for audit roles.
    # Exception: CANCEL_REQUEST raw_request contains only user-entered contact
    # info (reason, Contact URI, Contact Display Name) — not sensitive DICOM
    # protocol data. Frappe strips permlevel-1 fields via as_dict() for
    # non-audit roles, so we re-fetch raw_request directly from the DB for
    # CANCEL_REQUEST events.
    if not any(r in frappe.get_roles() for r in _AUDIT_ROLES):
        result.pop("raw_response", None)
        if result.get("event_type") == "CANCEL_REQUEST":
            result["raw_request"] = frappe.db.get_value("UPS Event", name, "raw_request")
        else:
            result.pop("raw_request", None)

    return result


# ---------------------------------------------------------------------------
# get_event_summary
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_event_summary(from_datetime=None, to_datetime=None):
    """
    Return counts per event_type for the given date range.

    Also returns a total count and counts for state transitions involving
    errors (http_status >= 400).

    Accessible to all portal roles.
    """
    frappe.only_for(_ALL_PORTAL_ROLES)

    base_filters = {}
    if from_datetime and to_datetime:
        base_filters["event_timestamp"] = ["between", [from_datetime, to_datetime]]
    elif from_datetime:
        base_filters["event_timestamp"] = [">=", from_datetime]
    elif to_datetime:
        base_filters["event_timestamp"] = ["<=", to_datetime]

    summary = {et: 0 for et in EVENT_TYPES}
    summary["TOTAL"] = 0
    summary["HTTP_ERROR"] = 0

    for event_type in EVENT_TYPES:
        f = dict(base_filters)
        f["event_type"] = event_type
        count = frappe.db.count("UPS Event", f)
        summary[event_type] = count
        summary["TOTAL"] += count

    # HTTP error count (status code >= 400)
    error_filters = dict(base_filters)
    error_filters["http_status"] = [">=", 400]
    summary["HTTP_ERROR"] = frappe.db.count("UPS Event", error_filters)

    return summary


# ---------------------------------------------------------------------------
# export_events_csv
# ---------------------------------------------------------------------------


@frappe.whitelist()
def export_events_csv(
    event_types=None,
    actor=None,
    ups_instance=None,
    actor_aet=None,
    from_datetime=None,
    to_datetime=None,
):
    """
    Return all matching events as a CSV string (max 10 000 rows).

    Restricted to Supervisor and Integration Engineer roles only.
    """
    frappe.only_for(_AUDIT_ROLES)

    filters = _build_filters(event_types, actor, ups_instance, actor_aet, from_datetime, to_datetime)

    events = frappe.get_list(
        "UPS Event",
        filters=filters,
        fields=_EVENT_LIST_FIELDS,
        order_by="event_timestamp desc",
        limit_page_length=10000,
        limit_start=0,
    )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_EVENT_LIST_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for ev in events:
        writer.writerow({k: (ev.get(k) or "") for k in _EVENT_LIST_FIELDS})

    return {"csv": output.getvalue(), "count": len(events)}


# ---------------------------------------------------------------------------
# Filtered subscription management
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_filtered_subscriptions():
    """
    Return all locally-tracked Active filtered DICOM subscriptions.

    Restricted to audit roles (Supervisor + Integration Engineer).
    """
    frappe.only_for(_AUDIT_ROLES)
    return frappe.get_list(
        "UPS Filtered Subscription",
        filters={"status": "Active"},
        fields=[
            "name",
            "matching_tag",
            "matching_tag_label",
            "matching_value",
            "ws_url",
            "subscribed_at",
            "subscribed_by",
        ],
        order_by="subscribed_at desc",
    )


@frappe.whitelist()
def create_filtered_subscription(matching_tag, matching_tag_label, matching_value):
    """
    Subscribe the portal AE to a DICOM UPS Filtered Global Worklist.

    Sends POST to dcm4chee-arc with ``matching_tag=matching_value`` as a
    QIDO-style query parameter, then records the subscription locally.

    Common ``matching_tag`` values::

        "00741202"            Worklist Label          (e.g. "CT-POOL-A")
        "00404025.00080100"   Station Name Code Value (e.g. "CT-MAIN")
        "00404026.00080100"   Station Class Code      (e.g. "CTSCANNER")

    Restricted to UPS Integration Engineer.
    """
    frappe.only_for(["UPS Integration Engineer"])

    if not re.fullmatch(r"[0-9A-Fa-f]{8}(\.[0-9A-Fa-f]{8})?", str(matching_tag)):
        frappe.throw(
            _("Invalid DICOM tag: {0}. Expected 8 hex digits, e.g. 00741202").format(matching_tag),
            frappe.ValidationError,
        )

    if not matching_value or not str(matching_value).strip():
        frappe.throw(_("Matching value is required."), frappe.ValidationError)

    if not _HAS_UPS_CLIENT:
        frappe.throw(
            _("ups_worklist_portal app is not installed on this site."),
            frappe.ValidationError,
        )

    client = _DICOMwebClient()
    try:
        ws_url = client.subscribe_filtered({matching_tag: matching_value})
    except _UPSClientError as exc:
        frappe.throw(_("dcm4chee-arc error: {0}").format(str(exc)))

    doc = frappe.new_doc("UPS Filtered Subscription")
    doc.matching_tag = matching_tag
    doc.matching_tag_label = matching_tag_label or ""
    doc.matching_value = matching_value
    doc.ws_url = ws_url or ""
    doc.subscribed_at = now_datetime()
    doc.subscribed_by = frappe.session.user
    doc.status = "Active"
    doc.flags.ignore_permissions = True
    doc.insert()

    return doc.as_dict()


@frappe.whitelist()
def delete_all_filtered_subscriptions():
    """
    Remove all filtered subscriptions from dcm4chee-arc and mark local
    records as Removed.

    Per the DICOM UPS standard, DELETE on the Filtered Global SOP class
    (1.2.840.10008.5.1.4.34.5.1) removes *all* filtered subscriptions for
    the portal AE in a single operation — individual removal is not
    supported by the standard.  All locally-tracked Active records are
    therefore marked Removed together.

    Restricted to UPS Integration Engineer.
    """
    frappe.only_for(["UPS Integration Engineer"])

    if not _HAS_UPS_CLIENT:
        frappe.throw(
            _("ups_worklist_portal app is not installed on this site."),
            frappe.ValidationError,
        )

    client = _DICOMwebClient()
    try:
        client.unsubscribe_filtered()
    except _UPSClientError as exc:
        # 404 = no subscription existed on the SCP — treat as success
        if exc.http_status != 404:
            frappe.throw(_("dcm4chee-arc error: {0}").format(str(exc)))

    active_names = frappe.get_list(
        "UPS Filtered Subscription",
        filters={"status": "Active"},
        pluck="name",
    )
    for name in active_names:
        frappe.db.set_value("UPS Filtered Subscription", name, "status", "Removed")

    return {"removed": len(active_names)}
