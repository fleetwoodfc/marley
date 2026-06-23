// Copyright (c) 2020, earthians and contributors
// For license information, please see license.txt

{% include "healthcare/healthcare/service_request.js" %}

frappe.ui.form.on("Service Request", {
	refresh: function (frm) {
		if (
			!frm.is_new() &&
			!frm.doc.insurance_policy &&
			frm.doc.billing_status == "Pending"
		) {
			frm.add_custom_button(__("Create Insurance Coverage"), function () {
				var d = new frappe.ui.Dialog({
					title: __("Select Insurance Policy"),
					fields: [
						{
							fieldname: "Patient Insurance Policy",
							fieldtype: "Link",
							label: __("Patient Insurance Policy"),
							options: "Patient Insurance Policy",
							get_query: function () {
								return {
									filters: {
										patient: frm.doc.patient,
										docstatus: 1,
									},
								};
							},
							reqd: 1,
						},
					],
				});
				d.set_primary_action(__("Create"), function () {
					d.hide();
					var data = d.get_values();
					frm.set_value("insurance_policy", data["Patient Insurance Policy"]);
					frm.save("Update");
				});
				d.show();
			});
		}

		frm.set_query("template_dt", function () {
			let order_template_doctypes = [
				"Therapy Type",
				"Lab Test Template",
				"Clinical Procedure Template",
				"Appointment Type",
				"Observation Template",
				"Healthcare Activity",
			];
			return {
				filters: {
					name: ["in", order_template_doctypes],
				},
			};
		});
		frm.set_df_property("template_dt", "only_select", true);

		frm.set_query("status", function () {
			return {
				filters: {
					code_system: "Request Status",
				},
			};
		});

		frm.set_query("insurance_policy", function () {
			return {
				filters: {
					patient: frm.doc.patient,
					docstatus: 1,
				},
			};
		});

		frm.trigger("setup_create_buttons");
	},

	setup_create_buttons: function (frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status === "Completed") return;

		if (frm.doc.template_dt === "Clinical Procedure Template") {
			frm.add_custom_button(
				__("Clinical Procedure"),
				function () {
					frappe.db
						.get_list("Clinical Procedure", {
							filters: {
								service_request: frm.doc.name,
								docstatus: ["!=", 2],
								procedure_template: frm.doc.template_dn,
							},
							fields: ["name"],
						})
						.then(response => {
							if (response.length == frm.doc.quantity) {
								frappe.set_route("List", "Clinical Procedure", {
									service_request: frm.doc.name,
								});
							} else {
								frappe.db
									.get_value(
										"Clinical Procedure",
										{ service_request: frm.doc.name, docstatus: 0 },
										"name",
									)
									.then(r => {
										if (Object.keys(r.message).length == 0) {
											frm.trigger("make_clinical_procedure");
										} else {
											if (r.message && r.message.name) {
												frappe.set_route(
													"Form",
													"Clinical Procedure",
													r.message.name,
												);
												frappe.show_alert({
													message: __(
														`Clinical Procedure is already created`,
													),
													indicator: "info",
												});
											}
										}
									});
							}
						});
				},
				__("Create"),
			);
		} else if (frm.doc.template_dt === "Lab Test Template") {
			frm.add_custom_button(
				__("Lab Test"),
				function () {
					frappe.db
						.get_value(
							"Lab Test",
							{ service_request: frm.doc.name, docstatus: ["!=", 2] },
							"name",
						)
						.then(r => {
							if (Object.keys(r.message).length == 0) {
								frm.trigger("make_lab_test");
							} else {
								if (r.message && r.message.name) {
									frappe.set_route(
										"Form",
										"Lab Test",
										r.message.name,
									);
									frappe.show_alert({
										message: __(`Lab Test is already created`),
										indicator: "info",
									});
								}
							}
						});
				},
				__("Create"),
			);
		} else if (frm.doc.template_dt === "Therapy Type") {
			frm.add_custom_button(
				__("Therapy Session"),
				function () {
					frappe.db
						.get_list("Therapy Session", {
							filters: {
								service_request: frm.doc.name,
								docstatus: ["!=", 2],
								therapy_type: frm.doc.template_dn,
							},
							fields: ["name"],
						})
						.then(response => {
							if (response.length == frm.doc.quantity) {
								frappe.set_route("List", "Therapy Session", {
									service_request: frm.doc.name,
								});
							} else {
								frappe.db
									.get_value(
										"Therapy Session",
										{ service_request: frm.doc.name, docstatus: 0 },
										"name",
									)
									.then(r => {
										if (Object.keys(r.message).length == 0) {
											frm.trigger("make_therapy_session");
										} else {
											if (r.message && r.message.name) {
												frappe.set_route(
													"Form",
													"Therapy Session",
													r.message.name,
												);
												frappe.show_alert({
													message: __(
														`Therapy Session is already created`,
													),
													indicator: "info",
												});
											}
										}
									});
							}
						});
				},
				__("Create"),
			);
		} else if (frm.doc.template_dt === "Observation Template") {
			frm.add_custom_button(
				__("Observation"),
				function () {
					frm.trigger("make_observation");
				},
				__("Create"),
			);
		} else if (frm.doc.template_dt === "Appointment Type") {
			frm.add_custom_button(
				__("Appointment"),
				function () {
					frappe.db
						.get_value(
							"Patient Appointment",
							{
								service_request: frm.doc.name,
								status: ["!=", "Cancelled"],
							},
							"name",
						)
						.then(r => {
							if (Object.keys(r.message).length == 0) {
								frappe.model.open_mapped_doc({
									method: "healthcare.healthcare.doctype.service_request.service_request.make_appointment",
									frm: frm,
								});
							} else {
								if (r.message && r.message.name) {
									frappe.set_route(
										"Form",
										"Patient Appointment",
										r.message.name,
									);
									frappe.show_alert({
										message: __(
											"Patient Appointment is already created",
										),
										indicator: "info",
									});
								}
							}
						});
				},
				__("Create"),
			);
		}

		frm.page.set_inner_btn_group_as_primary(__("Create"));
	},

	make_clinical_procedure: function (frm) {
		frappe.call({
			method: "healthcare.healthcare.doctype.service_request.service_request.make_clinical_procedure",
			args: { service_request: frm.doc.name },
			freeze: true,
			callback: function (r) {
				var doclist = frappe.model.sync(r.message);
				frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
			},
		});
	},

	make_lab_test: function (frm) {
		frappe.call({
			method: "healthcare.healthcare.doctype.service_request.service_request.make_lab_test",
			args: { service_request: frm.doc.name },
			freeze: true,
			callback: function (r) {
				var doclist = frappe.model.sync(r.message);
				frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
			},
		});
	},

	make_therapy_session: function (frm) {
		frappe.call({
			method: "healthcare.healthcare.doctype.therapy_plan.therapy_plan.make_therapy_session",
			args: {
				patient: frm.doc.patient,
				therapy_type: frm.doc.template_dn,
				company: frm.doc.company,
				service_request: frm.doc.name,
			},
			freeze: true,
			callback: function (r) {
				var doclist = frappe.model.sync(r.message);
				frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
			},
		});
	},

	make_observation: function (frm) {
		frappe.call({
			method: "healthcare.healthcare.doctype.service_request.service_request.make_observation",
			args: { service_request: frm.doc.name },
			freeze: true,
			callback: function (r) {
				if (r.message) {
					var title = "";
					var indicator = "info";
					if (r.message[2]) {
						title = `${r.message[0]} is already created`;
					} else {
						title = `${r.message[0]} is created`;
						indicator = "green";
					}
					frappe.show_alert({
						message: __("{0}", [title]),
						indicator: indicator,
					});
					frappe.set_route("Form", r.message[1], r.message[0]);
				}
			},
		});
	},
});
// ── CIEL Medical Code Picker ──────────────────────────────────────────────────
// Adds an "Add Medical Code" button to the codification_table grid toolbar.
// Searches the local Terminology Concept DocType (populated by ciel_sync.py)
// and inserts multiple coding rows at once (CIEL + LOINC + SNOMED + ICD-10).
// Requires: ciel_sync.py to have run at least once with an OCL API key.
// ─────────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Service Request", {
	refresh(frm) {
		if (!frm.fields_dict.codification_table) return;

		frm.fields_dict.codification_table.grid.add_custom_button(
			__("Add Medical Code"),
			() => _ciel_open_picker(frm),
		);
	},
});

