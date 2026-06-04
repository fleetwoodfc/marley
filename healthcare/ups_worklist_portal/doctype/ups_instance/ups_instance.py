"""
Controller for UPS Instance DocType.

Enforces state machine transitions and provides the append_event()
helper used by all API actions.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# ---------------------------------------------------------------------------
# Valid state transitions  (from_state -> set of allowed to_states)
# ---------------------------------------------------------------------------
_VALID_STATES = {"SCHEDULED", "IN PROGRESS", "COMPLETED", "CANCELED"}

_VALID_TRANSITIONS = {
    "SCHEDULED": {"IN PROGRESS", "CANCELED"},
    "IN PROGRESS": {"COMPLETED", "CANCELED"},
    "COMPLETED": set(),   # terminal — no transitions allowed
    "CANCELED": {"SCHEDULED"},   # proprietary reschedule only
}


class UPSInstance(Document):
    def validate(self):
        self._enforce_state_machine()

    def before_save(self):
        # Clear lock fields when entering a terminal state
        if self.ups_state in ("COMPLETED", "CANCELED"):
            self.transaction_uid = None

    # -----------------------------------------------------------------------
    # State machine enforcement
    # -----------------------------------------------------------------------

    def _enforce_state_machine(self):
        """
        Raise frappe.ValidationError if the requested state transition is invalid.

        New documents (inserts from dcm4chee sync) may start in any valid UPS
        state — state machine rules only apply to transitions on existing docs.
        Skip validation when flags.sync_import is set (scheduler-initiated upsert).
        """
        # Allow any valid state on brand-new inserts (dcm4chee sync import)
        if self.is_new() or self.flags.get("sync_import"):
            if self.ups_state not in _VALID_STATES:
                frappe.throw(
                    _("Invalid UPS state: {0}").format(self.ups_state),
                    frappe.ValidationError,
                )
            return

        old_state = frappe.db.get_value("UPS Instance", self.name, "ups_state")
        new_state = self.ups_state
        allowed = _VALID_TRANSITIONS.get(old_state, set())

        if new_state not in allowed and new_state != old_state:
            frappe.throw(
                _("Invalid UPS state transition: {0} → {1}. Allowed: {2}").format(
                    old_state or "None",
                    new_state,
                    ", ".join(sorted(allowed)) or "none",
                ),
                frappe.ValidationError,
                title=_("UPS State Machine Violation"),
            )

        # DICOM UPS §C.23.3 — "The SCU shall generate a Transaction UID and
        # include it in the state-change request."  Enforce this at the
        # DocType level so no code path can bypass the requirement.
        if old_state == "SCHEDULED" and new_state == "IN PROGRESS":
            if not self.transaction_uid:
                frappe.throw(
                    _(
                        "A Transaction UID is required to claim a SCHEDULED workitem "
                        "(DICOM UPS §C.23.3). Use the Claim action to initiate this transition."
                    ),
                    frappe.ValidationError,
                    title=_("Transaction UID Required"),
                )

    # -----------------------------------------------------------------------
    # Audit helper
    # -----------------------------------------------------------------------

    def append_event(
        self,
        event_type,
        old_state=None,
        new_state=None,
        details=None,
        http_status=None,
        raw_request=None,
        raw_response=None,
        actor=None,
        actor_aet=None,
        transaction_uid=None,
    ):
        """
        Insert a new UPS Event audit row for this workitem.

        This is the *only* way audit rows should be created; never
        call frappe.new_doc("UPS Event") directly from API code.

        Returns the inserted UPS Event document.
        """
        event = frappe.new_doc("UPS Event")
        event.ups_instance = self.name
        event.event_type = event_type
        event.actor = actor or frappe.session.user
        event.actor_aet = actor_aet or frappe.get_single("UPS Integration Settings").dicom_aet
        event.event_timestamp = now_datetime()
        event.old_state = old_state
        event.new_state = new_state
        event.transaction_uid = transaction_uid or self.transaction_uid
        event.details = details
        event.http_status = http_status
        event.raw_request = raw_request
        event.raw_response = raw_response
        event.flags.ignore_permissions = True
        event.insert()
        return event
