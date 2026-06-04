// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Radiology Procedure", {
	refresh: function (frm) {
		frm.set_query("radiology_template", function () {
			return {
				filters: {
					disabled: 0,
				},
			};
		});

		frm.set_query("body_part", function () {
			return {
				filters: {},
			};
		});

		frm.set_query("practitioner", function () {
			return {
				filters: {
					status: "Active",
				},
			};
		});

		// Add Complete button for submitted procedures
		if (frm.doc.docstatus === 1 && frm.doc.status === "In Progress") {
			frm.add_custom_button(__("Complete"), function () {
				frappe.call({
					method: "complete_procedure",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Completing Procedure..."),
					callback: function (r) {
						if (r.message) {
							frappe.show_alert({
								message: __("Procedure marked as Completed"),
								indicator: "green",
							});
							frm.reload_doc();
						}
					},
				});
			}).addClass("btn-primary");
		}

		// Status indicator colors
		if (frm.doc.status) {
			let indicator = "";
			switch (frm.doc.status) {
				case "Scheduled":
					indicator = "blue";
					break;
				case "In Progress":
					indicator = "orange";
					break;
				case "Completed":
					indicator = "green";
					break;
				case "Cancelled":
					indicator = "red";
					break;
			}
			if (indicator) {
				frm.page.set_indicator(frm.doc.status, indicator);
			}
		}
	},

	radiology_template: function (frm) {
		if (frm.doc.radiology_template) {
			frappe.db.get_doc("Radiology Procedure Template", frm.doc.radiology_template).then(
				template => {
					frm.set_value("modality", template.modality);
					frm.set_value("body_part", template.body_part);
					frm.set_value("laterality", template.laterality);
					frm.set_value("contrast_used", template.contrast_required);
					frm.set_value("contrast_type", template.contrast_type);
					frm.set_value("medical_department", template.medical_department);
				}
			);
		}
	},

	patient: function (frm) {
		if (frm.doc.patient) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Patient",
					name: frm.doc.patient,
				},
				callback: function (r) {
					if (r.message) {
						frm.set_value("patient_name", r.message.patient_name);
						frm.set_value("patient_sex", r.message.sex);
						frm.set_value("inpatient_record", r.message.inpatient_record);
					}
				},
			});
		}
	},

	practitioner: function (frm) {
		if (frm.doc.practitioner) {
			frappe.db.get_value(
				"Healthcare Practitioner",
				frm.doc.practitioner,
				"practitioner_name",
				function (r) {
					if (r) {
						frm.set_value("practitioner_name", r.practitioner_name);
					}
				}
			);
		}
	},
});
