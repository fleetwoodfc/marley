// Copyright (c) 2023, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Diagnostic Report", {
	refresh: function (frm) {
		render_diagnostic_content(frm);
		if (!frm.is_new()) {
			frm.add_custom_button(__(`Get PDF`), function () {
				generate_pdf_with_print_format(frm);
			});
		}

		// Show category indicator
		if (frm.doc.category) {
			const color_map = { LAB: "blue", RAD: "orange", PATH: "purple", CARD: "red" };
			frm.page.set_indicator(frm.doc.category, color_map[frm.doc.category] || "grey");
		}

		// Show FHIR status badge
		if (frm.doc.fhir_status) {
			const fhir_color = {
				Registered: "grey", Partial: "orange", Preliminary: "yellow",
				Final: "green", Amended: "blue", Cancelled: "red",
			};
			frm.dashboard.set_headline(
				`<span class="indicator-pill ${fhir_color[frm.doc.fhir_status] || "grey"}">
					FHIR: ${frm.doc.fhir_status}
				</span>`
			);
		}

		// Link to source Radiology Report
		if (frm.doc.category === "RAD" && frm.doc.radiology_report) {
			frm.add_custom_button(__("Open Radiology Report"), function () {
				frappe.set_route("Form", "Radiology Report", frm.doc.radiology_report);
			}, __("View"));
		}
	},
	before_save: function (frm) {
		if (!frm.is_new() && frm.is_dirty() && frm.doc.category !== "RAD") {
			if (this.diagnostic_report) {
				this.diagnostic_report.save_action("save");
			}
		}
	},
	after_workflow_action: function (frm) {
		frappe.call({
			method: "healthcare.healthcare.doctype.diagnostic_report.diagnostic_report.set_observation_status",
			args: {
				docname: frm.doc.name,
			},
		});
	},
});

/**
 * Render category-specific content in the observation HTML area.
 * LAB: renders the observation widget (lab results).
 * RAD: renders the radiology report inline.
 * Others: renders generic observation widget if patient is set.
 */
var render_diagnostic_content = function (frm) {
	frm.fields_dict.observation.html("");

	if (frm.doc.category === "RAD" && frm.doc.radiology_report) {
		render_radiology_content(frm);
	} else if (frm.doc.patient) {
		// Lab / generic path — the original observation widget
		this.diagnostic_report = new healthcare.Diagnostic.DiagnosticReport({
			frm: frm,
			observation_wrapper: $(frm.fields_dict.observation.wrapper),
			create_observation: false,
		});
		this.diagnostic_report.refresh();
	}
};

/**
 * Fetch and render radiology report content inline in the DR form.
 */
var render_radiology_content = function (frm) {
	frappe.call({
		method: "healthcare.healthcare.doctype.diagnostic_report.diagnostic_report.get_radiology_report_details",
		args: { diagnostic_report_name: frm.doc.name },
		callback: function (r) {
			if (!r.message) {
				frm.fields_dict.observation.$wrapper.html(
					`<div class="text-muted">${__("No radiology report data available.")}</div>`
				);
				return;
			}
			const rad = r.message;
			let html = build_radiology_html(rad);
			frm.fields_dict.observation.$wrapper.html(html);
		},
	});
};

/**
 * Build HTML for inline radiology report display.
 */
