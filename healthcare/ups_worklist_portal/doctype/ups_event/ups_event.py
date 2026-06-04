"""
Controller for UPS Event DocType (append-only audit log).

UPS Event records are write-once: once inserted they must never be
modified or deleted.  This controller enforces that invariant.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class UPSEvent(Document):
    def before_insert(self):
        """Set event_timestamp to now if not supplied by the caller."""
        if not self.event_timestamp:
            self.event_timestamp = now_datetime()

    def before_save(self):
        """
        Raise ValidationError if an attempt is made to save an existing row,
        unless we are inside a bench migration (frappe.flags.in_migrate).
        """
        if not self.flags.in_insert and not frappe.flags.in_migrate:
            frappe.throw(
                _("UPS Event records are append-only and cannot be modified."),
                frappe.ValidationError,
                title=_("Immutable Audit Record"),
            )

    def before_cancel(self):
        """Prevent cancellation."""
        frappe.throw(
            _("UPS Event records cannot be cancelled."),
            frappe.ValidationError,
        )
