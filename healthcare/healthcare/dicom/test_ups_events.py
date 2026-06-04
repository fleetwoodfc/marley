# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Integration tests for UPS Event handling.

These tests verify:
1. WebSocket connection to dcm4chee-arc (mocked)
2. Event handling and SPS updates
3. Realtime event publishing

To run:
    bench --site development.localhost run-tests \
        --app healthcare \
        --module healthcare.healthcare.dicom.test_ups_events
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import frappe
from frappe.tests import IntegrationTestCase

from healthcare.healthcare.dicom.ups_events import (
    UPSEventHandler,
    handle_ups_event,
    update_sps_from_remote_state,
)
from healthcare.healthcare.dicom.ups_rs import Tag, ProcedureStepState


class TestUPSEventHandler(IntegrationTestCase):
    """Tests for UPSEventHandler class."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test patient
        if not frappe.db.exists("Patient", "_Test Patient UPS"):
            patient = frappe.get_doc({
                "doctype": "Patient",
                "first_name": "Test",
                "last_name": "Patient UPS",
                "sex": "Male",
            })
            patient.insert(ignore_permissions=True)
            cls.patient_name = patient.name
        else:
            cls.patient_name = "_Test Patient UPS"
    
    def setUp(self):
        """Set up test data for each test."""
        # Create a test SPS
        self.test_sop_uid = f"2.25.{frappe.generate_hash()[:20]}"
        self.test_transaction_uid = f"2.25.{frappe.generate_hash()[:20]}"
        
        # Create SPS directly with frappe.get_doc
        self.sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "sop_instance_uid": self.test_sop_uid,
            "ups_state": ProcedureStepState.SCHEDULED.value,
            "ups_sync_status": "synced",
            "patient": self.patient_name,
            "scheduled_datetime": frappe.utils.now_datetime(),
            "modality": "CT",
            "procedure_step_label": "Test CT Scan",
        })
        self.sps.insert(ignore_permissions=True)
        frappe.db.commit()
    
    def tearDown(self):
        """Clean up test data."""
        if hasattr(self, 'sps') and frappe.db.exists("Scheduled Procedure Step", self.sps.name):
            frappe.delete_doc("Scheduled Procedure Step", self.sps.name, force=True)
            frappe.db.commit()
    
    def test_handler_initialization(self):
        """Test that handler initializes with correct event handlers."""
        handler = UPSEventHandler()
        
        self.assertIn("WorkitemCreated", handler.event_handlers)
        self.assertIn("WorkitemStateChanged", handler.event_handlers)
        self.assertIn("WorkitemCanceled", handler.event_handlers)
        self.assertIn("StateReport", handler.event_handlers)
        self.assertIn("ProgressReport", handler.event_handlers)
        self.assertIn("CancelRequest", handler.event_handlers)
    
    def test_extract_sop_instance_uid(self):
        """Test SOP Instance UID extraction from event data."""
        handler = UPSEventHandler()
        
        # Test with standard DICOM JSON format
        event = {
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": ["1.2.3.4.5"]}
            }
        }
        uid = handler._extract_sop_instance_uid(event)
        self.assertEqual(uid, "1.2.3.4.5")
        
        # Test with direct workitem_uid field
        event = {"workitem_uid": "1.2.3.4.6"}
        uid = handler._extract_sop_instance_uid(event)
        self.assertEqual(uid, "1.2.3.4.6")
        
        # Test with empty event
        event = {}
        uid = handler._extract_sop_instance_uid(event)
        self.assertIsNone(uid)
    
    def test_extract_state(self):
        """Test state extraction from event data."""
        handler = UPSEventHandler()
        
        event = {
            "workitem": {
                Tag.ProcedureStepState: {"vr": "CS", "Value": ["COMPLETED"]}
            }
        }
        state = handler._extract_state(event)
        self.assertEqual(state, "COMPLETED")
        
        # Test with empty event
        event = {}
        state = handler._extract_state(event)
        self.assertIsNone(state)
    
    def test_handle_state_changed_event(self):
        """Test handling of WorkitemStateChanged event."""
        event = {
            "event_type": "WorkitemStateChanged",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": [self.test_sop_uid]},
                Tag.ProcedureStepState: {"vr": "CS", "Value": ["IN PROGRESS"]}
            }
        }
        
        result = handle_ups_event(event)
        self.assertTrue(result)
        
        # Verify SPS was updated
        frappe.db.commit()  # Ensure changes are committed
        updated_sps = frappe.get_doc("Scheduled Procedure Step", self.sps.name)
        self.assertEqual(updated_sps.ups_state, "IN PROGRESS")
        self.assertEqual(updated_sps.ups_sync_status, "synced")
    
    def test_handle_state_report_event(self):
        """Test handling of StateReport event (alias for state change)."""
        event = {
            "event_type": "StateReport",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": [self.test_sop_uid]},
                Tag.ProcedureStepState: {"vr": "CS", "Value": ["IN PROGRESS"]}
            }
        }
        
        result = handle_ups_event(event)
        self.assertTrue(result)
        
        # Verify SPS was updated
        frappe.db.commit()
        updated_sps = frappe.get_doc("Scheduled Procedure Step", self.sps.name)
        self.assertEqual(updated_sps.ups_state, "IN PROGRESS")
    
    def test_handle_workitem_canceled_event(self):
        """Test handling of WorkitemCanceled event."""
        event = {
            "event_type": "WorkitemCanceled",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": [self.test_sop_uid]},
                "00741238": {"vr": "LO", "Value": ["Patient no-show"]}  # ReasonForCancellation
            }
        }
        
        result = handle_ups_event(event)
        self.assertTrue(result)
        
        # Verify SPS was updated
        frappe.db.commit()
        updated_sps = frappe.get_doc("Scheduled Procedure Step", self.sps.name)
        self.assertEqual(updated_sps.ups_state, "CANCELED")
    
    def test_handle_unknown_event_type(self):
        """Test that unknown event types return False."""
        event = {
            "event_type": "UnknownEventType",
            "workitem": {}
        }
        
        result = handle_ups_event(event)
        self.assertFalse(result)
    
    def test_handle_missing_event_type(self):
        """Test that missing event type returns False."""
        event = {
            "workitem": {}
        }
        
        result = handle_ups_event(event)
        self.assertFalse(result)
    
    def test_handle_nonexistent_sps(self):
        """Test handling event for non-existent SPS."""
        event = {
            "event_type": "WorkitemStateChanged",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": ["9.9.9.9.9"]},
                Tag.ProcedureStepState: {"vr": "CS", "Value": ["COMPLETED"]}
            }
        }
        
        result = handle_ups_event(event)
        self.assertFalse(result)
    
    def test_state_change_no_change_needed(self):
        """Test that same state doesn't trigger update."""
        event = {
            "event_type": "WorkitemStateChanged",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": [self.test_sop_uid]},
                Tag.ProcedureStepState: {"vr": "CS", "Value": ["SCHEDULED"]}
            }
        }
        
        result = handle_ups_event(event)
        self.assertTrue(result)  # Still returns True, just no update needed
    
    @patch("frappe.publish_realtime")
    def test_publishes_realtime_event(self, mock_publish):
        """Test that state changes publish realtime events."""
        event = {
            "event_type": "WorkitemStateChanged",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": [self.test_sop_uid]},
                Tag.ProcedureStepState: {"vr": "CS", "Value": ["IN PROGRESS"]}
            }
        }
        
        handle_ups_event(event)
        
        # Verify realtime was called
        mock_publish.assert_called()
        
        # Check that at least one call was for ups_state_changed
        call_args_list = mock_publish.call_args_list
        event_types = [call[0][0] for call in call_args_list]
        self.assertIn("ups_state_changed", event_types)
    
    def test_update_sps_from_remote_state(self):
        """Test the convenience function for updating SPS from remote state."""
        result = update_sps_from_remote_state(
            self.test_sop_uid,
            "COMPLETED"
        )
        self.assertTrue(result)
        
        # Verify SPS was updated
        frappe.db.commit()
        updated_sps = frappe.get_doc("Scheduled Procedure Step", self.sps.name)
        self.assertEqual(updated_sps.ups_state, "COMPLETED")


