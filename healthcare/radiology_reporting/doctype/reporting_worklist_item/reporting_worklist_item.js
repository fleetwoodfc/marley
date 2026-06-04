// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Reporting Worklist Item", {
	refresh(frm) {
		frm.trigger("set_worklist_indicator");

		if (frm.is_new()) return;

		// Start Reading — only for Pending items
		if (frm.doc.status === "Pending") {
			frm.add_custom_button(__("Start Reading"), () => {
				frm.call("start_reading").then(() => frm.reload_doc());
			}, __("Actions"));
		}

		// Create Report — for In Progress items without a report
		// Triggers template resolution before creating the report (T006/T008)
		if (frm.doc.status === "In Progress" && !frm.doc.radiology_report) {
			frm.add_custom_button(__("Create Report"), () => {
				frm.trigger("resolve_and_create_report");
			}, __("Actions"));
		}

		// Open linked report
		if (frm.doc.radiology_report) {
			frm.add_custom_button(__("Open Report"), () => {
				frappe.set_route("Form", "Radiology Report", frm.doc.radiology_report);
			});
		}

		// Cancel — for non-terminal statuses
		if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Cancel"), () => {
				frappe.confirm(
					__("Remove this item from the worklist?"),
					() => {
						frm.set_value("status", "Cancelled");
						frm.save();
					}
				);
			}, __("Actions"));
		}
	},

	// ---------------------------------------------------------------------------
	// T006: Template resolution + selection dialog
	// T012: NFR-001 — 3-second client-side timeout + error degradation path
	// ---------------------------------------------------------------------------
	resolve_and_create_report(frm) {
		// Guard flag prevents double-handling if both the timer fires and the
		// error callback fires in the same tick (frappe.call does not support
		// a native timeout option, so we manage it ourselves).
		let _handled = false;
		const _timer = setTimeout(() => {
			if (_handled) return;
			_handled = true;
			frm.trigger("_resolution_unavailable");
		}, 3000);

		frappe.call({
			method: "healthcare.radiology_reporting.api.report_template_manager.resolve_template_candidates",
			args: {
				modality: frm.doc.modality || "",
				body_part: frm.doc.body_part || "",
				radiology_procedure_template: frm.doc.radiology_procedure_template || "",
			},
			freeze: true,
			freeze_message: __("Finding matching templates…"),
			callback(r) {
				if (_handled) return;
				clearTimeout(_timer);
				_handled = true;
				if (r.exc) {
					frm.trigger("_resolution_unavailable");
					return;
				}
				const result = r.message;
				if (result && result.resolved && result.candidates && result.candidates.length > 0) {
					frm._template_candidates = result.candidates;
					frm.trigger("_show_template_selection_dialog");
				} else {
					// T008: no-match fallback
					const modality = frm.doc.modality || "—";
					const body_part = frm.doc.body_part || "—";
					frappe.confirm(
						__("No published template found for {0} / {1}. Create a blank report?", [modality, body_part]),
						() => {
							frm._selected_template_version = "";
							frm.trigger("_do_create_report");
						}
					);
				}
			},
			error() {
				if (_handled) return;
				clearTimeout(_timer);
				_handled = true;
				frm.trigger("_resolution_unavailable");
			},
		});
	},

	// T012: NFR-001 degradation path — called on timeout or network/server error
	_resolution_unavailable(frm) {
		frappe.show_alert({
			message: __("Automatic template resolution was unavailable. You can create a blank report or try again."),
			indicator: "orange",
		});
		frappe.confirm(
			__("Create a blank report?"),
			() => {
				frm._selected_template_version = "";
				frm.trigger("_do_create_report");
			}
		);
	},

	_show_template_selection_dialog(frm) {
		const candidates = frm._template_candidates || [];
		// Build options as [{value, label}] — Frappe Dialog Select requires this for separate value/label
		const options = candidates.map(c => ({
			value: c.version.name,
			label: `${c.template.title} — v${c.version.version_label}`,
		}));

		const d = new frappe.ui.Dialog({
			title: __("Select Report Template"),
			fields: [
				{
					fieldname: "template_version",
					fieldtype: "Select",
					label: __("Template"),
					options: options,
					default: candidates[0].version.name,
					description: __(
						"Select a template to pre-populate the report. The first option is the highest-priority match for {0} / {1}.",
						[frm.doc.modality || "—", frm.doc.body_part || "—"]
					),
				},
			],
			primary_action_label: __("Create Report with Template"),
			primary_action(values) {
				d.hide();
				frm._selected_template_version = values.template_version || "";
				frm.trigger("_do_create_report");
			},
			secondary_action_label: __("Create Blank Report"),
			secondary_action() {
				d.hide();
				frm._selected_template_version = "";
				frm.trigger("_do_create_report");
			},
		});
		d.show();
	},

	// T006a: execute create_report and handle retired-version error gracefully
	_do_create_report(frm) {
		const template_version = frm._selected_template_version || "";
		frm.call("create_report", { template_version })
			.then((r) => {
				frm.reload_doc();
				if (r && r.message) {
					frappe.set_route("Form", "Radiology Report", r.message.name);
				}
			})
			.catch((err) => {
				// Handle the case where the selected version is no longer Published
				// (retired/superseded between dialog open and confirm — T006a)
				const msg = (err && err.message) ? err.message : "";
				if (msg.includes("not Published")) {
					frappe.msgprint({
						title: __("Template No Longer Available"),
						message: __("The selected template version is no longer published. Please select a different template."),
						indicator: "orange",
					});
					// Re-run resolution to refresh candidates
					frm.trigger("resolve_and_create_report");
				}
				// Other errors surface via Frappe's default error handler
			});
	},

	set_worklist_indicator(frm) {
		const colors = {
			"Pending": "orange",
			"In Progress": "blue",
			"Draft Report": "yellow",
			"Preliminary": "purple",
			"Completed": "green",
			"Cancelled": "red",
		};
		if (frm.doc.status) {
			frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "grey");
		}
	},
});
