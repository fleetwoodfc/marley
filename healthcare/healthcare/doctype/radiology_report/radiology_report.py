# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RadiologyReport(Document):
    """Controller for Radiology Report documents.

    Represents a radiologist's interpretation/report for an imaging study.
    TODO: Add PACS/DICOM integration when available.
    """

    def validate(self):
        self.set_status()
        self.set_title()

    def set_status(self):
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            if self.status not in ["Final", "Amended", "Cancelled"]:
                self.status = "Preliminary"
        elif self.docstatus == 2:
            self.status = "Cancelled"

    def set_title(self):
        self.title = _("{0} - {1}").format(
            self.patient_name or self.patient, self.study or "Radiology Report"
        )[:100]

    @frappe.whitelist()
    def finalize_report(self):
        """Finalize the radiology report."""
        self.db_set("status", "Final")
        return "success"
