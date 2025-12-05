# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Migration patch to backfill Imaging Procedure records from Clinical Procedure.

This patch iterates through Clinical Procedure records that reference an
Imaging Procedure Template and creates corresponding Imaging Procedure documents.

The migration is idempotent - it skips Clinical Procedures that have already
been migrated (based on the clinical_procedure_source field in Imaging Procedure).
"""

import frappe
from frappe import _


def execute():
    """Execute the backfill migration.

    Iterates through Clinical Procedure records and creates Imaging Procedure
    documents for those that reference an Imaging Procedure Template.

    Uses insert(ignore_permissions=True) for creating new records to ensure
    the migration can run regardless of user permissions.
    """
    # Check if the Imaging Procedure doctype exists
    if not frappe.db.table_exists("Imaging Procedure"):
        frappe.log_error(
            message="Imaging Procedure table does not exist. Skipping migration.",
            title=_("Diagnostic Radiology Backfill Skipped"),
        )
        return

    if not frappe.db.table_exists("Imaging Procedure Template"):
        frappe.log_error(
            message="Imaging Procedure Template table does not exist. Skipping migration.",
            title=_("Diagnostic Radiology Backfill Skipped"),
        )
        return

    # Get all Imaging Procedure Template names to check against
    imaging_templates = frappe.get_all("Imaging Procedure Template", pluck="name")
    if not imaging_templates:
        # No imaging templates exist, nothing to migrate
        return

    imaging_template_set = set(imaging_templates)

    # Get all Clinical Procedures that have a procedure_template
    clinical_procedures = frappe.get_all(
        "Clinical Procedure",
        filters={"procedure_template": ("is", "set")},
        fields=[
            "name",
            "patient",
            "patient_name",
            "patient_age",
            "patient_sex",
            "procedure_template",
            "practitioner",
            "medical_department",
            "start_date",
            "start_time",
            "notes",
            "service_unit",
            "company",
            "status",
            "docstatus",
            "service_request",
            "appointment",
        ],
    )

    migrated_count = 0
    skipped_count = 0
    error_count = 0

    for cp in clinical_procedures:
        try:
            # Check if the procedure_template is an Imaging Procedure Template
            if cp.procedure_template not in imaging_template_set:
                skipped_count += 1
                continue

            # Check if already migrated (Imaging Procedure with same source exists)
            existing = frappe.db.exists(
                "Imaging Procedure",
                {"clinical_procedure_source": cp.name},
            )
            if existing:
                skipped_count += 1
                continue

            # Create new Imaging Procedure
            imaging_procedure = frappe.get_doc(
                {
                    "doctype": "Imaging Procedure",
                    "patient": cp.patient,
                    "patient_name": cp.patient_name,
                    "patient_age": cp.patient_age,
                    "patient_sex": cp.patient_sex,
                    "procedure_template": cp.procedure_template,
                    "practitioner": cp.practitioner,
                    "medical_department": cp.medical_department,
                    "start_date": cp.start_date,
                    "start_time": cp.start_time,
                    "notes": cp.notes,
                    "service_unit": cp.service_unit,
                    "company": cp.company,
                    "status": cp.status,
                    "service_request": cp.service_request,
                    "appointment": cp.appointment,
                    "clinical_procedure_source": cp.name,  # Track migration source
                }
            )

            imaging_procedure.insert(ignore_permissions=True)

            # If the original was submitted, submit the new one too
            if cp.docstatus == 1:
                imaging_procedure.submit()

            migrated_count += 1

        except Exception as e:
            error_count += 1
            frappe.log_error(
                message=f"Error migrating Clinical Procedure {cp.name}: {str(e)}",
                title=_("Diagnostic Radiology Backfill Error"),
            )
            continue

    if migrated_count > 0 or error_count > 0:
        frappe.log_error(
            message=f"Migration completed: {migrated_count} migrated, {skipped_count} skipped, {error_count} errors",
            title=_("Diagnostic Radiology Backfill Complete"),
        )