function _ciel_system_badge(system) {
	const labels = {
		"https://openconceptlab.org/orgs/CIEL/sources/CIEL/": "CIEL",
		"http://loinc.org": "LOINC",
		"http://snomed.info/sct": "SNOMED",
		"http://hl7.org/fhir/sid/icd-10-cm": "ICD-10",
		"http://hl7.org/fhir/sid/icd-10": "ICD-10",
		"http://www.nlm.nih.gov/research/umls/rxnorm": "RxNORM",
	};
	const label = labels[system] || system.split("/").pop();
	return `<span class="badge badge-secondary badge-pill" style="font-size:10px;margin-right:3px">${label}</span>`;
}

function _ciel_insert_concept(frm, concept) {
	const existing = (frm.doc.codification_table || []).map(
		(r) => `${r.system}::${r.code}`,
	);
	let inserted = 0;
	let skipped = 0;

	(concept.codings || []).forEach((row) => {
		const key = `${row.system}::${row.code}`;
		if (existing.includes(key)) {
			skipped++;
			return;
		}
		frm.add_child("codification_table", {
			system: row.system,
			code: row.code,
			display: row.display,
		});
		inserted++;
	});

	frm.refresh_field("codification_table");

	const systemNames = (concept.codings || [])
		.map((r) => {
			const m = {
				"http://loinc.org": "LOINC",
				"http://snomed.info/sct": "SNOMED CT",
				"http://hl7.org/fhir/sid/icd-10-cm": "ICD-10",
				"https://openconceptlab.org/orgs/CIEL/sources/CIEL/": "CIEL",
			};
			return m[r.system] || r.system.split("/").pop();
		})
		.filter((v, i, a) => a.indexOf(v) === i)
		.join(", ");

	if (inserted > 0) {
		const msg =
			skipped > 0
				? __(
						"{0} code{1} inserted ({2}). {3} already present.",
						[inserted, inserted !== 1 ? "s" : "", systemNames, skipped],
					)
				: __("{0} code{1} inserted: {2}", [
						inserted,
						inserted !== 1 ? "s" : "",
						systemNames,
					]);
		frappe.show_alert({ message: msg, indicator: "green" }, 5);
	} else {
		frappe.show_alert(
			{ message: __("All codes already present."), indicator: "orange" },
			3,
		);
	}
}