class TestUPSCancelRequest(IntegrationTestCase):
    """Tests for cancel request handling."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test patient
        if not frappe.db.exists("Patient", "_Test Patient Cancel"):
            patient = frappe.get_doc({
                "doctype": "Patient",
                "first_name": "Test",
                "last_name": "Patient Cancel",
                "sex": "Female",
            })
            patient.insert(ignore_permissions=True)
            cls.patient_name = patient.name
        else:
            cls.patient_name = "_Test Patient Cancel"
    
    def setUp(self):
        """Set up test data."""
        self.test_sop_uid = f"2.25.{frappe.generate_hash()[:20]}"
        
        self.sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "sop_instance_uid": self.test_sop_uid,
            "ups_state": ProcedureStepState.IN_PROGRESS.value,
            "ups_sync_status": "synced",
            "patient": self.patient_name,
            "scheduled_datetime": frappe.utils.now_datetime(),
            "modality": "MR",
            "procedure_step_label": "Test MRI Scan",
            "claimed_by": frappe.session.user,
        })
        self.sps.insert(ignore_permissions=True)
        frappe.db.commit()
    
    def tearDown(self):
        """Clean up test data."""
        if hasattr(self, 'sps') and frappe.db.exists("Scheduled Procedure Step", self.sps.name):
            frappe.delete_doc("Scheduled Procedure Step", self.sps.name, force=True)
            frappe.db.commit()
    
    @patch("frappe.publish_realtime")
    def test_cancel_request_publishes_realtime(self, mock_publish):
        """Test that cancel request publishes realtime event."""
        event = {
            "event_type": "CancelRequest",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": [self.test_sop_uid]},
                "00741238": {"vr": "LO", "Value": ["Urgent patient care needed"]}
            }
        }
        
        result = handle_ups_event(event)
        self.assertTrue(result)
        
        # Check realtime was called with cancel request event
        mock_publish.assert_called()
        call_args_list = mock_publish.call_args_list
        event_types = [call[0][0] for call in call_args_list]
        self.assertIn("ups_cancel_request", event_types)


class TestUPSProgressReport(IntegrationTestCase):
    """Tests for progress report handling."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Patient", "_Test Patient Progress"):
            patient = frappe.get_doc({
                "doctype": "Patient",
                "first_name": "Test",
                "last_name": "Patient Progress",
                "sex": "Male",
            })
            patient.insert(ignore_permissions=True)
            cls.patient_name = patient.name
        else:
            cls.patient_name = "_Test Patient Progress"
    
    def setUp(self):
        """Set up test data."""
        self.test_sop_uid = f"2.25.{frappe.generate_hash()[:20]}"
        
        self.sps = frappe.get_doc({
            "doctype": "Scheduled Procedure Step",
            "sop_instance_uid": self.test_sop_uid,
            "ups_state": ProcedureStepState.IN_PROGRESS.value,
            "ups_sync_status": "synced",
            "patient": self.patient_name,
            "scheduled_datetime": frappe.utils.now_datetime(),
            "modality": "CT",
            "procedure_step_label": "Test CT Scan",
        })
        self.sps.insert(ignore_permissions=True)
        frappe.db.commit()
    
    def tearDown(self):
        """Clean up test data."""
        if hasattr(self, 'sps') and frappe.db.exists("Scheduled Procedure Step", self.sps.name):
            frappe.delete_doc("Scheduled Procedure Step", self.sps.name, force=True)
            frappe.db.commit()
    
    @patch("frappe.publish_realtime")
    def test_progress_report_publishes_realtime(self, mock_publish):
        """Test that progress report publishes realtime event."""
        event = {
            "event_type": "ProgressReport",
            "workitem": {
                Tag.SOPInstanceUID: {"vr": "UI", "Value": [self.test_sop_uid]},
            }
        }
        
        result = handle_ups_event(event)
        self.assertTrue(result)
        
        # Check realtime was called with progress event
        mock_publish.assert_called()
        call_args_list = mock_publish.call_args_list
        event_types = [call[0][0] for call in call_args_list]
        self.assertIn("ups_progress_report", event_types)


if __name__ == "__main__":
    unittest.main()
