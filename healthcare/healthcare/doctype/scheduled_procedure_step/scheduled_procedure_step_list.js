// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.listview_settings["Scheduled Procedure Step"] = {
	add_fields: ["ups_state", "modality", "priority", "scheduled_datetime", "mwl_sync_status"],
	
	filters: [
		["ups_state", "in", ["SCHEDULED", "IN PROGRESS"]]
	],
	
	get_indicator: function(doc) {
		// Color-code by UPS state
		const states = {
			"SCHEDULED": ["Scheduled", "blue", "ups_state,=,SCHEDULED"],
			"IN PROGRESS": ["In Progress", "orange", "ups_state,=,IN PROGRESS"],
			"COMPLETED": ["Completed", "green", "ups_state,=,COMPLETED"],
			"CANCELED": ["Canceled", "red", "ups_state,=,CANCELED"]
		};
		
		return states[doc.ups_state] || ["Unknown", "grey", ""];
	},
	
	formatters: {
		scheduled_datetime: function(value) {
			if (value) {
				return frappe.datetime.str_to_user(value);
			}
			return "";
		},
		
		priority: function(value) {
			const badges = {
				"STAT": '<span class="badge badge-danger">STAT</span>',
				"HIGH": '<span class="badge badge-warning">HIGH</span>',
				"ROUTINE": '<span class="badge badge-info">ROUTINE</span>',
				"MEDIUM": '<span class="badge badge-secondary">MEDIUM</span>',
				"LOW": '<span class="badge badge-light">LOW</span>'
			};
			return badges[value] || value;
		}
	},
	
	onload: function(listview) {
		// Add quick filter buttons using inner buttons
		listview.page.add_inner_button(__("Today"), function() {
			const today = frappe.datetime.get_today();
			const tomorrow = frappe.datetime.add_days(today, 1);
			listview.filter_area.clear(false).then(() => {
				listview.filter_area.add([
					[listview.doctype, "scheduled_datetime", "between", [today, tomorrow]],
					[listview.doctype, "ups_state", "in", ["SCHEDULED", "IN PROGRESS"]]
				]);
				listview.refresh();
			});
		}, __("Quick Filters"));
		
		listview.page.add_inner_button(__("All Scheduled"), function() {
			listview.filter_area.clear(false).then(() => {
				listview.filter_area.add([[listview.doctype, "ups_state", "=", "SCHEDULED"]]);
				listview.refresh();
			});
		}, __("Quick Filters"));
		
		listview.page.add_inner_button(__("In Progress"), function() {
			listview.filter_area.clear(false).then(() => {
				listview.filter_area.add([[listview.doctype, "ups_state", "=", "IN PROGRESS"]]);
				listview.refresh();
			});
		}, __("Quick Filters"));
		
		listview.page.add_inner_button(__("Completed"), function() {
			listview.filter_area.clear(false).then(() => {
				listview.filter_area.add([[listview.doctype, "ups_state", "=", "COMPLETED"]]);
				listview.refresh();
			});
		}, __("Quick Filters"));
		
		// MWL Sync Status Filters
		listview.page.add_inner_button(__("MWL Synced"), function() {
			listview.filter_area.clear(false).then(() => {
				listview.filter_area.add([
					[listview.doctype, "mwl_sync_status", "=", "synced"],
					[listview.doctype, "ups_state", "=", "SCHEDULED"]
				]);
				listview.refresh();
			});
		}, __("MWL Filters"));
		
		listview.page.add_inner_button(__("MWL Pending"), function() {
			listview.filter_area.clear(false).then(() => {
				listview.filter_area.add([
					[listview.doctype, "mwl_sync_status", "in", ["pending", ""]],
					[listview.doctype, "ups_state", "=", "SCHEDULED"]
				]);
				listview.refresh();
			});
		}, __("MWL Filters"));
		
		listview.page.add_inner_button(__("MWL Errors"), function() {
			listview.filter_area.clear(false).then(() => {
				listview.filter_area.add([[listview.doctype, "mwl_sync_status", "=", "error"]]);
				listview.refresh();
			});
		}, __("MWL Filters"));
		
		// Add quick actions
		listview.page.add_inner_button(__("Refresh Worklist"), function() {
			listview.refresh();
		});
		
		// Add worklist counts to page
		listview.page.add_inner_button(__("Show Counts"), function() {
			frappe.call({
				method: "healthcare.healthcare.doctype.scheduled_procedure_step.api.get_worklist_counts",
				callback: function(r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Worklist Status"),
							message: `
								<table class="table table-bordered">
									<tr><td><strong>Scheduled</strong></td><td>${r.message.scheduled}</td></tr>
									<tr><td><strong>In Progress</strong></td><td>${r.message.in_progress}</td></tr>
									<tr><td><strong>Completed Today</strong></td><td>${r.message.completed_today}</td></tr>
									<tr><td><strong>Canceled Today</strong></td><td>${r.message.canceled_today}</td></tr>
								</table>
							`,
							indicator: "blue"
						});
					}
				}
			});
		});
	},
	
	button: {
		show: function(doc) {
			return doc.ups_state === "SCHEDULED";
		},
		get_label: function() {
			return __("Claim");
		},
		get_description: function(doc) {
			return __("Claim procedure {0}", [doc.name]);
		},
		action: function(doc) {
			frappe.call({
				method: "healthcare.healthcare.doctype.scheduled_procedure_step.api.claim_procedure",
				args: { procedure_step: doc.name },
				callback: function(r) {
					if (r.message && r.message.success) {
						frappe.show_alert({
							message: __("Procedure claimed successfully"),
							indicator: "green"
						});
						cur_list.refresh();
					}
				}
			});
		}
	}
};
