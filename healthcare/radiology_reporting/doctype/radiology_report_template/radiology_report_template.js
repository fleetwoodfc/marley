frappe.ui.form.on("Radiology Report Template", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("View Versions"), () => {
			frappe.set_route("List", "Radiology Report Template Version", {
				report_template: frm.docname,
			});
		});

		frm.add_custom_button(__("Import MRRT"), () => {
			frm.trigger("show_import_dialog");
		}, __("Actions"));

		if (frm.doc.current_published_version) {
			frm.add_custom_button(__("Export Published Version"), () => {
				frappe.call({
					method: "healthcare.radiology_reporting.api.report_template_manager.export_mrrt",
					args: { version_name: frm.doc.current_published_version },
					callback(r) {
						if (r.exc) return;
						const data = r.message;
						const blob = new Blob([data.mrrt_html], { type: "text/html" });
						const url = URL.createObjectURL(blob);
						const a = document.createElement("a");
						a.href = url;
						a.download = `${frm.doc.template_code}_${data.version_label}.html`;
						a.click();
						URL.revokeObjectURL(url);
						frappe.msgprint(__("Exported version {0}.", [data.version_label]));
						frm.reload_doc();
					},
				});
			}, __("Actions"));
		}
	},

	show_import_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Import MRRT Template"),
			fields: [
				{
					fieldname: "file_section",
					fieldtype: "Section Break",
					label: __("Upload File"),
					description: __(
						"Select a <code>.mrrt</code> file (ZIP) or <code>.html</code> file downloaded from radreport.org. " +
						"Title and content will be populated automatically."
					),
				},
				{
					fieldname: "file_upload_html",
					fieldtype: "HTML",
					options: `<div class="mrrt-upload-row" style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
						<input type="file" accept=".mrrt,.html,.htm,.zip" class="mrrt-file-input" style="display:none">
						<button class="btn btn-default btn-sm mrrt-pick-btn">
							<svg class="icon icon-sm" style="margin-right:4px"><use href="#icon-upload"></use></svg>
							${__("Choose .mrrt or .html File")}
						</button>
						<span class="mrrt-file-status text-muted small"></span>
					</div>`,
				},
				{
					fieldname: "col_break_1",
					fieldtype: "Column Break",
				},
				{
					fieldname: "version_label",
					fieldtype: "Data",
					label: __("Version Label"),
					reqd: 1,
					placeholder: "e.g. 1.0",
				},
				{
					fieldname: "language",
					fieldtype: "Data",
					label: __("Language"),
					default: "en",
				},
				{
					fieldname: "content_section",
					fieldtype: "Section Break",
					label: __("Content"),
					collapsible: 1,
					collapsed: 1,
				},
				{
					fieldname: "mrrt_content",
					fieldtype: "Code",
					options: "HTML",
					label: __("MRRT HTML Content"),
					reqd: 1,
					description: __("Auto-populated when you choose a file, or paste content directly."),
				},
				{
					fieldname: "details_section",
					fieldtype: "Section Break",
					label: __("Details"),
				},
				{
					fieldname: "replaces_version",
					fieldtype: "Link",
					label: __("Replaces Version (optional)"),
					options: "Radiology Report Template Version",
					get_query() {
						return { filters: { report_template: frm.docname } };
					},
				},
				{
					fieldname: "notes",
					fieldtype: "Small Text",
					label: __("Import Notes"),
				},
			],
			primary_action_label: __("Import"),
			primary_action({ version_label, language, mrrt_content, replaces_version, notes }) {
				frappe.call({
					method: "healthcare.radiology_reporting.api.report_template_manager.import_mrrt",
					args: {
						report_template: frm.docname,
						version_label,
						mrrt_content,
						language,
						replaces_version,
						notes,
					},
					freeze: true,
					freeze_message: __("Importing MRRT content..."),
					callback(r) {
						if (r.exc) return;
						d.hide();
						const result = r.message;
						frappe.msgprint({
							title: __("Import Successful"),
							message: __("Created version {0} with validation status: {1}.", [
								result.version_label,
								result.validation_status,
							]),
							indicator: result.validation_status === "Failed" ? "orange" : "green",
						});
						frappe.set_route("Form", "Radiology Report Template Version", result.name);
					},
				});
			},
		});

		d.show();

		// Wire up the file picker after the dialog renders
		const $wrap = d.$wrapper;
		const $input = $wrap.find(".mrrt-file-input");
		const $btn   = $wrap.find(".mrrt-pick-btn");
		const $status = $wrap.find(".mrrt-file-status");

		$btn.on("click", () => $input.trigger("click"));

		$input.on("change", function () {
			const file = this.files[0];
			if (!file) return;

			$status.text(__("Reading {0}...", [file.name]));
			$btn.prop("disabled", true);

			const reader = new FileReader();
			reader.onload = function (e) {
				// Convert ArrayBuffer → base64
				const bytes = new Uint8Array(e.target.result);
				let binary = "";
				for (let i = 0; i < bytes.byteLength; i++) {
					binary += String.fromCharCode(bytes[i]);
				}
				const b64 = btoa(binary);

				frappe.call({
					method: "healthcare.radiology_reporting.api.report_template_manager.extract_mrrt_package",
					args: { file_content_b64: b64, filename: file.name },
					callback(r) {
						$btn.prop("disabled", false);
						if (r.exc) {
							$status.text(__("Failed to extract file.")).css("color", "var(--red-500)");
							return;
						}
						const data = r.message;

						// Auto-populate content field
						d.set_value("mrrt_content", data.mrrt_html);

						// Auto-populate language if blank
						if (!d.get_value("language") || d.get_value("language") === "en") {
							d.set_value("language", data.language || "en");
						}

						// Expand the content section so user can preview
						d.$wrapper.find('[data-fieldname="content_section"] .section-head').trigger("click");

						$status
							.text(__("✓ {0} — {1}", [file.name, data.mrrt_title || __("No title found")]))
							.css("color", "var(--green-600)");
					},
				});
			};
			reader.readAsArrayBuffer(file);
		});
	},
});
