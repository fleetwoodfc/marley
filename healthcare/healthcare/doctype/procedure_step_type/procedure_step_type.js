// Copyright (c) 2026, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Procedure Step Type", {
	refresh: function(frm) {
		// Show system step type indicator
		if (frm.doc.is_system) {
			frm.set_intro(__("This is a system-provided step type and cannot be deleted."), "blue");
		}
		
		// Disable delete button for system step types
		if (frm.doc.is_system) {
			frm.disable_delete();
		}
	}
});

// List view configuration
frappe.listview_settings["Procedure Step Type"] = {
	add_fields: ["is_system", "is_active", "phase"],
	
	get_indicator: function(doc) {
		if (!doc.is_active) {
			return [__("Inactive"), "grey", "is_active,=,0"];
		}
		if (doc.is_system) {
			return [__("System"), "blue", "is_system,=,1"];
		}
		return [__("Custom"), "green", "is_system,=,0"];
	},
	
	filters: [
		["is_active", "=", 1]
	],
	
	button: {
		show: function(doc) {
			return doc.name;
		},
		get_label: function() {
			return __("View");
		},
		get_description: function(doc) {
			return __("View {0}", [doc.step_name]);
		},
		action: function(doc) {
			frappe.set_route("Form", "Procedure Step Type", doc.name);
		}
	}
};
