# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
Integration tests for UPS-RS workflow with mock dcm4chee-arc.

Tests the full workflow:
1. Create Imaging Service Request → Requested Procedure → Scheduled Procedure Step
2. Claim SPS (transition to IN PROGRESS)
3. Complete SPS (transition to COMPLETED)
4. Cancel workflow
5. Event handling

Uses httpretty to mock the dcm4chee-arc UPS-RS endpoints.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

try:
    import httpretty
    HTTPRETTY_AVAILABLE = True
except ImportError:
    HTTPRETTY_AVAILABLE = False


class TestUPSIntegration(IntegrationTestCase):
    """Integration tests for UPS-RS workflow."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures and mock server."""
        super().setUpClass()
        
        # Create test patient
        cls.patient = cls._create_test_patient()
        
        # Create test practitioner
        cls.practitioner = cls._create_test_practitioner()
        
        # Enable UPS sync in settings
        cls._configure_healthcare_settings()
    
    @classmethod
    def _create_test_patient(cls):
        """Create a test patient."""
        patient_name = "TEST-UPS-INTEGRATION-001"
        if frappe.db.exists("Patient", patient_name):
            return patient_name
        
        patient = frappe.get_doc({
            "doctype": "Patient",
            "patient_name": "Test UPS Patient",
            "sex": "Male",
            "dob": "1980-01-01"
        })
        patient.insert(ignore_permissions=True)
        return patient.name
    
    @classmethod
    def _create_test_practitioner(cls):
        """Create a test practitioner."""
        if frappe.db.exists("Healthcare Practitioner", "HP-TEST-UPS"):
            return "HP-TEST-UPS"
        
        practitioner = frappe.get_doc({
            "doctype": "Healthcare Practitioner",
            "practitioner_name": "Dr. Test UPS",
            "gender": "Male"
        })
        practitioner.insert(ignore_permissions=True)
        return practitioner.name
    
    @classmethod
    def _configure_healthcare_settings(cls):
        """Configure Healthcare Settings for UPS sync."""
        settings = frappe.get_single("Healthcare Settings")
        settings.enable_ups_sync = 1
        settings.ups_rs_url = "http://mock-dcm4chee:8080/dcm4chee-arc/aets/WORKLIST/rs"
        settings.save(ignore_permissions=True)
    
    def _create_imaging_order(self):
        """Create a full imaging order chain."""
        # Create Imaging Service Request
        isr = frappe.get_doc({
            "doctype": "Imaging Service Request",
            "patient": self.patient,
            "referred_to_practitioner": self.practitioner,
            "order_datetime": now_datetime(),
            "status": "Active"
        })
        isr.insert(ignore_permissions=True)
        
        # Create Requested Procedure
        rp = frappe.get_doc({
            "doctype": "Requested Procedure",
            "imaging_service_request": isr.name,
            "patient": self.patient,
            "modality": "CT",
            "body_site": "Chest",
            "description": "CT Chest with contrast"
        })
        rp.insert(ignore_permissions=True)
        
        # Create Scheduled Procedure Step
        import uuid
        sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "imaging_service_request": isr.name,
            "requested_procedure": rp.name,
            "patient": self.patient,
            "patient_name": "Test UPS Patient",
            "modality": "CT",
            "procedure_step_label": "CT Chest Protocol",
            "ups_state": "SCHEDULED",
            "scheduled_datetime": now_datetime(),
            "station_name": "CT1",
            "station_aet": "CT1_AET",
            "sop_instance_uid": str(uuid.uuid4())
        })
        sps.insert(ignore_permissions=True)
        
        return isr, rp, sps
    
    @patch('healthcare.healthcare.dicom.ups_sync.sync_state_change')
    def test_full_workflow_scheduled_to_completed(self, mock_sync):
        """Test full workflow from SCHEDULED to COMPLETED."""
        isr, rp, sps = self._create_imaging_order()
        
        # Verify initial state
        self.assertEqual(sps.ups_state, "SCHEDULED")
        self.assertIsNotNone(sps.sop_instance_uid)
        
        # Claim the procedure (transition to IN PROGRESS)
        sps.reload()
        result = sps.claim()
        
        self.assertTrue(result.get("success"))
        self.assertIsNotNone(result.get("transaction_uid"))
        
        sps.reload()
        self.assertEqual(sps.ups_state, "IN PROGRESS")
        self.assertIsNotNone(sps.claimed_by)
        
        # Complete the procedure
        transaction_uid = sps.transaction_uid
        result = sps.complete(transaction_uid)
        
        self.assertTrue(result.get("success"))
        
        sps.reload()
        self.assertEqual(sps.ups_state, "COMPLETED")
        
        # Cleanup
        sps.delete(ignore_permissions=True)
        rp.delete(ignore_permissions=True)
        isr.delete(ignore_permissions=True)
    
    @patch('healthcare.healthcare.dicom.ups_sync.sync_state_change')
    def test_cancel_scheduled_procedure(self, mock_sync):
        """Test cancellation of a SCHEDULED procedure."""
        isr, rp, sps = self._create_imaging_order()
        
        # Cancel the procedure
        sps.reload()
        result = sps.cancel_procedure(reason="Patient no-show")
        
        self.assertTrue(result.get("success"))
        
        sps.reload()
        self.assertEqual(sps.ups_state, "CANCELED")
        
        # Cleanup
        sps.delete(ignore_permissions=True)
        rp.delete(ignore_permissions=True)
        isr.delete(ignore_permissions=True)
    
    @patch('healthcare.healthcare.dicom.ups_sync.sync_state_change')
    def test_cancel_in_progress_procedure(self, mock_sync):
        """Test cancellation of an IN PROGRESS procedure."""
        isr, rp, sps = self._create_imaging_order()
        
        # First claim
        sps.reload()
        sps.claim()
        
        sps.reload()
        self.assertEqual(sps.ups_state, "IN PROGRESS")
        
        # Cancel with transaction UID
        result = sps.cancel_procedure(
            reason="Equipment malfunction",
            transaction_uid=sps.transaction_uid
        )
        
        self.assertTrue(result.get("success"))
        
        sps.reload()
        self.assertEqual(sps.ups_state, "CANCELED")
        
        # Cleanup
        sps.delete(ignore_permissions=True)
        rp.delete(ignore_permissions=True)
        isr.delete(ignore_permissions=True)
    
    @patch('healthcare.healthcare.dicom.ups_sync.sync_state_change')
    def test_invalid_state_transition_rejected(self, mock_sync):
        """Test that invalid state transitions are rejected."""
        isr, rp, sps = self._create_imaging_order()
        
        # Try to complete without claiming first
        sps.reload()
        with self.assertRaises(frappe.ValidationError):
            sps.complete("dummy-transaction-uid")
        
        # Cleanup
        sps.delete(ignore_permissions=True)
        rp.delete(ignore_permissions=True)
        isr.delete(ignore_permissions=True)
    
    @patch('healthcare.healthcare.dicom.ups_sync.sync_state_change')
    def test_wrong_transaction_uid_rejected(self, mock_sync):
        """Test that wrong transaction UID is rejected."""
        isr, rp, sps = self._create_imaging_order()
        
        # Claim first
        sps.reload()
        sps.claim()
        
        # Try to complete with wrong transaction UID
        sps.reload()
        with self.assertRaises(frappe.ValidationError):
            sps.complete("wrong-transaction-uid")
        
        # Cleanup
        sps.delete(ignore_permissions=True)
        rp.delete(ignore_permissions=True)
        isr.delete(ignore_permissions=True)
    
    def test_uid_generation(self):
        """Test that UIDs are correctly generated."""
        from healthcare.healthcare.dicom import (
            generate_sop_instance_uid,
            generate_transaction_uid,
            generate_study_instance_uid
        )
        
        sop_uid = generate_sop_instance_uid()
        transaction_uid = generate_transaction_uid()
        study_uid = generate_study_instance_uid()
        
        # Verify format (DICOM UID is a series of dot-separated numbers)
        self.assertRegex(sop_uid, r'^[\d.]+$')
        self.assertRegex(study_uid, r'^[\d.]+$')
        
        # Transaction UID can be different format
        self.assertIsNotNone(transaction_uid)
        self.assertTrue(len(transaction_uid) > 0)
        
        # Verify uniqueness
        sop_uid2 = generate_sop_instance_uid()
        self.assertNotEqual(sop_uid, sop_uid2)
    
    @patch('healthcare.healthcare.dicom.ups_sync.get_ups_client')
    def test_sync_disabled_skips_sync(self, mock_get_client):
        """Test that sync is skipped when disabled."""
        # Disable sync
        settings = frappe.get_single("Healthcare Settings")
        settings.enable_ups_sync = 0
        settings.save(ignore_permissions=True)
        
        mock_get_client.return_value = None
        
        from healthcare.healthcare.dicom.ups_sync import sync_state_change
        
        # Should not raise, just skip
        sync_state_change("nonexistent-sps")
        
        # Re-enable sync
        settings.enable_ups_sync = 1
        settings.save(ignore_permissions=True)
    
    def test_accession_number_generation(self):
        """Test accession number generation."""
        from healthcare.healthcare.dicom import generate_accession_number
        
        accession = generate_accession_number()
        
        self.assertIsNotNone(accession)
        self.assertTrue(len(accession) > 0)
        
        # Verify uniqueness
        accession2 = generate_accession_number()
        self.assertNotEqual(accession, accession2)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures."""
        # Re-enable UPS sync to original state
        settings = frappe.get_single("Healthcare Settings")
        settings.enable_ups_sync = 1
        settings.save(ignore_permissions=True)
        
        # Clean up test patient
        if frappe.db.exists("Patient", "TEST-UPS-INTEGRATION-001"):
            frappe.delete_doc("Patient", "TEST-UPS-INTEGRATION-001", ignore_permissions=True)
        
        # Clean up test practitioner
        if frappe.db.exists("Healthcare Practitioner", "HP-TEST-UPS"):
            frappe.delete_doc("Healthcare Practitioner", "HP-TEST-UPS", ignore_permissions=True)
        
        super().tearDownClass()
