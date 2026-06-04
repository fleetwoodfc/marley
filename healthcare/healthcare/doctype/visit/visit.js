// Copyright (c) 2026, Healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Visit", {
	refresh: function(frm) {
		frm.set_query("patient", function() {
			return {
				filters: {
					status: "Active"
				}
			};
		});

		frm.set_query("service_unit", function() {
			return {
				filters: {
					is_group: 0,
					company: frm.doc.company
				}
			};
		});

		frm.set_query("primary_practitioner", function() {
			return {
				filters: {
					status: "Active"
				}
			};
		});

		// Add action buttons based on status
		if (!frm.is_new()) {
			add_action_buttons(frm);
		}

		// Set up dashboard
		if (!frm.is_new()) {
			frm.add_custom_button(__("View Summary"), function() {
				frm.call("get_visit_summary").then(r => {
					if (r.message) {
						show_visit_summary(frm, r.message);
					}
				});
			});
		}
	},

	patient: function(frm) {
		if (frm.doc.patient) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Patient",
					name: frm.doc.patient
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value("patient_name", r.message.patient_name);
						frm.set_value("patient_sex", r.message.sex);
						if (r.message.inpatient_record) {
							frm.set_value("inpatient_record", r.message.inpatient_record);
						}
						// Set default insurance if patient has one
						if (r.message.insurance_policy) {
							frm.set_value("insurance_policy", r.message.insurance_policy);
						}
					}
				}
			});
		}
	},

	visit_date: function(frm) {
		// Check for existing visit on same date
		if (frm.doc.patient && frm.doc.visit_date && frm.is_new()) {
			frappe.call({
				method: "healthcare.healthcare.doctype.visit.visit.get_visit_for_patient",
				args: {
					patient: frm.doc.patient,
					visit_date: frm.doc.visit_date
				},
				callback: function(r) {
					if (r.message) {
						frappe.confirm(
							__("A visit already exists for this patient on {0}. Do you want to open it instead?", [frm.doc.visit_date]),
							function() {
								frappe.set_route("Form", "Visit", r.message.name);
							}
						);
					}
				}
			});
		}
	},

	arrival_time: function(frm) {
		calculate_duration(frm);
		if (frm.doc.arrival_time && frm.doc.status === "Scheduled") {
			frm.set_value("status", "Arrived");
		}
	},

	departure_time: function(frm) {
		calculate_duration(frm);
		if (frm.doc.departure_time && !["Completed", "Cancelled"].includes(frm.doc.status)) {
			frm.set_value("status", "Completed");
		}
	}
});

function add_action_buttons(frm) {
	// Check In button
	if (frm.doc.status === "Scheduled") {
		frm.add_custom_button(__("Check In"), function() {
			frm.call("check_in").then(() => {
				frm.reload_doc();
			});
		}, __("Actions"));

		frm.add_custom_button(__("Mark No Show"), function() {
			frappe.confirm(__("Mark this visit as No Show?"), function() {
				frm.call("mark_no_show").then(() => {
					frm.reload_doc();
				});
			});
		}, __("Actions"));
	}

	// Start Visit button
	if (["Scheduled", "Arrived"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Start Visit"), function() {
			frm.call("start_visit").then(() => {
				frm.reload_doc();
			});
		}, __("Actions"));
	}

	// Check Out button
	if (["Arrived", "In Progress"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Check Out"), function() {
			frm.call("check_out").then(() => {
				frm.reload_doc();
			});
		}, __("Actions"));
	}

	// Cancel button
	if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Cancel Visit"), function() {
			frappe.confirm(__("Cancel this visit?"), function() {
				frm.call("cancel_visit").then(() => {
					frm.reload_doc();
				});
			});
		}, __("Actions"));
	}

	// Create documents buttons
	if (!["Completed", "Cancelled", "No Show"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Patient Encounter"), function() {
			frm.call("create_encounter").then(r => {
				if (r.message) {
					frappe.model.sync(r.message);
					frappe.set_route("Form", "Patient Encounter", r.message.name);
				}
			});
		}, __("Create"));

		frm.add_custom_button(__("Patient Appointment"), function() {
			frm.call("create_appointment").then(r => {
				if (r.message) {
					frappe.model.sync(r.message);
					frappe.set_route("Form", "Patient Appointment", r.message.name);
				}
			});
		}, __("Create"));
	}
}

function calculate_duration(frm) {
	if (frm.doc.arrival_time && frm.doc.departure_time) {
		let arrival = moment(frm.doc.arrival_time, "HH:mm:ss");
		let departure = moment(frm.doc.departure_time, "HH:mm:ss");
		if (departure.isAfter(arrival)) {
			let duration_seconds = departure.diff(arrival, 'seconds');
			frm.set_value("visit_duration", duration_seconds);
		}
	}
}

function show_visit_summary(frm, summary) {
	let html = `<div class="visit-summary">`;
	
	// Appointments section
	html += `<h5>${__("Appointments")} (${summary.appointments.length})</h5>`;
	if (summary.appointments.length > 0) {
		html += `<ul>`;
		summary.appointments.forEach(a => {
			html += `<li><a href="/app/patient-appointment/${a.name}">${a.name}</a> - ${a.practitioner || "No Practitioner"} (${a.status})</li>`;
		});
		html += `</ul>`;
	} else {
		html += `<p class="text-muted">${__("No appointments")}</p>`;
	}

	// Encounters section
	html += `<h5>${__("Encounters")} (${summary.encounters.length})</h5>`;
	if (summary.encounters.length > 0) {
		html += `<ul>`;
		summary.encounters.forEach(e => {
			html += `<li><a href="/app/patient-encounter/${e.name}">${e.name}</a> - ${e.practitioner || "No Practitioner"}</li>`;
		});
		html += `</ul>`;
	} else {
		html += `<p class="text-muted">${__("No encounters")}</p>`;
	}

	// Service Requests section
	html += `<h5>${__("Service Requests")} (${summary.service_requests.length})</h5>`;
	if (summary.service_requests.length > 0) {
		html += `<ul>`;
		summary.service_requests.forEach(sr => {
			html += `<li><a href="/app/service-request/${sr.name}">${sr.name}</a> - ${sr.template || "N/A"} (${sr.status})</li>`;
		});
		html += `</ul>`;
	} else {
		html += `<p class="text-muted">${__("No service requests")}</p>`;
	}

	html += `</div>`;

	frappe.msgprint({
		title: __("Visit Summary"),
		message: html,
		wide: true
	});
}