function _ciel_render_results(d, results, term) {
	if (!results || results.length === 0) {
		const count = frappe.db.get_list
			? null
			: null; // placeholder for sync-not-run detection
		const msg =
			term.length < 3
				? __("Type at least 3 characters to search")
				: __(
						"No concepts found for \"{0}\". Try a broader term.",
						[term],
					);
		d.fields_dict.results_html.$wrapper.html(
			`<p class="text-muted small mt-2" style="padding:8px 10px">${msg}</p>`,
		);
		return;
	}

	let selectedIdx = 0;

	const rows = results
		.map((c, i) => {
			const badges = (c.codings || []).map((r) => _ciel_system_badge(r.system)).join("");
			const insertLabel = __("Insert {0} code{1}", [
				c.codings.length,
				c.codings.length !== 1 ? "s" : "",
			]);
			return `
			<div class="ciel-result-row" data-idx="${i}"
				style="display:flex;justify-content:space-between;align-items:center;
					padding:8px 10px;border-bottom:1px solid var(--border-color);
					cursor:pointer;min-height:44px;"
				tabindex="0" role="option" aria-selected="${i === 0}">
				<div>
					<div style="font-weight:500;font-size:13px">${frappe.utils.escape_html(c.display_name)}</div>
					<div style="margin-top:3px">${badges}</div>
				</div>
				<button class="btn btn-xs btn-default ciel-insert-btn"
					style="min-width:44px;min-height:44px;white-space:nowrap"
					title="${insertLabel}">
					+${c.codings.length}
				</button>
			</div>`;
		})
		.join("");

	d.fields_dict.results_html.$wrapper.html(`
		<div role="listbox" aria-label="${__("CIEL Concept Results")}">
			<div class="text-muted small" style="padding:6px 10px">
				${__("Showing {0} result{1}", [results.length, results.length !== 1 ? "s" : ""])}
			</div>
			${rows}
		</div>
	`);

	// Click handler
	d.fields_dict.results_html.$wrapper.find(".ciel-insert-btn").on("click", function (e) {
		e.stopPropagation();
		const idx = $(this).closest(".ciel-result-row").data("idx");
		_ciel_insert_concept(d._frm, results[idx]);
	});

	// Row click
	d.fields_dict.results_html.$wrapper.find(".ciel-result-row").on("click", function (e) {
		if ($(e.target).hasClass("ciel-insert-btn")) return;
		const idx = $(this).data("idx");
		_ciel_insert_concept(d._frm, results[idx]);
	});

	// Keyboard nav: arrows + Enter
	d.fields_dict.results_html.$wrapper.find(".ciel-result-row").on("keydown", function (e) {
		const rowEls = d.fields_dict.results_html.$wrapper.find(".ciel-result-row");
		if (e.key === "ArrowDown") {
			selectedIdx = Math.min(selectedIdx + 1, rowEls.length - 1);
			rowEls.eq(selectedIdx).focus();
		} else if (e.key === "ArrowUp") {
			selectedIdx = Math.max(selectedIdx - 1, 0);
			rowEls.eq(selectedIdx).focus();
		} else if (e.key === "Enter") {
			_ciel_insert_concept(d._frm, results[selectedIdx]);
		}
	});
}

