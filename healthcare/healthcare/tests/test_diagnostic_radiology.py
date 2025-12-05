import unittest

import frappe
from frappe.utils import nowdate, nowtime

from healthcare.healthcare.doctype.imaging_procedure.imaging_procedure import (
	make_imaging_procedure,
)
from healthcare.healthcare.patches.diagnostic_radiology_backfill import execute as run_backfill


class TestDiagnosticRadiology(unittest.TestCase):
    """Basic unit test skeleton for diagnostic radiology.

    These tests are lightweight and intended as a starting point. They create
    minimal fixture docs if needed and assert high-level flows:
    - mapping a Patient Appointment to an Imaging Procedure
    - running the migration patch to backfill from Clinical Procedure -> Imaging Procedure

    Note: tests use insert(ignore_permissions=True) for fixtures and try to clean up
    after themselves where feasible.
    """

    def setUp(self):
        # Ensure a Patient exists
        patients = frappe.get_all("Patient", limit=1)
        if patients:
            self.patient = patients[0].name
        else:
            p = frappe.get_doc({"doctype": "Patient", "patient_name": "Test Patient"}).insert(
                ignore_permissions=True
            )
            self.patient = p.name

        # Ensure an Imaging Procedure Template exists for mapping tests
        if not frappe.db.exists("Imaging Procedure Template", "Test Imaging Template"):
            tpl = frappe.get_doc(
                {"doctype": "Imaging Procedure Template", "template_name": "Test Imaging Template"}
            ).insert(ignore_permissions=True)
            self.template = tpl.name
        else:
            self.template = "Test Imaging Template"

    def tearDown(self):
        # Cleanup docs created by tests when possible. Use try/except to avoid failing teardown.
        try:
            for name in frappe.get_all(
                "Imaging Procedure", filters={"procedure_template": self.template}, fields=["name"]
            ):
                frappe.delete_doc("Imaging Procedure", name.name, force=True)
        except Exception:
            pass
        try:
            # Remove the test template if it was created
            if frappe.db.exists("Imaging Procedure Template", "Test Imaging Template"):
                frappe.delete_doc(
                    "Imaging Procedure Template", "Test Imaging Template", force=True
                )
        except Exception:
            pass

    def test_make_imaging_procedure_from_appointment(self):
        # Create a Patient Appointment and map it to an Imaging Procedure
        appt = frappe.get_doc(
            {
                "doctype": "Patient Appointment",
                "patient": self.patient,
                "start_date": nowdate(),
                "start_time": nowtime(),
                "procedure_template": self.template,
            }
        ).insert(ignore_permissions=True)

        # Call the mapping function (same pattern as Clinical Procedure mapping)
        doc = make_imaging_procedure(appt.name)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.doctype, "Imaging Procedure")
        self.assertEqual(doc.procedure_template, self.template)

        # Cleanup appointment
        try:
            frappe.delete_doc("Patient Appointment", appt.name, force=True)
        except Exception:
            pass

    def test_backfill_migration_creates_imaging_procedure(self):
        # Create a Clinical Procedure that references the imaging template
        cp = frappe.get_doc(
            {
                "doctype": "Clinical Procedure",
                "patient": self.patient,
                "procedure_template": self.template,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True)

        # Run the backfill migration (should create an Imaging Procedure)
        run_backfill()

        # Assert an Imaging Procedure exists that references this patient and template
        ips = frappe.get_all(
            "Imaging Procedure",
            filters={"patient": self.patient, "procedure_template": self.template},
            limit=1,
        )
        self.assertTrue(len(ips) >= 1)

        # Cleanup clinical procedure
        try:
            frappe.delete_doc("Clinical Procedure", cp.name, force=True)
        except Exception:
            pass
