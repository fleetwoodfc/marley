// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.listview_settings["Requested Procedure"] = {
	add_fields: ["status", "procedure_type", "modality", "scheduled_datetime"],
	filters: [],

	get_indicator(doc) {
		const status_map = {
			"Draft": [__("Draft"), "orange", "status,=,Draft"],
			"Scheduled": [__("Scheduled"), "blue", "status,=,Scheduled"],
			"In Progress": [__("In Progress"), "yellow", "status,=,In Progress"],
			"Completed": [__("Completed"), "green", "status,=,Completed"],
			"Cancelled": [__("Cancelled"), "grey", "status,=,Cancelled"],
		};
		return status_map[doc.status] || [__("Draft"), "orange", "status,=,Draft"];
	},
};