var build_radiology_html = function (rad) {
	const status_color = {
		Draft: "orange", Preliminary: "yellow", Final: "green",
		Amended: "blue", Cancelled: "red",
	};
	const badge = `<span class="indicator-pill ${status_color[rad.report_status] || "grey"}">${rad.report_status}</span>`;

	let html = `<div class="radiology-report-inline" style="font-size: 13px;">`;

	// Header
	html += `<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
		<div>
			<strong>${__("Radiology Report")}: </strong>
			<a href="/app/radiology-report/${encodeURIComponent(rad.report_name)}">${rad.report_name}</a>
			&nbsp;${badge}
		</div>
		<div class="text-muted" style="font-size: 11px;">
			${rad.report_datetime ? frappe.datetime.str_to_user(rad.report_datetime) : ""}
			${rad.signed_datetime ? " &middot; Signed: " + frappe.datetime.str_to_user(rad.signed_datetime) : ""}
		</div>
	</div>`;

	// Practitioners
	const practitioners = [];
	if (rad.reporting_radiologist) practitioners.push(`<strong>${__("Reporting")}:</strong> ${rad.reporting_radiologist}`);
	if (rad.reviewing_radiologist) practitioners.push(`<strong>${__("Reviewing")}:</strong> ${rad.reviewing_radiologist}`);
	if (practitioners.length) {
		html += `<div style="margin-bottom: 10px; color: var(--text-muted);">${practitioners.join(" &middot; ")}</div>`;
	}

	// Sections
	const sections = [
		{ label: __("Technique"), content: rad.technique },
		{ label: __("Comparison"), content: rad.comparison },
		{ label: __("Clinical Information"), content: rad.clinical_information },
	];
	for (const s of sections) {
		if (s.content) {
			html += `<div style="margin-bottom: 8px;">
				<div style="font-weight: 600; color: var(--heading-color); margin-bottom: 2px;">${s.label}</div>
				<div>${s.content}</div>
			</div>`;
		}
	}

	// Findings
	if (rad.findings && rad.findings.length) {
		html += `<div style="margin-bottom: 8px;">
			<div style="font-weight: 600; color: var(--heading-color); margin-bottom: 4px;">${__("Findings")}</div>`;
		for (const f of rad.findings) {
			const sig = f.significance ? ` <span class="indicator-pill red">${__("Significant")}</span>` : "";
			html += `<div style="margin-left: 12px; margin-bottom: 4px; padding: 4px 8px; border-left: 3px solid var(--border-color); background: var(--bg-color);">
				<strong>${f.title || f.type}</strong>${sig}
				${f.body_site ? ` &middot; ${f.body_site}` : ""}
				${f.laterality ? ` (${f.laterality})` : ""}
				${f.description ? `<div style="margin-top: 2px;">${f.description}</div>` : ""}
			</div>`;
		}
		html += `</div>`;
	}

	// Impression
	if (rad.impression) {
		html += `<div style="margin-bottom: 8px; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--subtle-accent);">
			<div style="font-weight: 700; color: var(--heading-color); margin-bottom: 4px;">${__("Impression")}</div>
			<div>${rad.impression}</div>
		</div>`;
	}

	// Conclusion
	if (rad.conclusion && rad.conclusion !== rad.impression) {
		html += `<div style="margin-bottom: 8px;">
			<div style="font-weight: 600; color: var(--heading-color); margin-bottom: 2px;">${__("Conclusion")}</div>
			<div>${rad.conclusion}</div>
		</div>`;
	}

	// Recommendations
	if (rad.recommendations) {
		html += `<div style="margin-bottom: 8px;">
			<div style="font-weight: 600; color: var(--heading-color); margin-bottom: 2px;">${__("Recommendations")}</div>
			<div>${rad.recommendations}</div>
		</div>`;
	}

	// Critical Result
	if (rad.critical_result) {
		html += `<div style="margin-bottom: 8px; padding: 8px; border: 2px solid var(--red-500); border-radius: 4px; background: var(--red-50);">
			<div style="font-weight: 700; color: var(--red-600);">${__("⚠ Critical Result")}</div>
			${rad.critical_result_communicated_to ? `<div>${__("Communicated to")}: ${rad.critical_result_communicated_to}</div>` : ""}
			${rad.critical_result_communicated_at ? `<div>${__("At")}: ${frappe.datetime.str_to_user(rad.critical_result_communicated_at)}</div>` : ""}
		</div>`;
	}

	// Addenda
	if (rad.addenda && rad.addenda.length) {
		html += `<div style="margin-bottom: 8px;">
			<div style="font-weight: 600; color: var(--heading-color); margin-bottom: 4px;">${__("Addenda")}</div>`;
		for (const a of rad.addenda) {
			html += `<div style="margin-left: 12px; margin-bottom: 4px; padding: 4px 8px; border-left: 3px solid var(--yellow-500); background: var(--yellow-50);">
				<strong>${a.type}</strong>
				${a.datetime ? ` &middot; ${frappe.datetime.str_to_user(a.datetime)}` : ""}
				${a.author ? ` &middot; ${a.author}` : ""}
				${a.reason ? ` &middot; <em>${a.reason}</em>` : ""}
				${a.text ? `<div style="margin-top: 2px;">${a.text}</div>` : ""}
			</div>`;
		}
		html += `</div>`;
	}

	html += `</div>`;
	return html;
};

var generate_pdf_with_print_format = function (frm) {
	const letterheads = get_letterhead_options();
	const dialog = new frappe.ui.Dialog({
		title: __("Print {0}", [frm.doc.name]),
		fields: [
			{
				fieldtype: "Select",
				label: __("Letter Head"),
				fieldname: "letter_sel",
				options: letterheads,
				default: letterheads[0],
			},
			{
				fieldtype: "Select",
				label: __("Print Format"),
				fieldname: "print_sel",
				options: frappe.meta.get_print_formats(frm.doc.doctype),
				default: frappe.get_meta(frm.doc.doctype).default_print_format,
			},
		],
	});

	dialog.set_primary_action(__("Print"), args => {
		if (!args) return;
		const default_print_format = frappe.get_meta(
			frm.doc.doctype,
		).default_print_format;
		const with_letterhead = args.letter_sel == __("No Letterhead") ? 0 : 1;
		const print_format = args.print_sel ? args.print_sel : default_print_format;
		const doc_names = JSON.stringify([frm.doc.name]);
		const letterhead = args.letter_sel;

		let pdf_options = JSON.stringify({
			"page-size": "A4",
			"margin-top": "60mm",
			"margin-bottom": "60mm",
			"margin-left": "0mm",
			"margin-right": "0mm",
		});

		if (letterhead == __("No Letterhead")) {
			pdf_options = JSON.stringify({
				"page-size": "A4",
				"margin-top": "5mm",
				"margin-bottom": "5mm",
				"margin-left": "0mm",
				"margin-right": "0mm",
			});
		}

		const w = window.open(
			"/api/method/frappe.utils.print_format.download_multi_pdf?" +
				"doctype=" +
				encodeURIComponent(frm.doc.doctype) +
				"&name=" +
				encodeURIComponent(doc_names) +
				"&format=" +
				encodeURIComponent(print_format) +
				"&no_letterhead=" +
				(with_letterhead ? "0" : "1") +
				"&letterhead=" +
				encodeURIComponent(letterhead) +
				"&options=" +
				encodeURIComponent(pdf_options),
		);

		if (!w) {
			frappe.msgprint(__("Please enable pop-ups"));
			return;
		}
	});

	dialog.show();
};

var get_letterhead_options = () => {
	const letterhead_options = [__("No Letterhead")];
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Letter Head",
			fields: ["name", "is_default"],
			filters: { disabled: 0 },
			limit_page_length: 0,
		},
		async: false,
		callback(r) {
			if (r.message) {
				r.message.forEach(letterhead => {
					letterhead_options.push(letterhead.name);
				});
			}
		},
	});
	return letterhead_options;
};
