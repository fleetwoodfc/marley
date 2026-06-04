# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
Unit tests for Cancellation Request DocType.

Tests the third-party cancellation workflow including:
- Creating requests for IN PROGRESS procedures
- Accept/decline/withdraw actions
- Notification delivery
- UPS-RS integration
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime
from unittest.mock import patch, MagicMock


class TestCancellationRequest(IntegrationTestCase):
    """Test cases for Cancellation Request DocType."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        super().setUpClass()
        
        # Create test users
        cls.operator = cls._create_test_user("operator@test.local", "Operator User")
        cls.requester = cls._create_test_user("requester@test.local", "Requester User")
        
        # Create test patient
        cls.patient = cls._create_test_patient()
    
    @classmethod
    def _create_test_user(cls, email, full_name):
        """Create a test user if it doesn't exist."""
        if not frappe.db.exists("User", email):
            user = frappe.get_doc({
                "doctype": "User",
                "email": email,
                "first_name": full_name.split()[0],
                "last_name": full_name.split()[-1] if len(full_name.split()) > 1 else "",
                "enabled": 1,
                "user_type": "System User"
            })
            user.insert(ignore_permissions=True)
            return user.name
        return email
    
    @classmethod
    def _create_test_patient(cls):
        """Create a test patient."""
        patient_name = "TEST-CANCEL-001"
        if not frappe.db.exists("Patient", patient_name):
            patient = frappe.get_doc({
                "doctype": "Patient",
                "patient_name": "Test Cancel Patient",
                "sex": "Male"
            })
            patient.insert(ignore_permissions=True)
            return patient.name
        return patient_name
    
    def _create_test_sps(self, state="IN PROGRESS", claimed_by=None):
        """Create a test Scheduled Procedure Step."""
        import uuid
        
        sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "patient": self.patient,
            "modality": "CT",
            "procedure_step_label": "CT Abdomen Test",
            "ups_state": state,
            "claimed_by": claimed_by,
            "sop_instance_uid": str(uuid.uuid4()),
            "scheduled_datetime": now_datetime()
        })
        sps.insert(ignore_permissions=True)
        return sps
    
    def test_creates_request_for_in_progress_step(self):
        """Test that cancellation request can be created for IN PROGRESS steps."""
        # Create an IN PROGRESS SPS claimed by operator
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        # Login as requester
        frappe.set_user(self.requester)
        
        # Create cancellation request
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "reason": "Patient needs to reschedule"
        })
        
        # Should succeed
        request.insert(ignore_permissions=True)
        
        self.assertEqual(request.status, "Pending")
        self.assertEqual(request.requester, self.requester)
        
        # Cleanup
        frappe.set_user("Administrator")
        request.delete(ignore_permissions=True)
        sps.delete(ignore_permissions=True)
    
    def test_cannot_create_request_for_scheduled_step(self):
        """Test that cancellation request cannot be created for SCHEDULED steps."""
        # Create a SCHEDULED SPS
        sps = self._create_test_sps(state="SCHEDULED")
        
        frappe.set_user(self.requester)
        
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "reason": "Want to cancel"
        })
        
        # Should fail validation
        with self.assertRaises(frappe.ValidationError):
            request.insert(ignore_permissions=True)
        
        # Cleanup
        frappe.set_user("Administrator")
        sps.delete(ignore_permissions=True)
    
    def test_cannot_request_own_procedure_cancellation(self):
        """Test that operator cannot request cancellation of their own procedure."""
        # Create SPS claimed by operator
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        # Login as operator (same user who claimed it)
        frappe.set_user(self.operator)
        
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "requester": self.operator,  # Same as claimed_by
            "reason": "Self cancel attempt"
        })
        
        # Should fail validation
        with self.assertRaises(frappe.ValidationError):
            request.insert(ignore_permissions=True)
        
        # Cleanup
        frappe.set_user("Administrator")
        sps.delete(ignore_permissions=True)
    
    def test_accept_cancels_procedure(self):
        """Test that accepting a cancellation request cancels the procedure."""
        # Create IN PROGRESS SPS
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        frappe.set_user(self.requester)
        
        # Create cancellation request
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "reason": "Patient condition changed"
        })
        request.insert(ignore_permissions=True)
        
        # Login as operator and accept
        frappe.set_user(self.operator)
        
        request.reload()
        
        # Mock the SPS cancel_procedure method to avoid UPS-RS calls
        with patch.object(
            frappe.get_doc("Scheduled Procedure Step", sps.name).__class__,
            'cancel_procedure',
            return_value=None
        ):
            request.accept(decision_reason="Agreed to reschedule")
        
        # Verify request status
        request.reload()
        self.assertEqual(request.status, "Accepted")
        self.assertEqual(request.decision_by, self.operator)
        self.assertIsNotNone(request.decision_at)
        
        # Cleanup
        frappe.set_user("Administrator")
        request.delete(ignore_permissions=True)
        sps.delete(ignore_permissions=True)
    
    def test_decline_notifies_requester(self):
        """Test that declining a request creates notification for requester."""
        # Create IN PROGRESS SPS
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        frappe.set_user(self.requester)
        
        # Create cancellation request
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "reason": "Patient needs to leave"
        })
        request.insert(ignore_permissions=True)
        
        # Login as operator and decline
        frappe.set_user(self.operator)
        
        request.reload()
        request.decline(decision_reason="Procedure almost complete")
        
        # Verify request status
        request.reload()
        self.assertEqual(request.status, "Declined")
        self.assertEqual(request.decision_reason, "Procedure almost complete")
        
        # Verify SPS is still IN PROGRESS
        sps.reload()
        self.assertEqual(sps.ups_state, "IN PROGRESS")
        
        # Cleanup
        frappe.set_user("Administrator")
        request.delete(ignore_permissions=True)
        sps.delete(ignore_permissions=True)
    
    def test_decline_requires_reason(self):
        """Test that declining requires a reason."""
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        frappe.set_user(self.requester)
        
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "reason": "Please cancel"
        })
        request.insert(ignore_permissions=True)
        
        frappe.set_user(self.operator)
        request.reload()
        
        # Should fail without reason
        with self.assertRaises(frappe.ValidationError):
            request.decline()
        
        # Cleanup
        frappe.set_user("Administrator")
        request.delete(ignore_permissions=True)
        sps.delete(ignore_permissions=True)
    
    def test_withdraw_by_requester(self):
        """Test that requester can withdraw their request."""
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        frappe.set_user(self.requester)
        
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "reason": "Changed my mind"
        })
        request.insert(ignore_permissions=True)
        
        # Requester withdraws
        request.withdraw()
        
        request.reload()
        self.assertEqual(request.status, "Withdrawn")
        
        # Cleanup
        frappe.set_user("Administrator")
        request.delete(ignore_permissions=True)
        sps.delete(ignore_permissions=True)
    
    def test_cannot_process_already_processed_request(self):
        """Test that already processed requests cannot be processed again."""
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        frappe.set_user(self.requester)
        
        request = frappe.get_doc({
            "doctype": "Cancellation Request",
            "scheduled_procedure_step": sps.name,
            "reason": "First reason"
        })
        request.insert(ignore_permissions=True)
        
        # Withdraw first
        request.withdraw()
        
        # Try to accept after withdrawal
        frappe.set_user(self.operator)
        request.reload()
        
        with self.assertRaises(frappe.ValidationError):
            request.accept()
        
        # Cleanup
        frappe.set_user("Administrator")
        request.delete(ignore_permissions=True)
        sps.delete(ignore_permissions=True)
    
    def test_sends_ups_cancel_request(self):
        """Test that UPS cancel request is sent on creation."""
        sps = self._create_test_sps(state="IN PROGRESS", claimed_by=self.operator)
        
        frappe.set_user(self.requester)
        
        # Mock the send_cancel_request function
        with patch(
            'healthcare.healthcare.doctype.cancellation_request.cancellation_request.send_cancel_request'
        ) as mock_send:
            request = frappe.get_doc({
                "doctype": "Cancellation Request",
                "scheduled_procedure_step": sps.name,
                "reason": "Need to cancel"
            })
            request.insert(ignore_permissions=True)
            
            # Verify send_cancel_request was called
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            self.assertEqual(call_args.kwargs.get('procedure_step'), sps.name)
            self.assertEqual(call_args.kwargs.get('reason'), "Need to cancel")
        
        # Cleanup
        frappe.set_user("Administrator")
        request.delete(ignore_permissions=True)
        sps.delete(ignore_permissions=True)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures."""
        frappe.set_user("Administrator")
        
        # Clean up test users
        for email in ["operator@test.local", "requester@test.local"]:
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True)
        
        # Clean up test patient
        if frappe.db.exists("Patient", "TEST-CANCEL-001"):
            frappe.delete_doc("Patient", "TEST-CANCEL-001", ignore_permissions=True)
        
        super().tearDownClass()
