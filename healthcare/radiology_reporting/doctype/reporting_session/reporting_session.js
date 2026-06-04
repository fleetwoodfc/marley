// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Reporting Session", {
	refresh(frm) {
		frm.set_indicator();

		if (!frm.is_new()) {
			// Session action buttons based on status
			if (frm.doc.status === "Active") {
				frm.add_custom_button(__("Suspend Session"), () => {
					frappe.confirm(
						__("Suspend this reporting session?"),
						() => {
							frm.call("suspend_session").then(() => frm.reload_doc());
						}
					);
				}, __("Actions"));

				frm.add_custom_button(__("Close Session"), () => {
					frappe.confirm(
						__("Close this reporting session? This cannot be undone."),
						() => {
							frm.call("close_session").then(() => frm.reload_doc());
						}
					);
				}, __("Actions"));
			}

			if (frm.doc.status === "Suspended") {
				frm.add_custom_button(__("Resume Session"), () => {
					frm.call("resume_session").then(() => frm.reload_doc());
				}, __("Actions"));

				frm.add_custom_button(__("Close Session"), () => {
					frappe.confirm(
						__("Close this suspended session?"),
						() => {
							frm.call("close_session").then(() => frm.reload_doc());
						}
					);
				}, __("Actions"));
			}

			if (frm.doc.status !== "Closed") {
				frm.add_custom_button(__("Refresh Statistics"), () => {
					frm.call("update_statistics").then(() => frm.reload_doc());
				}, __("Actions"));
			}
		}
	},

	set_indicator(frm) {
		const colors = {
			"Active": "green",
			"Suspended": "orange",
			"Closed": "grey",
		};
		if (frm.doc.status) {
			frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "grey");
		}
	},
});
