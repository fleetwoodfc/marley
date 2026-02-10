// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Performed Procedure Step", {
    refresh(frm) {
        // Set status indicator
        if (frm.doc.status) {
            let indicator = get_status_indicator(frm.doc.status);
            frm.page.set_indicator(frm.doc.status, indicator);
        }
        
        // Add action buttons based on status
        if (frm.doc.status === "In Progress") {
            frm.add_custom_button(__("Complete Procedure"), function() {
                complete_procedure(frm);
            }).addClass("btn-primary");
            
            frm.add_custom_button(__("Discontinue"), function() {
                discontinue_procedure(frm);
            }, __("Actions"));
        }
        
        // Link to scheduled step
        if (frm.doc.scheduled_procedure_step) {
            frm.add_custom_button(__("View Scheduled Step"), function() {
                frappe.set_route("Form", "Scheduled Procedure Step", frm.doc.scheduled_procedure_step);
            });
        }
        
        // Calculate and display duration
        if (frm.doc.start_datetime && frm.doc.end_datetime) {
            let duration = frappe.datetime.get_minute_diff(
                frm.doc.end_datetime,
                frm.doc.start_datetime
            );
            frm.dashboard.add_indicator(
                __("Duration: {0} minutes", [duration]),
                "blue"
            );
        }
    },
    
    scheduled_procedure_step(frm) {
        // Fetch patient from scheduled step
        if (frm.doc.scheduled_procedure_step) {
            frappe.db.get_value(
                "Scheduled Procedure Step",
                frm.doc.scheduled_procedure_step,
                ["patient", "ups_state"],
                function(r) {
                    if (r) {
                        frm.set_value("patient", r.patient);
                        
                        // Warn if SPS is not in correct state
                        if (r.ups_state !== "IN PROGRESS") {
                            frappe.msgprint({
                                title: __("Warning"),
                                message: __("Scheduled Procedure Step is in state {0}. " +
                                    "It should be IN PROGRESS to create a Performed Step.", 
                                    [r.ups_state]),
                                indicator: "orange"
                            });
                        }
                    }
                }
            );
        }
    },
    
    status(frm) {
        // Auto-set end datetime when completing
        if (frm.doc.status === "Completed" && !frm.doc.end_datetime) {
            frm.set_value("end_datetime", frappe.datetime.now_datetime());
        }
        
        // Show/hide discontinuation fields
        frm.toggle_reqd("discontinuation_reason", frm.doc.status === "Discontinued");
    },
    
    contrast_used(frm) {
        frm.toggle_reqd("contrast_agent", frm.doc.contrast_used);
    }
});

function complete_procedure(frm) {
    frappe.confirm(
        __("Mark this procedure as completed?"),
        function() {
            frm.set_value("status", "Completed");
            frm.set_value("end_datetime", frappe.datetime.now_datetime());
            frm.save().then(() => {
                frappe.show_alert({
                    message: __("Procedure completed"),
                    indicator: "green"
                });
            });
        }
    );
}

function discontinue_procedure(frm) {
    frappe.prompt([
        {
            label: __("Discontinuation Reason"),
            fieldname: "reason",
            fieldtype: "Small Text",
            reqd: 1
        }
    ], function(values) {
        frm.set_value("status", "Discontinued");
        frm.set_value("discontinuation_reason", values.reason);
        frm.set_value("end_datetime", frappe.datetime.now_datetime());
        frm.save().then(() => {
            frappe.show_alert({
                message: __("Procedure discontinued"),
                indicator: "orange"
            });
        });
    }, __("Discontinue Procedure"), __("Confirm"));
}

function get_status_indicator(status) {
    const indicators = {
        "In Progress": "yellow",
        "Completed": "green",
        "Discontinued": "red"
    };
    return indicators[status] || "gray";
}
