# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe import ValidationError
from frappe.utils import now_datetime, add_to_date


class TestPerformedProcedureStep(IntegrationTestCase):
    """Test cases for Performed Procedure Step DocType"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_test_data()
    
    @classmethod
    def _setup_test_data(cls):
        """Create test data for performed procedure step tests."""
        # Create test patient if not exists
        if not frappe.db.exists("Patient", {"patient_name": "Test PPS Patient"}):
            patient = frappe.get_doc({
                "doctype": "Patient",
                "first_name": "Test",
                "last_name": "PPS Patient",
                "sex": "Male",
                "dob": "1975-07-10"
            })
            patient.insert(ignore_permissions=True)
            cls.patient = patient.name
        else:
            cls.patient = frappe.db.get_value(
                "Patient",
                {"patient_name": "Test PPS Patient"},
                "name"
            )
        
        frappe.db.commit()
    
    def _create_test_sps(self, ups_state="IN PROGRESS"):
        """Create a test Scheduled Procedure Step."""
        from healthcare.healthcare.dicom import generate_sop_instance_uid, generate_study_instance_uid, generate_transaction_uid
        
        sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "patient": self.patient,
            "modality": "CT",
            "scheduled_datetime": now_datetime(),
            "ups_state": ups_state,
            "sop_instance_uid": generate_sop_instance_uid(),
            "study_instance_uid": generate_study_instance_uid(),
            "procedure_step_label": "Test CT Procedure for PPS"
        })
        
        # Set transaction UID if in progress
        if ups_state == "IN PROGRESS":
            sps.transaction_uid = generate_transaction_uid()
            sps.claimed_by = frappe.session.user
            sps.claimed_at = now_datetime()
        
        sps.insert(ignore_permissions=True)
        return sps
    
    def test_creates_from_scheduled_step(self):
        """Test that PPS can be created from a scheduled step."""
        sps = self._create_test_sps()
        
        pps = frappe.get_doc({
            "doctype": "Performed Procedure Step",
            "scheduled_procedure_step": sps.name,
            "patient": self.patient,
            "start_datetime": now_datetime(),
            "performing_operator": frappe.session.user,
            "status": "In Progress"
        })
        pps.insert(ignore_permissions=True)
        
        self.assertIsNotNone(pps.name)
        self.assertEqual(pps.scheduled_procedure_step, sps.name)
        self.assertEqual(pps.patient, self.patient)
        
        # Cleanup
        frappe.delete_doc("Performed Procedure Step", pps.name, force=True)
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_copies_protocol_codes_from_sps(self):
        """Test that protocol codes are copied from scheduled step."""
        sps = self._create_test_sps()
        
        # Add protocol codes to SPS
        sps.append("protocol_codes", {
            "code_value": "71260",
            "coding_scheme_designator": "CPT",
            "code_meaning": "CT Thorax w/contrast"
        })
        sps.save()
        
        pps = frappe.get_doc({
            "doctype": "Performed Procedure Step",
            "scheduled_procedure_step": sps.name,
            "start_datetime": now_datetime(),
            "performing_operator": frappe.session.user,
            "status": "In Progress"
        })
        pps.insert(ignore_permissions=True)
        
        # Should have copied the protocol codes
        self.assertEqual(len(pps.performed_protocol_codes), 1)
        self.assertEqual(pps.performed_protocol_codes[0].code_value, "71260")
        
        # Cleanup
        frappe.delete_doc("Performed Procedure Step", pps.name, force=True)
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_completion_updates_scheduled_step(self):
        """Test that completing PPS updates the scheduled step."""
        sps = self._create_test_sps()
        
        pps = frappe.get_doc({
            "doctype": "Performed Procedure Step",
            "scheduled_procedure_step": sps.name,
            "patient": self.patient,
            "start_datetime": now_datetime(),
            "performing_operator": frappe.session.user,
            "status": "In Progress"
        })
        pps.insert(ignore_permissions=True)
        
        # Complete the performed step
        pps.status = "Completed"
        pps.end_datetime = now_datetime()
        pps.save()
        
        # Check that SPS is also completed
        sps.reload()
        self.assertEqual(sps.ups_state, "COMPLETED")
        
        # Cleanup
        frappe.delete_doc("Performed Procedure Step", pps.name, force=True)
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_discontinuation_requires_reason(self):
        """Test that discontinuation requires a reason."""
        sps = self._create_test_sps()
        
        pps = frappe.get_doc({
            "doctype": "Performed Procedure Step",
            "scheduled_procedure_step": sps.name,
            "patient": self.patient,
            "start_datetime": now_datetime(),
            "performing_operator": frappe.session.user,
            "status": "Discontinued"
            # No reason provided
        })
        
        with self.assertRaises(ValidationError):
            pps.insert(ignore_permissions=True)
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_discontinuation_with_reason(self):
        """Test that discontinuation works with a reason."""
        sps = self._create_test_sps()
        
        pps = frappe.get_doc({
            "doctype": "Performed Procedure Step",
            "scheduled_procedure_step": sps.name,
            "patient": self.patient,
            "start_datetime": now_datetime(),
            "performing_operator": frappe.session.user,
            "status": "Discontinued",
            "discontinuation_reason": "Patient became claustrophobic"
        })
        pps.insert(ignore_permissions=True)
        
        self.assertEqual(pps.status, "Discontinued")
        self.assertIsNotNone(pps.discontinuation_reason)
        
        # Cleanup
        frappe.delete_doc("Performed Procedure Step", pps.name, force=True)
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_timing_validation(self):
        """Test that end time cannot be before start time."""
        sps = self._create_test_sps()
        
        start = now_datetime()
        end = add_to_date(start, hours=-1)  # 1 hour before start
        
        pps = frappe.get_doc({
            "doctype": "Performed Procedure Step",
            "scheduled_procedure_step": sps.name,
            "patient": self.patient,
            "start_datetime": start,
            "end_datetime": end,  # Invalid - before start
            "performing_operator": frappe.session.user,
            "status": "Completed"
        })
        
        with self.assertRaises(ValidationError):
            pps.insert(ignore_permissions=True)
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_output_information_tracking(self):
        """Test that output information can be tracked."""
        sps = self._create_test_sps()
        
        pps = frappe.get_doc({
            "doctype": "Performed Procedure Step",
            "scheduled_procedure_step": sps.name,
            "patient": self.patient,
            "start_datetime": now_datetime(),
            "performing_operator": frappe.session.user,
            "status": "In Progress"
        })
        pps.insert(ignore_permissions=True)
        
        # Add output information
        pps.append("output_information", {
            "reference_type": "Series",
            "sop_class_uid": "1.2.840.10008.5.1.4.1.1.2",
            "sop_instance_uid": "2.25.123456789",
            "description": "CT Chest Series 1"
        })
        pps.save()
        
        self.assertEqual(len(pps.output_information), 1)
        self.assertEqual(pps.get_output_series_count(), 1)
        
        # Cleanup
        frappe.delete_doc("Performed Procedure Step", pps.name, force=True)
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
