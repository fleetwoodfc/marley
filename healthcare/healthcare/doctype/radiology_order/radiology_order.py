# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe import _
from frappe.model.document import Document


class RadiologyOrder(Document):
    """Controller for Radiology Order documents.

    Represents an order for diagnostic radiology services.
    TODO: Add PACS/DICOM integration when available.
    """

    def validate(self):
        self.set_status()
        self.set_title()

    def set_status(self):
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            if self.status not in ["In Progress", "Completed", "Cancelled"]:
                self.status = "Pending"
        elif self.docstatus == 2:
            self.status = "Cancelled"

    def set_title(self):
        self.title = _("{0} - {1}").format(
            self.patient_name or self.patient, self.procedure_template or "Radiology Order"
        )[:100]