function _ciel_open_picker(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Add Medical Code"),
		fields: [
			{
				fieldtype: "Data",
				fieldname: "term",
				label: __("Search terminology"),
				description: __("Type at least 3 characters to search CIEL concepts"),
			},
			{
				fieldtype: "HTML",
				fieldname: "results_html",
			},
		],
		primary_action_label: __("Close"),
		primary_action() {
			d.hide();
		},
	});

	d._frm = frm;

	d.fields_dict.results_html.$wrapper.html(
		`<p class="text-muted small mt-2" style="padding:8px 10px">${__("Type at least 3 characters to search")}</p>`,
	);

	d.fields_dict.term.$input.on(
		"input",
		frappe.utils.debounce(function () {
			const term = d.get_value("term");
			if (!term || term.length < 3) {
				d.fields_dict.results_html.$wrapper.html(
					`<p class="text-muted small mt-2" style="padding:8px 10px">${__("Type at least 3 characters to search")}</p>`,
				);
				return;
			}

			// Loading state
			d.fields_dict.results_html.$wrapper.html(
				`<div class="text-center mt-3"><div class="spinner-border spinner-border-sm" role="status"></div></div>`,
			);

			frappe.call({
				method: "healthcare.healthcare.api.ciel_sync.search_ciel_concepts",
				args: { term, limit: 20 },
				callback({ message }) {
					if (!message || message.length === 0) {
						// Detect if sync has never run (0 local concepts)
						frappe.call({
							method: "frappe.client.get_count",
							args: { doctype: "Terminology Concept" },
							callback({ message: count }) {
								const emptyMsg =
									count === 0
										? __(
												"Medical code library not loaded yet. Ask your admin to run the CIEL sync (DCM4CHEE Settings → trigger_ciel_sync).",
											)
										: __(
												"No concepts found for \"{0}\". Try a broader term.",
												[term],
											);
								d.fields_dict.results_html.$wrapper.html(
									`<p class="text-muted small mt-2" style="padding:8px 10px">${emptyMsg}</p>`,
								);
							},
						});
						return;
					}
					_ciel_render_results(d, message, term);
				},
			});
		}, 300),
	);

	d.show();
	// Autofocus search field on open
	setTimeout(() => d.fields_dict.term && d.fields_dict.term.$input.focus(), 100);
}