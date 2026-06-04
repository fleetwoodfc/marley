// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Radiology Procedure Template", {
	refresh: function (frm) {
		// Toggle item linking fields based on link_existing_item
		if (!frm.doc.__islocal) {
			frm.set_df_property("link_existing_item", "read_only", 1);
		}
	},

	link_existing_item: function (frm) {
		if (frm.doc.link_existing_item) {
			frm.set_value("item_code", "");
			frm.set_value("is_billable", 0);
			frm.set_value("rate", 0);
		} else {
			frm.set_value("item", "");
		}
	},

	item: function (frm) {
		if (frm.doc.link_existing_item && frm.doc.item) {
			frappe.db.get_value("Item", frm.doc.item, ["item_group"], function (r) {
				if (r) {
					frm.set_value("item_group", r.item_group);
				}
			});
		}
	},

	is_billable: function (frm) {
		if (!frm.doc.is_billable) {
			frm.set_value("rate", 0);
		}
	}
});
