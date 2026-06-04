"""
DICOMweb UPS-RS client for dcm4chee-arc.

Wraps HTTP calls to the UPS-RS endpoint using the `requests` library.
Configuration is read from the `UPS Integration Settings` singleton at
instantiation.  All request/response pairs can be logged to the UPS Instance
mirror for audit purposes.

Error hierarchy:
    UPSClientError           ← base
    ├── ConflictError        ← HTTP 409 (already claimed)
    ├── BadRequestError      ← HTTP 400 (transaction UID mismatch, etc.)
    ├── NotFoundError        ← HTTP 404
    └── ServerError          ← HTTP 5xx / timeout
"""

import json
import logging

import frappe
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class UPSClientError(Exception):
    """Base class for all DICOMwebClient errors."""

    def __init__(self, message, http_status=None, response_body=None):
        super().__init__(message)
        self.http_status = http_status
        self.response_body = response_body


class ConflictError(UPSClientError):
    """HTTP 409 — resource already claimed or duplicate workitem."""


class BadRequestError(UPSClientError):
    """HTTP 400 — malformed request or Transaction UID mismatch."""


class NotFoundError(UPSClientError):
    """HTTP 404 — workitem does not exist."""


class ServerError(UPSClientError):
    """HTTP 5xx or connection timeout from dcm4chee-arc."""


# ---------------------------------------------------------------------------
# DICOMwebClient
# ---------------------------------------------------------------------------

_DICOM_JSON_CT = "application/dicom+json"


