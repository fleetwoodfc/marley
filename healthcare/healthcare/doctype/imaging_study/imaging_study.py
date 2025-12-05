# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe import _
from frappe.model.document import Document


class ImagingStudy(Document):
    """Controller for Imaging Study documents.

    Represents a completed imaging study with DICOM data references.
    TODO: Add PACS/DICOM integration when available.
    """

    def validate(self):
        self.set_status()
        self.set_title()

    def set_status(self):
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            if self.status not in ["Available", "Archived"]:
                self.status = "Available"
        elif self.docstatus == 2:
            self.status = "Cancelled"

    def set_title(self):
        self.title = _("{0} - {1}").format(
            self.patient_name or self.patient, self.modality or "Imaging Study"
        )[:100]
