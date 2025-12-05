# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ImagingProcedureTemplate(Document):
    """Template for Imaging Procedures (diagnostic radiology).

    Follows Clinical Procedure Template patterns for consistency.
    """

    def validate(self):
        self.set_title()

    def set_title(self):
        if not self.template_name:
            frappe.throw(_("Template Name is required"))
