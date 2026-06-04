frappe.ui.form.on("Radiology Report Template Version", {
	refresh(frm) {
		frm.trigger("add_lifecycle_buttons");
		frm.trigger("show_lineage_info");
	},

	show_lineage_info(frm) {
		// Highlight supersession/replacement lineage when relevant
		if (frm.doc.replacement_version) {
			frm.dashboard.add_comment(
				__("This version has been superseded by {0}.", [
					`<a href="/app/radiology-report-template-version/${frm.doc.replacement_version}">${frm.doc.replacement_version}</a>`
				]),
				"yellow"
			);
		}
		if (frm.doc.replaces_version) {
			frm.dashboard.add_comment(
				__("This version replaces {0}.", [
					`<a href="/app/radiology-report-template-version/${frm.doc.replaces_version}">${frm.doc.replaces_version}</a>`
				]),
				"blue"
			);
		}
	},

	add_lifecycle_buttons(frm) {
		const status = frm.doc.lifecycle_status;
		const isNew = frm.is_new();

		if (isNew) return;

		// Validate button – always available on saved records
		frm.add_custom_button(__("Validate"), () => {
			frappe.call({
				method: "healthcare.radiology_reporting.api.report_template_manager.validate_version",
				args: { version_name: frm.docname },
				freeze: true,
				freeze_message: __("Running validation..."),
				callback(r) {
					if (!r.exc) {
						const result = r.message;
						frappe.msgprint({
							title: __("Validation Result"),
							message: `<b>Status:</b> ${result.validation_status}<br><b>Summary:</b> ${result.validation_summary}`,
							indicator: result.validation_status === "Failed" ? "red" : result.validation_status === "Warnings" ? "orange" : "green",
						});
						frm.reload_doc();
					}
				},
			});
		}, __("Actions"));

		// Preview button – renders mrrt_html in a dialog (FR-014); available to all users with Read permission
		frm.add_custom_button(__("Preview"), () => {
			const html = frm.doc.mrrt_html;
			if (!html || !html.trim()) {
				frappe.msgprint({ title: __("Preview"), message: __("No template content (mrrt_html) to preview."), indicator: "orange" });
				return;
			}
			const dialog = new frappe.ui.Dialog({
				title: __("Template Preview: {0}", [frm.doc.version_label || frm.docname]),
				size: "extra-large",
			});
			// Render in a sandboxed iframe to isolate template CSS/JS
			dialog.$wrapper.find(".modal-body").html(
				`<iframe sandbox="allow-same-origin" style="width:100%;height:70vh;border:1px solid #d1d8dd;border-radius:4px;"
				  srcdoc="${frappe.utils.escape_html(html).replace(/"/g, '&quot;')}"></iframe>`
			);
			dialog.show();
		}, __("Actions"));

		if (status === "Draft") {
			frm.add_custom_button(__("Submit for Review"), () => {
				frappe.prompt(
					[{ label: __("Notes"), fieldname: "notes", fieldtype: "Small Text" }],
					({ notes }) => {
						frappe.call({
							method: "healthcare.radiology_reporting.api.report_template_manager.submit_for_review",
							args: { version_name: frm.docname, notes },
							freeze: true,
							callback(r) { if (!r.exc) frm.reload_doc(); },
						});
					},
					__("Submit for Review"),
					__("Submit")
				);
			}, __("Actions"));
		}

		if (status === "Review Ready") {
			frm.add_custom_button(__("Approve"), () => {
				frappe.prompt(
					[{ label: __("Approval Notes"), fieldname: "notes", fieldtype: "Small Text" }],
					({ notes }) => {
						frappe.call({
							method: "healthcare.radiology_reporting.api.report_template_manager.approve_version",
							args: { version_name: frm.docname, notes },
							freeze: true,
							callback(r) { if (!r.exc) frm.reload_doc(); },
						});
					},
					__("Approve Version"),
					__("Approve")
				);
			}, __("Actions"));

			frm.add_custom_button(__("Return to Draft"), () => {
				frappe.call({
					method: "healthcare.radiology_reporting.api.report_template_manager.return_to_draft",
					args: { version_name: frm.docname },
					freeze: true,
					callback(r) { if (!r.exc) frm.reload_doc(); },
				});
			}, __("Actions"));
		}

		if (status === "Approved") {
			frm.add_custom_button(__("Publish"), () => {
				frappe.prompt(
					[{ label: __("Publisher Notes"), fieldname: "notes", fieldtype: "Small Text" }],
					({ notes }) => {
						frappe.call({
							method: "healthcare.radiology_reporting.api.report_template_manager.publish_version",
							args: { version_name: frm.docname, notes },
							freeze: true,
							callback(r) { if (!r.exc) frm.reload_doc(); },
						});
					},
					__("Publish Version"),
					__("Publish")
				);
			}, __("Actions"));

			frm.add_custom_button(__("Retire"), () => {
				frappe.confirm(__("Retire this approved version?"), () => {
					frappe.call({
						method: "healthcare.radiology_reporting.api.report_template_manager.retire_version",
						args: { version_name: frm.docname },
						freeze: true,
						callback(r) { if (!r.exc) frm.reload_doc(); },
					});
				});
			}, __("Actions"));
		}

		if (status === "Published") {
			frm.add_custom_button(__("Retire"), () => {
				frappe.prompt(
					[{ label: __("Retirement Notes"), fieldname: "notes", fieldtype: "Small Text" }],
					({ notes }) => {
						frappe.confirm(__("Retire this published version? This will remove it as the active template."), () => {
							frappe.call({
								method: "healthcare.radiology_reporting.api.report_template_manager.retire_version",
								args: { version_name: frm.docname, notes },
								freeze: true,
								callback(r) { if (!r.exc) frm.reload_doc(); },
							});
						});
					},
					__("Retire Version"),
					__("Retire")
				);
			}, __("Actions"));
		}

		// Status badge colour
		const colourMap = {
			Draft: "grey",
			"Review Ready": "blue",
			Approved: "green",
			Published: "green",
			Superseded: "orange",
			Retired: "red",
		};
		frm.page.set_indicator(status, colourMap[status] || "grey");
	},
});