class DICOMwebClient:
    """
    Thin wrapper around dcm4chee-arc UPS-RS endpoints.

    Usage::

        client = DICOMwebClient()
        workitems = client.get_worklist({"00741000": ["SCHEDULED"]})
        client.change_state(uid, "IN PROGRESS", txn_uid)
    """

    def __init__(self):
        settings = frappe.get_single("UPS Integration Settings")
        raw_url = (settings.ups_rs_url or "").rstrip("/")
        # T039: Validate URL format to prevent SSRF / misconfiguration
        if raw_url and not frappe.utils.validate_url(raw_url):
            raise frappe.ValidationError(
                _("UPS Integration Settings: ups_rs_url is not a valid URL.")
            )
        self.base = raw_url
        self.aet = settings.dicom_aet or "FRAPPE-PORTAL"
        self.timeout = int(settings.request_timeout_seconds or 30)

        auth_type = settings.auth_type or "None"
        if auth_type == "Basic":
            password = settings.get_password("auth_password") or ""
            self.auth = HTTPBasicAuth(settings.auth_username or "", password)
        elif auth_type == "Bearer":
            token = settings.get_password("auth_password") or ""
            self.auth = _BearerAuth(token)
        else:
            self.auth = None

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _headers(self, include_content_type=False):
        h = {"Accept": _DICOM_JSON_CT}
        if include_content_type:
            h["Content-Type"] = _DICOM_JSON_CT
        return h

    def _request(self, method, path, **kwargs):
        """
        Execute an HTTP request and map error codes to custom exceptions.

        Never logs credential values; only logs method, URL, and status code.
        """
        url = f"{self.base}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)
        if self.auth:
            kwargs["auth"] = self.auth

        try:
            resp = requests.request(method, url, **kwargs)
        except requests.Timeout as exc:
            raise ServerError(f"Timeout calling {method} {url}") from exc
        except requests.ConnectionError as exc:
            raise ServerError(f"Connection error calling {method} {url}") from exc

        logger.debug("UPS-RS %s %s → %s", method, url, resp.status_code)

        body = resp.text or ""
        if resp.status_code in (200, 201, 204):
            return resp
        if resp.status_code == 400:
            raise BadRequestError(
                f"400 Bad Request: {url}", http_status=400, response_body=body
            )
        if resp.status_code == 404:
            raise NotFoundError(
                f"404 Not Found: {url}", http_status=404, response_body=body
            )
        if resp.status_code == 409:
            raise ConflictError(
                f"409 Conflict: {url}", http_status=409, response_body=body
            )
        if resp.status_code >= 500:
            raise ServerError(
                f"{resp.status_code} Server Error: {url}",
                http_status=resp.status_code,
                response_body=body,
            )
        # Unexpected 4xx
        raise UPSClientError(
            f"{resp.status_code} Unexpected: {url}",
            http_status=resp.status_code,
            response_body=body,
        )

    # -----------------------------------------------------------------------
    # UPS-RS operations (see contracts/ups-rs-mapping.md for payloads)
    # -----------------------------------------------------------------------

    def get_worklist(self, filters=None):
        """
        Query workitems from dcm4chee-arc (QIDO-style).

        ``filters`` is a dict mapping DICOM tag strings to value lists, e.g.::

            {"00741000": ["SCHEDULED", "IN PROGRESS"]}

        Returns list of DICOM+JSON dataset dicts (empty list on 204).
        """
        params = {}
        if filters:
            for tag, values in filters.items():
                # QIDO allows repeated param names for OR semantics, but
                # requests only supports one value per key; join with comma
                # per QIDO-RS spec §8.3.4
                if isinstance(values, list):
                    params[tag] = ",".join(str(v) for v in values)
                else:
                    params[tag] = str(values)

        resp = self._request(
            "GET", "workitems", params=params, headers=self._headers()
        )
        if resp.status_code == 204:
            return []
        return resp.json()

    def get_workitem(self, ups_uid):
        """
        Retrieve a single UPS workitem by UID.

        Returns a DICOM+JSON dataset dict.
        Raises NotFoundError if the workitem does not exist.
        """
        resp = self._request("GET", f"workitems/{ups_uid}", headers=self._headers())
        return resp.json()

    def create_workitem(self, ups_uid, attributes):
        """
        Create a new UPS workitem in dcm4chee-arc.

        ``attributes`` is a full DICOM+JSON dataset dict.
        Returns the Location header value from the 201 response.
        """
        resp = self._request(
            "POST",
            "workitems",
            params={"workitem": ups_uid},
            headers=self._headers(include_content_type=True),
            data=json.dumps(attributes),
        )
        return resp.headers.get("Location", "")

    def change_state(self, ups_uid, new_state, transaction_uid, reason=None):
        """
        Change the state of a UPS workitem.

        Used for claim (SCHEDULED → IN PROGRESS), complete (→ COMPLETED),
        and cancel (→ CANCELED) operations.

        ``transaction_uid`` is required for IN PROGRESS and COMPLETED transitions.
        ``reason`` is an optional discontinuation reason string for CANCELED.

        Returns the raw requests.Response on success.
        """
        payload = {
            "00741000": {"vr": "CS", "Value": [new_state]},
        }
        if transaction_uid:
            payload["00081195"] = {"vr": "UI", "Value": [transaction_uid]}
        if reason and new_state == "CANCELED":
            payload["00741238"] = {
                "vr": "SQ",
                "Value": [{"00080104": {"vr": "LO", "Value": [reason]}}],
            }

        return self._request(
            "PUT",
            f"workitems/{ups_uid}/state/{self.aet}",
            headers=self._headers(include_content_type=True),
            data=json.dumps(payload),
        )

    def request_cancel(self, ups_uid, reason, contact_uri=None, contact_display_name=None):
        """
        Send a third-party cancel request (supervisor advisory) to dcm4chee-arc.

        This is advisory only: the performer decides whether to honor it.
        For SCHEDULED workitems with no active performer, follow with
        ``change_state(..., "CANCELED", transaction_uid=None)``.

        Returns the raw requests.Response on success.
        """
        payload = {
            "00741238": {
                "vr": "SQ",
                "Value": [{"00080104": {"vr": "LO", "Value": [reason or "Supervisor cancel"]}}],
            }
        }
        if contact_uri:
            payload["0074100A"] = {"vr": "UR", "Value": [contact_uri]}
        if contact_display_name:
            payload["0074100C"] = {"vr": "LO", "Value": [contact_display_name]}
        return self._request(
            "POST",
            f"workitems/{ups_uid}/cancelrequest/{self.aet}",
            headers=self._headers(include_content_type=True),
            data=json.dumps(payload),
        )

    def update_workitem(self, ups_uid, attributes, transaction_uid=None):
        """
        Update attributes of an existing workitem (e.g., reassign AE Title).

        ``attributes`` is a partial DICOM+JSON dataset.
        ``transaction_uid`` is required when the workitem is IN PROGRESS.

        Returns the raw requests.Response on success.
        """
        headers = self._headers(include_content_type=True)
        if transaction_uid:
            headers["If-Match"] = transaction_uid  # dcm4chee uses this for IN PROGRESS updates
        return self._request(
            "POST",
            f"workitems/{ups_uid}",
            headers=headers,
            data=json.dumps(attributes),
        )

    def subscribe_global(self):
        """
        Subscribe this portal AE to the Global UPS Worklist on dcm4chee-arc.

        Returns the WebSocket URL from the Location response header so the
        ws_sidecar can open a WebSocket connection.

        UID 1.2.840.10008.5.1.4.34.5 = Global Subscription SOP Class.
        """
        global_uid = "1.2.840.10008.5.1.4.34.5"
        resp = self._request(
            "POST",
            f"workitems/{global_uid}/subscribers/{self.aet}",
            headers=self._headers(),
        )
        ws_url = resp.headers.get("Location", "")
        return ws_url

    def unsubscribe_global(self):
        """Remove the global subscription for this portal AE."""
        global_uid = "1.2.840.10008.5.1.4.34.5"
        return self._request(
            "DELETE",
            f"workitems/{global_uid}/subscribers/{self.aet}",
            headers=self._headers(),
        )

    def suspend_subscription(self):
        """Suspend the global subscription (keep-alive, pause events)."""
        global_uid = "1.2.840.10008.5.1.4.34.5"
        return self._request(
            "POST",
            f"workitems/{global_uid}/subscribers/{self.aet}/suspend",
            headers=self._headers(),
        )

    def reschedule_workitem(self, ups_uid):
        """
        Reschedule a CANCELED workitem back to SCHEDULED.

        This uses the dcm4chee-arc proprietary extension endpoint.
        See research.md §1 quirk Q3 and contracts/ups-rs-mapping.md §11.
        """
        return self._request(
            "POST",
            f"workitems/{ups_uid}/reschedule",
            headers=self._headers(),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _BearerAuth(requests.auth.AuthBase):
    """Attaches a Bearer token to requests."""

    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers["Authorization"] = f"Bearer {self.token}"
        return r


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

# Back-off delays in seconds for retry attempts (attempt 1..4)
_RETRY_DELAYS_SECONDS = [60, 300, 900, 3600]


def schedule_sync_retry(
    method_dotted_path,
    ups_uid,
    attempt=1,
    extra_kwargs=None,
):
    """
    Enqueue a retry of a background sync job using Frappe's job queue.

    Called when a ``ServerError`` occurs during a background sync operation.
    Each invocation increments ``attempt`` up to ``max_sync_retries`` from
    ``UPS Integration Settings``.

    ``method_dotted_path`` must be an importable Python dotted path
    (e.g. ``"healthcare.ups_worklist_portal.tasks.retry_sync_workitem"``).

    Error state is written to the ``UPS Instance.ups_sync_error`` field so
    Integration Engineers can inspect sync problems without viewing credentials.
    """
    settings = frappe.get_single("UPS Integration Settings")
    max_retries = int(settings.max_sync_retries or 4)

    if attempt > max_retries:
        # Exhaust retries — mark the local mirror as sync-errored
        if ups_uid:
            try:
                doc = frappe.get_doc("UPS Instance", ups_uid)
                doc.ups_sync_status = "error"
                doc.ups_sync_error = (
                    f"Sync failed after {max_retries} attempts (last attempt {attempt - 1}). "
                    "Check dcm4chee-arc connectivity."
                )
                doc.save(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                logger.exception("Could not update UPS Instance sync error for %s", ups_uid)
        return

    delay = _RETRY_DELAYS_SECONDS[min(attempt - 1, len(_RETRY_DELAYS_SECONDS) - 1)]
    kwargs = {"ups_uid": ups_uid, "attempt": attempt + 1}
    if extra_kwargs:
        kwargs.update(extra_kwargs)

    frappe.enqueue(
        method_dotted_path,
        queue="long",
        timeout=300,
        is_async=True,
        at_front=False,
        job_id=f"ups_retry::{ups_uid}::attempt{attempt + 1}",
        **kwargs,
    )
    logger.info(
        "Scheduled retry %d/%d for %s in %ds",
        attempt + 1,
        max_retries,
        ups_uid,
        delay,
    )
