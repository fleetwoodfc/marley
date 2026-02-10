# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
UPS-RS Event Worker for Frappe

This module provides a background worker for receiving UPS-RS WebSocket events
and dispatching them to Frappe's realtime system.

Usage:
	# Start the worker via bench command
	bench execute healthcare.healthcare.dicom.ups_worker.start_worker
	
	# Or via Frappe scheduler
	frappe.enqueue(
		"healthcare.healthcare.dicom.ups_worker.start_worker",
		queue="long",
		is_async=True
	)
"""

import asyncio
import frappe
from frappe.utils.background_jobs import enqueue

from healthcare.healthcare.dicom.ups_rs import (
	UpsRSClient,
	get_ups_client,
	ProcedureStepState,
	Tag,
	UpsEvent,
)


class UpsEventWorker:
	"""
	Background worker that listens to UPS-RS WebSocket events
	and dispatches them to Frappe realtime.
	"""
	
	def __init__(self, client: UpsRSClient):
		self.client = client
		self._running = False
	
	async def on_event(self, event_type: str, data: dict):
		"""
		Handle incoming UPS event.
		
		Args:
			event_type: Type of event (StateReport, ProgressReport, etc.)
			data: Event data in DICOM JSON format
		"""
		frappe.logger().info(f"UPS Event: {event_type}")
		
		# Extract workitem UID
		workitem_uid = None
		if Tag.SOPInstanceUID in data and "Value" in data[Tag.SOPInstanceUID]:
			workitem_uid = data[Tag.SOPInstanceUID]["Value"][0]
		
		# Publish to Frappe realtime
		frappe.publish_realtime(
			"ups_event",
			{
				"event_type": event_type,
				"workitem_uid": workitem_uid,
				"data": data
			},
			after_commit=False
		)
		
		# Handle specific event types
		if event_type == UpsEvent.STATE_REPORT.value:
			await self._handle_state_change(workitem_uid, data)
		elif event_type == UpsEvent.CANCEL_REQUEST.value:
			await self._handle_cancel_request(workitem_uid, data)
	
	async def _handle_state_change(self, workitem_uid: str, data: dict):
		"""Handle workitem state change event."""
		if Tag.ProcedureStepState not in data:
			return
		
		new_state = data[Tag.ProcedureStepState].get("Value", [None])[0]
		if not new_state:
			return
		
		frappe.logger().info(f"UPS Workitem {workitem_uid} state changed to {new_state}")
		
		# Look up linked Radiology Procedure and update status
		try:
			procedures = frappe.get_all(
				"Radiology Procedure",
				filters={"ups_workitem_uid": workitem_uid},
				pluck="name"
			)
			
			for proc_name in procedures:
				frappe.db.set_value(
					"Radiology Procedure",
					proc_name,
					"ups_state",
					new_state
				)
				
				# Map UPS state to procedure status
				status_map = {
					"SCHEDULED": "Scheduled",
					"IN PROGRESS": "In Progress",
					"COMPLETED": "Completed",
					"CANCELED": "Cancelled",
				}
				
				if new_state in status_map:
					frappe.db.set_value(
						"Radiology Procedure",
						proc_name,
						"status",
						status_map[new_state]
					)
				
				frappe.db.commit()
				
				# Publish update to connected clients
				frappe.publish_realtime(
					"radiology_procedure_updated",
					{"name": proc_name, "ups_state": new_state},
					doctype="Radiology Procedure",
					docname=proc_name
				)
		except Exception as e:
			frappe.log_error(f"Error updating Radiology Procedure from UPS event: {e}")
	
	async def _handle_cancel_request(self, workitem_uid: str, data: dict):
		"""Handle cancellation request event."""
		reason = None
		if Tag.ReasonForCancellation in data and "Value" in data[Tag.ReasonForCancellation]:
			reason = data[Tag.ReasonForCancellation]["Value"][0]
		
		frappe.logger().info(f"UPS Cancellation requested for {workitem_uid}: {reason}")
		
		# Create a notification for the cancellation request
		try:
			procedures = frappe.get_all(
				"Radiology Procedure",
				filters={"ups_workitem_uid": workitem_uid},
				fields=["name", "patient", "practitioner"]
			)
			
			for proc in procedures:
				# Create notification
				frappe.get_doc({
					"doctype": "Notification Log",
					"subject": f"Cancellation requested for Radiology Procedure {proc.name}",
					"email_content": f"Reason: {reason or 'Not specified'}",
					"for_user": proc.practitioner if proc.practitioner else frappe.session.user,
					"document_type": "Radiology Procedure",
					"document_name": proc.name,
					"type": "Alert",
				}).insert(ignore_permissions=True)
				
				frappe.publish_realtime(
					"ups_cancel_request",
					{
						"procedure": proc.name,
						"patient": proc.patient,
						"reason": reason
					}
				)
		except Exception as e:
			frappe.log_error(f"Error handling UPS cancellation request: {e}")
	
	async def run(self, subscribe_global: bool = True):
		"""
		Start the event worker.
		
		Args:
			subscribe_global: Whether to subscribe to global worklist
		"""
		self._running = True
		
		# Subscribe to worklist
		if subscribe_global:
			self.client.subscribe_worklist()
		
		# Start WebSocket listener
		await self.client.subscribe_websocket(
			callback=self.on_event,
			reconnect=True,
			reconnect_delay=10
		)
	
	async def stop(self):
		"""Stop the event worker."""
		self._running = False
		await self.client.close_websocket()


def start_worker(settings_name: str = None):
	"""
	Start the UPS event worker.
	
	This should be called from a background job or bench command.
	
	Args:
		settings_name: Optional name of DICOM server settings
	"""
	client = get_ups_client(settings_name)
	worker = UpsEventWorker(client)
	
	try:
		asyncio.run(worker.run())
	except KeyboardInterrupt:
		frappe.logger().info("UPS Event Worker stopped by user")
	except Exception as e:
		frappe.log_error(f"UPS Event Worker error: {e}")
		raise
	finally:
		client.close()


@frappe.whitelist()
def enqueue_worker(settings_name: str = None):
	"""
	Enqueue the UPS event worker as a background job.
	
	Args:
		settings_name: Optional name of DICOM server settings
	"""
	enqueue(
		"healthcare.healthcare.dicom.ups_worker.start_worker",
		queue="long",
		timeout=86400,  # 24 hours
		is_async=True,
		settings_name=settings_name
	)
	
	return {"status": "Worker enqueued"}


# ============================================================
# Bench Commands
# ============================================================

def setup_hooks():
	"""Add scheduler entry for UPS worker."""
	# This would be added to hooks.py
	return {
		"scheduler_events": {
			"cron": {
				"0 */1 * * *": [  # Every hour
					"healthcare.healthcare.dicom.ups_worker.check_worker_health"
				]
			}
		}
	}


def check_worker_health():
	"""
	Check if the UPS worker is running and restart if needed.
	
	This can be called from the scheduler to ensure the worker stays alive.
	"""
	# Check if worker job exists in queue
	from frappe.utils.background_jobs import get_jobs
	
	jobs = get_jobs(site=frappe.local.site, queue="long")
	worker_running = any(
		"ups_worker.start_worker" in str(job.get("job_name", ""))
		for job in jobs
	)
	
	if not worker_running:
		# Check if UPS is configured
		hs = frappe.get_single("Healthcare Settings")
		if hs.get("ups_rs_url") and hs.get("enable_ups_worker"):
			frappe.logger().info("Restarting UPS Event Worker")
			enqueue_worker()
