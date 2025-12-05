# -*- coding: utf-8 -*-
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Utility functions for Diagnostic Radiology module.

This module contains helper functions for diagnostic radiology operations
including PACS/DICOM integration (TODO) and imaging workflow utilities.
"""

import frappe
from frappe import _


def get_imaging_modalities():
    """Get list of available imaging modalities.

    Returns:
            List of imaging modality names
    """
    try:
        return frappe.get_all("Imaging Modality", pluck="name")
    except Exception:
        return []


def get_pending_imaging_procedures(patient=None):
    """Get pending imaging procedures, optionally filtered by patient.

    Args:
            patient: Optional patient name to filter by

    Returns:
            List of pending imaging procedure records
    """
    filters = {"status": "Pending", "docstatus": 1}
    if patient:
        filters["patient"] = patient

    try:
        return frappe.get_all(
            "Imaging Procedure",
            filters=filters,
            fields=["name", "patient", "procedure_template", "start_date", "practitioner"],
        )
    except Exception:
        return []


def create_imaging_study_from_procedure(imaging_procedure_name):
    """Create an Imaging Study document from an Imaging Procedure.

    Args:
            imaging_procedure_name: Name of the Imaging Procedure

    Returns:
            Created Imaging Study document or None on error

    TODO: Add PACS/DICOM integration to populate study details.
    """
    try:
        procedure = frappe.get_doc("Imaging Procedure", imaging_procedure_name)
        study = frappe.get_doc(
            {
                "doctype": "Imaging Study",
                "patient": procedure.patient,
                "imaging_procedure": procedure.name,
                "status": "Draft",
            }
        )
        study.insert(ignore_permissions=True)
        return study
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title=_("Error creating Imaging Study from Procedure"),
        )
        return None


def validate_imaging_template_exists(template_name):
    """Validate that an Imaging Procedure Template exists.

    Args:
            template_name: Template name to check

    Returns:
            True if exists, False otherwise
    """
    if not template_name:
        return False
    return frappe.db.exists("Imaging Procedure Template", template_name)
