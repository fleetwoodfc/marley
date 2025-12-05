# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import get_link_to_form

from healthcare.healthcare.doctype.service_request.service_request import (
	set_service_request_status,
)


class ImagingProcedure(Document):
    """Controller for Imaging Procedure documents (diagnostic radiology).

    Follows the same patterns as Clinical Procedure for consistency.
    """

    def validate(self):
        self.set_status()
        self.set_title()

    def before_insert(self):
        if self.service_request:
            has_procedure = frappe.db.exists(
                "Imaging Procedure",
                {"service_request": self.service_request, "docstatus": 0},
            )
            if has_procedure:
                frappe.throw(
                    _("Imaging Procedure {0} already created from service request {1}").format(
                        frappe.bold(get_link_to_form("Imaging Procedure", has_procedure)),
                        frappe.bold(get_link_to_form("Service Request", self.service_request)),
                    ),
                    title=_("Already Exists"),
                )

    def on_cancel(self):
        if self.service_request:
            set_service_request_status(self.service_request, "active-Request Status")

    def after_insert(self):
        if self.appointment:
            frappe.db.set_value("Patient Appointment", self.appointment, "status", "Closed")
        self.reload()

    def on_submit(self):
        if self.service_request:
            status = "active-Request Status"
            if self.status == "Completed":
                status = "completed-Request Status"
            set_service_request_status(self.service_request, status)

    def set_status(self):
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            if self.status not in ["In Progress", "Completed"]:
                self.status = "Pending"
        elif self.docstatus == 2:
            self.status = "Cancelled"

    def set_title(self):
        self.title = _("{0} - {1}").format(
            self.patient_name or self.patient, self.procedure_template
        )[:100]

    @frappe.whitelist()
    def complete_procedure(self):
        """Mark the procedure as completed."""
        self.db_set("status", "Completed")
        if self.service_request:
            set_service_request_status(self.service_request, "completed-Request Status")

    @frappe.whitelist()
    def start_procedure(self):
        """Start the imaging procedure."""
        self.db_set("status", "In Progress")
        return "success"


@frappe.whitelist()
def make_imaging_procedure(source_name, target_doc=None):
    """Create an Imaging Procedure from a Patient Appointment.

    Args:
            source_name: Patient Appointment name
            target_doc: Optional target document

    Returns:
            Imaging Procedure document (unsaved)
    """

    def set_missing_values(source, target):
        # TODO: Add PACS/DICOM integration when available
        pass

    doc = get_mapped_doc(
        "Patient Appointment",
        source_name,
        {
            "Patient Appointment": {
                "doctype": "Imaging Procedure",
                "field_map": [
                    ["appointment", "name"],
                    ["patient", "patient"],
                    ["patient_age", "patient_age"],
                    ["patient_sex", "patient_sex"],
                    ["procedure_template", "procedure_template"],
                    ["practitioner", "practitioner"],
                    ["medical_department", "department"],
                    ["start_date", "appointment_date"],
                    ["start_time", "appointment_time"],
                    ["notes", "notes"],
                    ["service_unit", "service_unit"],
                    ["company", "company"],
                    ["invoiced", "invoiced"],
                ],
            }
        },
        target_doc,
        set_missing_values,
    )

    return doc


@frappe.whitelist()
def get_imaging_procedure_prescribed(patient, encounter=False):
    """Get prescribed imaging procedures for a patient.

    Args:
            patient: Patient name
            encounter: Optional encounter filter

    Returns:
            List of service requests for imaging procedures
    """
    hso = frappe.qb.DocType("Service Request")
    return (
        frappe.qb.from_(hso)
        .select(
            hso.template_dn,
            hso.order_group,
            hso.billing_status,
            hso.practitioner,
            hso.order_date,
            hso.name,
            hso.insurance_policy,
            hso.insurance_payor,
        )
        .where(hso.patient == patient)
        .where(hso.status != "completed-Request Status")
        .where(hso.template_dt == "Imaging Procedure Template")
        .orderby(hso.creation, order=frappe.qb.desc)
    ).run()
