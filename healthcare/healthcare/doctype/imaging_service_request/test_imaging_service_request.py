# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from healthcare.healthcare.dicom import (
    generate_accession_number,
    generate_study_instance_uid,
    generate_sop_instance_uid,
)


class TestImagingServiceRequest(IntegrationTestCase):
    """Test cases for Imaging Service Request DocType"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_test_data()
    
    @classmethod
    def _setup_test_data(cls):
        """Create test data for imaging service request tests."""
        # Create test patient if not exists
        if not frappe.db.exists("Patient", {"patient_name": "Test ISR Patient"}):
            patient = frappe.get_doc({
                "doctype": "Patient",
                "first_name": "Test",
                "last_name": "ISR Patient",
                "sex": "Male",
                "dob": "1990-01-15"
            })
            patient.insert(ignore_permissions=True)
            cls.patient = patient.name
        else:
            cls.patient = frappe.db.get_value(
                "Patient",
                {"patient_name": "Test ISR Patient"},
                "name"
            )
        
        # Create test practitioner if not exists
        if not frappe.db.exists("Healthcare Practitioner", {"practitioner_name": "Test ISR Practitioner"}):
            practitioner = frappe.get_doc({
                "doctype": "Healthcare Practitioner",
                "first_name": "Test",
                "last_name": "ISR Practitioner"
            })
            practitioner.insert(ignore_permissions=True)
            cls.practitioner = practitioner.name
        else:
            cls.practitioner = frappe.db.get_value(
                "Healthcare Practitioner",
                {"practitioner_name": "Test ISR Practitioner"},
                "name"
            )
        
        # Create test procedure type if not exists
        if not frappe.db.exists("Procedure Type", "Test CT Chest"):
            procedure_type = frappe.get_doc({
                "doctype": "Procedure Type",
                "procedure_name": "Test CT Chest",
                "default_modality": "CT",
                "typical_duration": 30
            })
            procedure_type.insert(ignore_permissions=True)
            cls.procedure_type = procedure_type.name
        else:
            cls.procedure_type = "Test CT Chest"
        
        frappe.db.commit()
    
    def test_accession_number_generation(self):
        """Test that accession numbers are auto-generated on insert."""
        isr = frappe.get_doc({
            "doctype": "Imaging Service Request",
            "patient": self.patient,
            "requesting_practitioner": self.practitioner,
            "order_datetime": frappe.utils.now_datetime(),
            "priority": "ROUTINE",
            "requested_procedures": [{
                "procedure_type": self.procedure_type
            }]
        })
        isr.insert(ignore_permissions=True)
        
        self.assertIsNotNone(isr.accession_number)
        self.assertTrue(isr.accession_number.startswith("ACC-"))
        
        # Cleanup
        frappe.delete_doc("Imaging Service Request", isr.name, force=True)
    
    def test_study_instance_uid_generation(self):
        """Test that Study Instance UIDs are generated for requested procedures."""
        isr = frappe.get_doc({
            "doctype": "Imaging Service Request",
            "patient": self.patient,
            "requesting_practitioner": self.practitioner,
            "order_datetime": frappe.utils.now_datetime(),
            "priority": "ROUTINE",
            "requested_procedures": [{
                "procedure_type": self.procedure_type
            }]
        })
        isr.insert(ignore_permissions=True)
        
        self.assertEqual(len(isr.requested_procedures), 1)
        self.assertIsNotNone(isr.requested_procedures[0].study_instance_uid)
        self.assertTrue(isr.requested_procedures[0].study_instance_uid.startswith("2.25."))
        
        # Cleanup
        frappe.delete_doc("Imaging Service Request", isr.name, force=True)
    
    def test_validation_requires_requested_procedure(self):
        """Test that at least one requested procedure is required."""
        isr = frappe.get_doc({
            "doctype": "Imaging Service Request",
            "patient": self.patient,
            "requesting_practitioner": self.practitioner,
            "order_datetime": frappe.utils.now_datetime(),
            "priority": "ROUTINE",
            "requested_procedures": []  # Empty
        })
        
        with self.assertRaises(frappe.ValidationError):
            isr.insert(ignore_permissions=True)
    
    def test_creates_scheduled_procedure_step_on_submit(self):
        """Test that SPS is created when ISR is submitted."""
        isr = frappe.get_doc({
            "doctype": "Imaging Service Request",
            "patient": self.patient,
            "requesting_practitioner": self.practitioner,
            "order_datetime": frappe.utils.now_datetime(),
            "priority": "ROUTINE",
            "requested_procedures": [{
                "procedure_type": self.procedure_type
            }]
        })
        isr.insert(ignore_permissions=True)
        isr.submit()
        
        # Reload to get updated data
        isr.reload()
        
        # Check SPS was created
        self.assertIsNotNone(isr.requested_procedures[0].scheduled_procedure_step)
        
        # Verify SPS details
        sps = frappe.get_doc(
            "Scheduled Procedure Step",
            isr.requested_procedures[0].scheduled_procedure_step
        )
        self.assertEqual(sps.ups_state, "SCHEDULED")
        self.assertEqual(sps.patient, self.patient)
        self.assertEqual(sps.modality, "CT")
        self.assertIsNotNone(sps.sop_instance_uid)
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
        frappe.delete_doc("Imaging Service Request", isr.name, force=True)
    
    def test_status_updates_to_ordered_on_submit(self):
        """Test that status changes to Ordered on submit."""
        isr = frappe.get_doc({
            "doctype": "Imaging Service Request",
            "patient": self.patient,
            "requesting_practitioner": self.practitioner,
            "order_datetime": frappe.utils.now_datetime(),
            "priority": "ROUTINE",
            "requested_procedures": [{
                "procedure_type": self.procedure_type
            }]
        })
        isr.insert(ignore_permissions=True)
        
        self.assertEqual(isr.status, "Draft")
        
        isr.submit()
        isr.reload()
        
        self.assertEqual(isr.status, "Ordered")
        
        # Cleanup
        sps_name = isr.requested_procedures[0].scheduled_procedure_step
        frappe.delete_doc("Scheduled Procedure Step", sps_name, force=True)
        frappe.delete_doc("Imaging Service Request", isr.name, force=True)
