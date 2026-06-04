// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

/**
 * DICOM UPS-RS Client for Frappe Frontend
 * 
 * Provides JavaScript helpers for interacting with UPS workitems
 * and receiving real-time UPS events via Frappe's Socket.IO.
 * 
 * Usage:
 *   // Create a workitem
 *   healthcare.dicom.ups.createWorkitem({
 *     procedure_step_label: "CT Chest",
 *     patient_id: "PAT001"
 *   }).then(uid => console.log("Created:", uid));
 * 
 *   // Subscribe to UPS events
 *   healthcare.dicom.ups.on("state_change", (data) => {
 *     console.log("Workitem state changed:", data);
 *   });
 *   
 *   // Auto-refresh worklist on state changes
 *   healthcare.dicom.ups.enableWorklistAutoRefresh(true);
 */

frappe.provide("healthcare.dicom.ups");

$.extend(healthcare.dicom.ups, {
	/**
	 * Event callback registry
	 */
	_callbacks: {
		state_change: [],
		progress: [],
		cancel_request: [],
		workitem_created: [],
		workitem_updated: [],
		worklist_updated: [],
		websocket_connected: [],
		websocket_disconnected: [],
		subscription_status: [],
		sync_status: [],
	},
	
	/**
	 * Auto-refresh settings
	 */
	_autoRefresh: {
		enabled: false,
		listView: null,
	},

	/**
	 * Initialize UPS event listeners
	 * Call this once when the page loads
	 */
	init: function() {
		if (this._initialized) return;
		this._initialized = true;

		// Subscribe to UPS realtime events from backend
		frappe.realtime.on("ups_event", (data) => {
			this._handleEvent(data);
		});

		frappe.realtime.on("ups_event_statereport", (data) => {
			this._triggerCallbacks("state_change", data);
		});

		frappe.realtime.on("ups_event_progressreport", (data) => {
			this._triggerCallbacks("progress", data);
		});

		frappe.realtime.on("ups_event_cancelrequest", (data) => {
			this._triggerCallbacks("cancel_request", data);
		});

		frappe.realtime.on("ups_websocket_connected", (data) => {
			this._triggerCallbacks("websocket_connected", data);
		});
		
		// New event types for Scheduled Procedure Step
		frappe.realtime.on("ups_state_changed", (data) => {
			this._triggerCallbacks("state_change", data);
			this._triggerCallbacks("workitem_updated", data);
			this._handleWorklistUpdate(data);
		});
		
		frappe.realtime.on("ups_workitem_created", (data) => {
			this._triggerCallbacks("workitem_created", data);
			this._handleWorklistUpdate(data);
		});
		
		frappe.realtime.on("ups_cancel_request", (data) => {
			this._triggerCallbacks("cancel_request", data);
			this._showCancelRequestAlert(data);
		});
		
		frappe.realtime.on("ups_progress_report", (data) => {
			this._triggerCallbacks("progress", data);
		});
		
		frappe.realtime.on("worklist_updated", (data) => {
			this._triggerCallbacks("worklist_updated", data);
			this._handleWorklistUpdate(data);
		});
		
		frappe.realtime.on("worklist_refresh_required", () => {
			this._refreshWorklist();
		});
		
		frappe.realtime.on("ups_subscription_status", (data) => {
			this._triggerCallbacks("subscription_status", data);
			this._handleSubscriptionStatus(data);
		});
		
		frappe.realtime.on("ups_sync_status", (data) => {
			this._triggerCallbacks("sync_status", data);
		});

		frappe.realtime.on("radiology_procedure_updated", (data) => {
			this._triggerCallbacks("workitem_updated", data);
		});

		console.log("UPS-RS client initialized");
	},

	/**
	 * Register event callback
	 * @param {string} event - Event type: state_change, progress, cancel_request, etc.
	 * @param {Function} callback - Callback function(data)
	 * @returns {Function} Unsubscribe function
	 */
	on: function(event, callback) {
		if (!this._callbacks[event]) {
			this._callbacks[event] = [];
		}
		this._callbacks[event].push(callback);

		// Return unsubscribe function
		return () => {
			const idx = this._callbacks[event].indexOf(callback);
			if (idx > -1) {
				this._callbacks[event].splice(idx, 1);
			}
		};
	},

	/**
	 * Remove event callback
	 * @param {string} event - Event type
	 * @param {Function} callback - Callback to remove
	 */
	off: function(event, callback) {
		if (this._callbacks[event]) {
			const idx = this._callbacks[event].indexOf(callback);
			if (idx > -1) {
				this._callbacks[event].splice(idx, 1);
			}
		}
	},

	/**
	 * Create a new UPS workitem
	 * @param {Object} options - Workitem options
	 * @param {string} options.procedure_step_label - Procedure label
	 * @param {string} options.patient_id - Patient ID
	 * @param {string} [options.patient_name] - Patient name
	 * @param {string} [options.accession_number] - Accession number
	 * @param {string} [options.scheduled_start] - ISO datetime string
	 * @param {string} [options.workitem_code] - Code in format value^meaning^scheme
	 * @param {string} [options.station_name] - Station code in format value^meaning^scheme
	 * @returns {Promise<string>} Created workitem UID
	 */
	createWorkitem: function(options) {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_rs.create_ups_workitem",
			args: options,
			freeze: true,
			freeze_message: __("Creating workitem...")
		}).then(r => {
			const uid = r.message;
			this._triggerCallbacks("workitem_created", { uid, ...options });
			return uid;
		});
	},

	/**
	 * Retrieve a UPS workitem
	 * @param {string} uid - Workitem UID
	 * @returns {Promise<Object>} Workitem data
	 */
	getWorkitem: function(uid) {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_rs.get_ups_workitem",
			args: { uid }
		}).then(r => r.message);
	},

	/**
	 * Search for UPS workitems
	 * @param {Object} [filters] - Search filters
	 * @param {string} [filters.state] - Filter by state (SCHEDULED, IN PROGRESS, etc.)
	 * @param {string} [filters.patient_id] - Filter by patient ID
	 * @param {number} [filters.limit=100] - Max results
	 * @returns {Promise<Array>} List of workitems
	 */
	searchWorkitems: function(filters = {}) {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_rs.search_ups_workitems",
			args: filters
		}).then(r => r.message || []);
	},

	/**
	 * Change workitem state
	 * @param {string} uid - Workitem UID
	 * @param {string} state - Target state (SCHEDULED, IN PROGRESS, COMPLETED, CANCELED)
	 * @param {string} [transaction_uid] - Transaction UID (required for IN PROGRESS state)
	 * @returns {Promise<string>} Transaction UID
	 */
	changeState: function(uid, state, transaction_uid = null) {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_rs.change_ups_state",
			args: { uid, state, transaction_uid },
			freeze: true,
			freeze_message: __("Updating workitem...")
		}).then(r => r.message);
	},

	/**
	 * Start a workitem (change to IN PROGRESS)
	 * @param {string} uid - Workitem UID
	 * @returns {Promise<string>} Transaction UID for subsequent operations
	 */
	startWorkitem: function(uid) {
		return this.changeState(uid, "IN PROGRESS");
	},

	/**
	 * Complete a workitem
	 * @param {string} uid - Workitem UID
	 * @param {string} transaction_uid - Transaction UID from startWorkitem
	 * @returns {Promise}
	 */
	completeWorkitem: function(uid, transaction_uid) {
		return this.changeState(uid, "COMPLETED", transaction_uid);
	},

	/**
	 * Cancel a workitem
	 * @param {string} uid - Workitem UID
	 * @param {string} transaction_uid - Transaction UID from startWorkitem
	 * @returns {Promise}
	 */
	cancelWorkitem: function(uid, transaction_uid) {
		return this.changeState(uid, "CANCELED", transaction_uid);
	},

	/**
	 * Start the UPS event worker (admin only)
	 * @returns {Promise}
	 */
	startWorker: function() {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_worker.enqueue_worker",
			freeze: true,
			freeze_message: __("Starting UPS worker...")
		}).then(r => {
			frappe.show_alert({
				message: __("UPS Event Worker started"),
				indicator: "green"
			});
			return r.message;
		});
	},

	/**
	 * Handle incoming UPS event
	 * @private
	 */
	_handleEvent: function(data) {
		const eventType = data.event_type;
		
		switch (eventType) {
			case "StateReport":
				this._triggerCallbacks("state_change", data);
				break;
			case "ProgressReport":
				this._triggerCallbacks("progress", data);
				break;
			case "CancelRequest":
				this._triggerCallbacks("cancel_request", data);
				break;
			default:
				console.log("Unknown UPS event:", eventType, data);
		}
	},

	/**
	 * Trigger callbacks for an event
	 * @private
	 */
	_triggerCallbacks: function(event, data) {
		const callbacks = this._callbacks[event] || [];
		callbacks.forEach(cb => {
			try {
				cb(data);
			} catch (e) {
				console.error("UPS callback error:", e);
			}
		});
	},
	
	// ============================================================
	// Subscription Management
	// ============================================================
	
	/**
	 * Subscribe to global worklist events
	 * @returns {Promise<Object>} Subscription result
	 */
	subscribeGlobal: function() {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_subscription.subscribe_global",
			freeze: true,
			freeze_message: __("Subscribing to worklist...")
		}).then(r => {
			if (r.message?.success) {
				frappe.show_alert({
					message: __("Subscribed to global worklist"),
					indicator: "green"
				});
			}
			return r.message;
		});
	},
	
	/**
	 * Subscribe to filtered worklist events
	 * @param {Object} filter_criteria - Filter criteria (modality, station_aet, etc.)
	 * @returns {Promise<Object>} Subscription result
	 */
	subscribeFiltered: function(filter_criteria) {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_subscription.subscribe_filtered",
			args: { filter_criteria },
			freeze: true,
			freeze_message: __("Subscribing to worklist...")
		}).then(r => {
			if (r.message?.success) {
				frappe.show_alert({
					message: __("Subscribed to filtered worklist"),
					indicator: "green"
				});
			}
			return r.message;
		});
	},
	
	/**
	 * Unsubscribe from worklist events
	 * @param {string} [subscription_uid] - Optional specific subscription to remove
	 * @returns {Promise<Object>} Unsubscribe result
	 */
	unsubscribe: function(subscription_uid = null) {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_subscription.unsubscribe",
			args: { subscription_uid },
			freeze: true,
			freeze_message: __("Unsubscribing...")
		}).then(r => {
			if (r.message?.success) {
				frappe.show_alert({
					message: r.message.message,
					indicator: "blue"
				});
			}
			return r.message;
		});
	},
	
	/**
	 * Get list of active subscriptions
	 * @returns {Promise<Array>} List of subscriptions
	 */
	listSubscriptions: function() {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_subscription.list_subscriptions"
		}).then(r => r.message || []);
	},
	
	/**
	 * Get subscription and worker status
	 * @returns {Promise<Object>} Status information
	 */
	getSubscriptionStatus: function() {
		return frappe.call({
			method: "healthcare.healthcare.dicom.ups_subscription.get_subscription_status"
		}).then(r => r.message);
	},
	
	// ============================================================
	// Worklist Auto-Refresh
	// ============================================================
	
	/**
	 * Enable/disable automatic worklist refresh on state changes
	 * @param {boolean} enabled - Whether to enable auto-refresh
	 * @param {Object} [listView] - Optional list view to refresh
	 */
	enableWorklistAutoRefresh: function(enabled, listView = null) {
		this._autoRefresh.enabled = enabled;
		if (listView) {
			this._autoRefresh.listView = listView;
		}
	},
	
	/**
	 * Set the list view for auto-refresh
	 * @param {Object} listView - Frappe list view instance
	 */
	setWorklistListView: function(listView) {
		this._autoRefresh.listView = listView;
	},
	
	/**
	 * Handle worklist update events
	 * @private
	 */
	_handleWorklistUpdate: function(data) {
		if (!this._autoRefresh.enabled) return;
		
		// Debounce refresh to avoid too many calls
		if (this._refreshTimeout) {
			clearTimeout(this._refreshTimeout);
		}
		
		this._refreshTimeout = setTimeout(() => {
			this._refreshWorklist();
		}, 500);
	},
	
	/**
	 * Refresh the worklist
	 * @private
	 */
	_refreshWorklist: function() {
		if (this._autoRefresh.listView) {
			this._autoRefresh.listView.refresh();
		} else if (cur_list && cur_list.doctype === "Scheduled Procedure Step") {
			cur_list.refresh();
		}
	},
	
	/**
	 * Show alert for cancel request
	 * @private
	 */
	_showCancelRequestAlert: function(data) {
		frappe.show_alert({
			message: __("Cancellation requested for {0}: {1}", [data.sps_name, data.reason || __("No reason given")]),
			indicator: "orange"
		}, 10);
	},
	
	/**
	 * Handle subscription status updates
	 * @private
	 */
	_handleSubscriptionStatus: function(data) {
		if (data.status === "connected") {
			frappe.show_alert({
				message: __("Connected to UPS worklist"),
				indicator: "green"
			}, 5);
		} else if (data.status === "disconnected") {
			frappe.show_alert({
				message: __("Disconnected from UPS worklist"),
				indicator: "orange"
			}, 5);
		} else if (data.status === "error") {
			frappe.show_alert({
				message: __("UPS subscription error: {0}", [data.error]),
				indicator: "red"
			}, 10);
		}
	}
});

// Auto-initialize when DOM is ready
$(document).ready(function() {
	healthcare.dicom.ups.init();
});
