frappe.listview_settings["Radiology Report Template"] = {
	add_fields: ["status", "default_modality", "default_body_part", "current_published_version"],

	get_indicator(doc) {
		// Active with a current published version → green
		if (doc.status === "Active" && doc.current_published_version) {
			return [__("Active"), "green"];
		}
		// Active but no published version (all versions retired/superseded or none published yet) → orange
		if (doc.status === "Active" && !doc.current_published_version) {
			return [__("Active – No Published Version"), "orange"];
		}
		// Inactive → grey
		if (doc.status === "Inactive") {
			return [__("Inactive"), "grey"];
		}
		// Archived (retired from catalog) → red
		if (doc.status === "Archived") {
			return [__("Archived"), "red"];
		}
		return [doc.status || __("Unknown"), "grey"];
	},

};
