"""
Controller for UPS Integration Settings (Single DocType).
"""

import frappe
from frappe.model.document import Document


class UPSIntegrationSettings(Document):
    def validate(self):
        """Raise ValidationError if sync is enabled but no URL is provided."""
        if self.enable_ups_sync and not self.ups_rs_url:
            frappe.throw(
                "UPS-RS Base URL is required when Enable UPS Sync is turned on.",
                frappe.ValidationError,
                title="UPS Integration Settings",
            )
        if self.ups_rs_url:
            # Strip trailing slash to ensure consistent URL construction
            self.ups_rs_url = self.ups_rs_url.rstrip("/")
