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
from healthcare.healthcare.dicom.ups_events import UPSEventHandler


class UpsEventWorker:
	"""
	Background worker that listens to UPS-RS WebSocket events
	and dispatches them to Frappe realtime.
	
	This worker:
	1. Establishes WebSocket connection to dcm4chee-arc
	2. Subscribes to UPS events (global or filtered)
	3. Routes events to UPSEventHandler for processing
	4. Publishes updates to Frappe realtime for connected browsers
	"""
	
	def __init__(self, client: UpsRSClient):
		self.client = client
		self.event_handler = UPSEventHandler()
		self._running = False
		self._subscription_aet = None
	
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
		
		# Publish raw event to Frappe realtime
		frappe.publish_realtime(
			"ups_event",
			{
				"event_type": event_type,
				"workitem_uid": workitem_uid,
				"data": data
			},
			after_commit=False
		)
		
		# Delegate to event handler for Scheduled Procedure Step updates
		event = {
			"event_type": event_type,
			"workitem_uid": workitem_uid,
			"workitem": data,
			"data": data
		}
		self.event_handler.handle_event(event)
	
	async def run(self, subscribe_global: bool = True, filter_criteria: dict = None):
		"""
		Start the event worker.
		
		Args:
			subscribe_global: Whether to subscribe to global worklist
			filter_criteria: Optional filter criteria for subscription (modality, station, etc.)
		"""
		self._running = True
		
		# Subscribe to worklist (global or filtered)
		if subscribe_global:
			result = self.client.subscribe_worklist()
			if result:
				self._subscription_aet = result.get("aet")
				frappe.logger().info(f"Subscribed to global worklist as {self._subscription_aet}")
		elif filter_criteria:
			# Filtered subscription based on criteria
			result = self.client.subscribe_filtered_worklist(filter_criteria)
			if result:
				self._subscription_aet = result.get("aet")
				frappe.logger().info(f"Subscribed to filtered worklist: {filter_criteria}")
		
		# Start WebSocket listener
		await self.client.subscribe_websocket(
			callback=self.on_event,
			reconnect=True,
			reconnect_delay=10
		)
	
	async def stop(self):
		"""Stop the event worker."""
		self._running = False
		
		# Unsubscribe from worklist
		if self._subscription_aet:
			try:
				self.client.unsubscribe_worklist()
				frappe.logger().info("Unsubscribed from worklist")
			except Exception as e:
				frappe.logger().warning(f"Error unsubscribing: {e}")
		
		await self.client.close_websocket()


def start_worker(settings_name: str = None, filter_criteria: dict = None):
	"""
	Start the UPS event worker.
	
	This should be called from a background job or bench command.
	
	Args:
		settings_name: Optional name of DICOM server settings
		filter_criteria: Optional filter criteria for subscription
	"""
	client = get_ups_client(settings_name)
	worker = UpsEventWorker(client)
	
	try:
		asyncio.run(worker.run(
			subscribe_global=(filter_criteria is None),
			filter_criteria=filter_criteria
		))
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
