// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Radiology Report", {
	refresh(frm) {
		frm.trigger("set_report_indicator");

		if (frm.is_new()) return;

		// Sign / Finalize button — only for Draft or Preliminary
		if (["Draft", "Preliminary"].includes(frm.doc.report_status)) {
			frm.add_custom_button(
				__("Sign & Finalize"),
				() => {
					frappe.confirm(
						__(
							"Electronically sign and finalize this report? This will set the status to Final."
						),
						() => {
							frm.call("sign_report").then(() => frm.reload_doc());
						}
					);
				},
				__("Actions")
			);
		}

		// Mark as Preliminary — only from Draft
		if (frm.doc.report_status === "Draft") {
			frm.add_custom_button(
				__("Mark Preliminary"),
				() => {
					frm.set_value("report_status", "Preliminary");
					frm.save();
				},
				__("Actions")
			);
		}

		// Add Addendum — only for Final or Amended
		if (["Final", "Amended"].includes(frm.doc.report_status)) {
			frm.add_custom_button(
				__("Add Addendum"),
				() => {
					frm.trigger("show_addendum_dialog");
				},
				__("Actions")
			);
		}

		// Cancel report — non-terminal statuses
		if (!["Final", "Amended", "Cancelled"].includes(frm.doc.report_status)) {
			frm.add_custom_button(
				__("Cancel Report"),
				() => {
					frappe.confirm(
						__("Cancel this radiology report?"),
						() => {
							frm.set_value("report_status", "Cancelled");
							frm.save();
						}
					);
				},
				__("Actions")
			);
		}

		// Apply Report Template — available on Draft and Preliminary reports (before finalisation)
		if (["Draft", "Preliminary"].includes(frm.doc.report_status)) {
			frm.add_custom_button(__("Apply Report Template"), () => {
				frm.trigger("resolve_and_apply_template");
			}, __("Actions"));
		}
	},

	resolve_and_apply_template(frm) {
		frappe.call({
			method: "healthcare.radiology_reporting.api.report_template_manager.resolve_template",
			args: {
				modality: frm.doc.modality || "",
				body_part: frm.doc.body_part || "",
				language: "",
				organization: "",
				radiology_procedure_template: frm.doc.radiology_procedure_template || "",
			},
			callback(r) {
				if (r.exc) return;
				const result = r.message;
				if (!result.resolved) {
					frappe.msgprint({
						title: __("No Template Found"),
						message: __("No published template matches the current modality/body-part context."),
						indicator: "orange",
					});
					return;
				}
				const v = result.version;
				frappe.confirm(
					__("Apply template <b>{0}</b> (version {1})?", [result.template.title, v.version_label]),
					() => {
						frm.set_value("report_template", result.template.name);
						frm.set_value("report_template_version", v.name);
						frm.set_value("template_version_label", v.version_label);
						frm.save();
					}
				);
			},
		});
	},

	set_report_indicator(frm) {
		const colors = {
			Draft: "orange",
			Preliminary: "blue",
			Final: "green",
			Amended: "purple",
			Cancelled: "red",
		};
		if (frm.doc.report_status) {
			frm.page.set_indicator(
				__(frm.doc.report_status),
				colors[frm.doc.report_status] || "grey"
			);
		}
	},

	show_addendum_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Add Addendum"),
			fields: [
				{
					fieldname: "addendum_type",
					fieldtype: "Select",
					label: __("Type"),
					options: "Addendum\nAmendment\nCorrection\nClarification",
					default: "Addendum",
					reqd: 1,
				},
				{
					fieldname: "addendum_text",
					fieldtype: "Text Editor",
					label: __("Addendum Text"),
					reqd: 1,
				},
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Reason"),
				},
			],
			primary_action_label: __("Add"),
			primary_action(values) {
				frm.call("add_addendum", {
					addendum_text: values.addendum_text,
					reason: values.reason,
					addendum_type: values.addendum_type,
				}).then(() => {
					d.hide();
					frm.reload_doc();
				});
			},
		});
		d.show();
	},
});
