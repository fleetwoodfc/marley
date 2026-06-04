// Copyright (c) 2023, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Code Value Set", {
	setup(frm) {
		// Restrict code_value picker in the members table to the set's code system
		frm.set_query("code_value", "members", function () {
			return frm.doc.code_system
				? { filters: { code_system: frm.doc.code_system } }
				: {};
		});
	},

	refresh(frm) {
		if (frm.is_new() || frm.doc.members.length > 0) return;

		// Populate the members table from existing Code Value records that
		// already point at this set (e.g. records created before this UI existed).
		frappe.db
			.get_list("Code Value", {
				filters: { value_set: frm.doc.name },
				fields: ["name", "code_system", "display", "definition"],
				limit: 500,
			})
			.then((rows) => {
				if (!rows.length || frm.doc.members.length > 0) return;
				rows.forEach((r) => {
					let row = frm.add_child("members");
					row.code_value = r.name;
					row.code_system = r.code_system;
					row.display = r.display;
					row.definition = r.definition;
				});
				frm.refresh_field("members");
				// Save immediately so the rows are persisted
				frm.save();
			});
	},
});
