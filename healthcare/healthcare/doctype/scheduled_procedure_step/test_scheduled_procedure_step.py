# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe import ValidationError

from healthcare.healthcare.doctype.scheduled_procedure_step.api import (
    get_worklist,
    claim_procedure,
    complete_procedure,
    cancel_procedure,
)


class TestScheduledProcedureStep(IntegrationTestCase):
    """Test cases for Scheduled Procedure Step DocType"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_test_data()
    
    @classmethod
    def _setup_test_data(cls):
        """Create test data for scheduled procedure step tests."""
        # Create test patient if not exists
        if not frappe.db.exists("Patient", {"patient_name": "Test SPS Patient"}):
            patient = frappe.get_doc({
                "doctype": "Patient",
                "first_name": "Test",
                "last_name": "SPS Patient",
                "sex": "Female",
                "dob": "1985-03-20"
            })
            patient.insert(ignore_permissions=True)
            cls.patient = patient.name
        else:
            cls.patient = frappe.db.get_value(
                "Patient",
                {"patient_name": "Test SPS Patient"},
                "name"
            )
        
        frappe.db.commit()
    
    def _create_test_sps(self, ups_state="SCHEDULED"):
        """Create a test Scheduled Procedure Step."""
        from healthcare.healthcare.dicom import generate_sop_instance_uid, generate_study_instance_uid
        
        sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "patient": self.patient,
            "modality": "CT",
            "scheduled_datetime": frappe.utils.now_datetime(),
            "ups_state": ups_state,
            "sop_instance_uid": generate_sop_instance_uid(),
            "study_instance_uid": generate_study_instance_uid(),
            "procedure_step_label": "Test CT Procedure"
        })
        sps.insert(ignore_permissions=True)
        return sps
    
    def test_claim_generates_transaction_uid(self):
        """Test that claiming a procedure generates a Transaction UID."""
        sps = self._create_test_sps()
        
        self.assertIsNone(sps.transaction_uid)
        
        transaction_uid = sps.claim()
        sps.reload()
        
        self.assertIsNotNone(transaction_uid)
        self.assertIsNotNone(sps.transaction_uid)
        self.assertEqual(transaction_uid, sps.transaction_uid)
        self.assertTrue(transaction_uid.startswith("2.25."))
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_claim_only_scheduled_state(self):
        """Test that only SCHEDULED procedures can be claimed."""
        sps = self._create_test_sps()
        
        # First claim should succeed
        sps.claim()
        sps.reload()
        
        self.assertEqual(sps.ups_state, "IN PROGRESS")
        
        # Second claim should fail
        with self.assertRaises(ValidationError):
            sps.claim()
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_claim_sets_in_progress_state(self):
        """Test that claiming transitions to IN PROGRESS state."""
        sps = self._create_test_sps()
        
        self.assertEqual(sps.ups_state, "SCHEDULED")
        
        sps.claim()
        sps.reload()
        
        self.assertEqual(sps.ups_state, "IN PROGRESS")
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_cannot_claim_already_claimed(self):
        """Test that an already claimed procedure cannot be claimed again."""
        sps = self._create_test_sps()
        
        # Claim the procedure
        sps.claim()
        sps.reload()
        
        # Try to claim again
        with self.assertRaises(ValidationError) as context:
            sps.claim()
        
        self.assertIn("IN PROGRESS", str(context.exception))
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_complete_requires_valid_transaction_uid(self):
        """Test that completion requires the correct Transaction UID."""
        sps = self._create_test_sps()
        
        # Claim to get transaction UID
        original_uid = sps.claim()
        sps.reload()
        
        # Try to complete with wrong UID
        with self.assertRaises(ValidationError):
            sps.complete("2.25.999999999999999")
        
        # Complete with correct UID should work
        sps.complete(original_uid)
        sps.reload()
        
        self.assertEqual(sps.ups_state, "COMPLETED")
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_complete_transitions_to_completed(self):
        """Test that complete() transitions to COMPLETED state."""
        sps = self._create_test_sps()
        
        transaction_uid = sps.claim()
        sps.reload()
        
        sps.complete(transaction_uid)
        sps.reload()
        
        self.assertEqual(sps.ups_state, "COMPLETED")
        self.assertIsNotNone(sps.procedure_end_datetime)
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_cancel_requires_reason(self):
        """Test that cancellation requires a reason."""
        sps = self._create_test_sps()
        
        # Cancel without reason should fail
        with self.assertRaises(ValidationError):
            sps.cancel_procedure(reason=None)
        
        with self.assertRaises(ValidationError):
            sps.cancel_procedure(reason="")
        
        # Cancel with reason should work
        sps.cancel_procedure(reason="Patient no-show")
        sps.reload()
        
        self.assertEqual(sps.ups_state, "CANCELED")
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
    
    def test_final_states_are_immutable(self):
        """Test that COMPLETED and CANCELED states cannot be changed."""
        # Test COMPLETED state
        sps1 = self._create_test_sps()
        uid1 = sps1.claim()
        sps1.reload()
        sps1.complete(uid1)
        sps1.reload()
        
        with self.assertRaises(ValidationError):
            sps1.claim()
        
        with self.assertRaises(ValidationError):
            sps1.cancel_procedure("Test reason")
        
        # Test CANCELED state
        sps2 = self._create_test_sps()
        sps2.cancel_procedure("Test cancellation")
        sps2.reload()
        
        with self.assertRaises(ValidationError):
            sps2.claim()
        
        with self.assertRaises(ValidationError):
            sps2.complete("any-uid")
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps1.name, force=True)
        frappe.delete_doc("Scheduled Procedure Step", sps2.name, force=True)
    
    def test_worklist_query_filters(self):
        """Test worklist query with various filters."""
        # Create test SPS records
        sps1 = self._create_test_sps()
        sps2 = self._create_test_sps()
        
        # Query by modality
        worklist = get_worklist(modality="CT")
        self.assertTrue(len(worklist) >= 2)
        
        # Query by state
        worklist = get_worklist(ups_state="SCHEDULED")
        self.assertTrue(all(w["ups_state"] == "SCHEDULED" for w in worklist))
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps1.name, force=True)
        frappe.delete_doc("Scheduled Procedure Step", sps2.name, force=True)
    
    def test_claim_api_endpoint(self):
        """Test the claim API endpoint."""
        sps = self._create_test_sps()
        
        result = claim_procedure(sps.name)
        
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["transaction_uid"])
        self.assertEqual(result["ups_state"], "IN PROGRESS")
        
        # Cleanup
        frappe.delete_doc("Scheduled Procedure Step", sps.name, force=True)
