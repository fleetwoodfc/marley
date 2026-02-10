// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.listview_settings["Scheduled Procedure Step"] = {
	add_fields: ["ups_state", "modality", "priority", "scheduled_datetime"],
	
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
		// Add custom filters
		listview.page.add_field({
			label: __("Modality"),
			fieldtype: "Select",
			fieldname: "modality_filter",
			options: "\nCT\nMR\nUS\nXR\nNM\nPT",
			change: function() {
				const modality = this.get_value();
				if (modality) {
					listview.filter_area.add(
						["Scheduled Procedure Step", "modality", "=", modality]
					);
				} else {
					listview.filter_area.remove("modality");
				}
				listview.refresh();
			}
		});
		
		listview.page.add_field({
			label: __("Station"),
			fieldtype: "Data",
			fieldname: "station_filter",
			change: function() {
				const station = this.get_value();
				if (station) {
					listview.filter_area.add(
						["Scheduled Procedure Step", "station_aet", "like", `%${station}%`]
					);
				} else {
					listview.filter_area.remove("station_aet");
				}
				listview.refresh();
			}
		});
		
		listview.page.add_field({
			label: __("Scheduled Date"),
			fieldtype: "Date",
			fieldname: "date_filter",
			default: frappe.datetime.get_today(),
			change: function() {
				const date = this.get_value();
				if (date) {
					const next_day = frappe.datetime.add_days(date, 1);
					listview.filter_area.add(
						["Scheduled Procedure Step", "scheduled_datetime", "between", [date, next_day]]
					);
				} else {
					listview.filter_area.remove("scheduled_datetime");
				}
				listview.refresh();
			}
		});
		
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
	
	primary_action: function() {
		// Quick claim from list (if single row selected)
		const selected = this.get_checked_items();
		if (selected.length === 1) {
			const sps = selected[0];
			if (sps.ups_state === "SCHEDULED") {
				frappe.confirm(
					__("Claim this procedure and start work?"),
					() => {
						frappe.call({
							method: "healthcare.healthcare.doctype.scheduled_procedure_step.api.claim_procedure",
							args: { procedure_step: sps.name },
							callback: (r) => {
								if (r.message && r.message.success) {
									frappe.show_alert({
										message: __("Procedure claimed. Transaction UID: {0}", [r.message.transaction_uid]),
										indicator: "green"
									});
									this.refresh();
								}
							}
						});
					}
				);
			} else {
				frappe.msgprint(__("Only SCHEDULED procedures can be claimed"));
			}
		}
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
