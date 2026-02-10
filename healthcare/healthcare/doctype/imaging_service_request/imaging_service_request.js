// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Imaging Service Request", {
    refresh(frm) {
        // Set patient query to only show active patients
        frm.set_query("patient", function() {
            return {
                filters: {
                    status: "Active"
                }
            };
        });
        
        // Add Submit button for new requests
        if (frm.doc.docstatus === 0 && !frm.is_new()) {
            frm.add_custom_button(__("Submit Order"), function() {
                frm.save("Submit");
            }).addClass("btn-primary");
        }
        
        // Show linked Scheduled Procedure Steps
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__("View Worklist"), function() {
                frappe.set_route("List", "Scheduled Procedure Step", {
                    imaging_service_request: frm.doc.name
                });
            });
        }
        
        // Display status indicator
        if (frm.doc.status) {
            let indicator = get_status_indicator(frm.doc.status);
            frm.page.set_indicator(frm.doc.status, indicator);
        }
    },
    
    patient(frm) {
        // Fetch patient details when patient is selected
        if (frm.doc.patient) {
            frappe.db.get_doc("Patient", frm.doc.patient).then(patient => {
                frm.set_value("patient_name", patient.patient_name);
                frm.set_value("patient_sex", patient.sex);
                
                // Calculate age
                if (patient.dob) {
                    let dob = frappe.datetime.str_to_obj(patient.dob);
                    let today = new Date();
                    let age = today.getFullYear() - dob.getFullYear();
                    let m = today.getMonth() - dob.getMonth();
                    if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) {
                        age--;
                    }
                    frm.set_value("patient_age", age + " Years");
                }
            });
        }
    },
    
    priority(frm) {
        // Visual feedback for STAT priority
        if (frm.doc.priority === "STAT") {
            frm.set_intro(__("⚠️ STAT Priority - Requires immediate attention"), "red");
        } else {
            frm.set_intro("");
        }
    }
});

frappe.ui.form.on("Requested Procedure", {
    procedure_type(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.procedure_type) {
            frappe.db.get_doc("Procedure Type", row.procedure_type).then(pt => {
                frappe.model.set_value(cdt, cdn, "procedure_description", pt.procedure_name);
                frappe.model.set_value(cdt, cdn, "modality", pt.default_modality);
            });
        }
    }
});

function get_status_indicator(status) {
    const indicators = {
        "Draft": "orange",
        "Ordered": "blue",
        "In Progress": "yellow",
        "Completed": "green",
        "Cancelled": "red"
    };
    return indicators[status] || "gray";
}
