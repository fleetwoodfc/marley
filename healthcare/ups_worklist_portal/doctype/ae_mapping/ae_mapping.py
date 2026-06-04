"""
Controller for AE Mapping DocType.
"""

import frappe
from frappe.model.document import Document


class AEMapping(Document):
    def validate(self):
        """Uppercase and strip whitespace from the AE Title."""
        if self.ae_title:
            self.ae_title = self.ae_title.strip().upper()
        if self.display_name:
            self.display_name = self.display_name.strip()
