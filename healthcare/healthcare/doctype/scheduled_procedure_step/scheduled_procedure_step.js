// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Scheduled Procedure Step", {
    refresh(frm) {
        // Display state indicator
        if (frm.doc.ups_state) {
            let indicator = get_state_indicator(frm.doc.ups_state);
            frm.page.set_indicator(frm.doc.ups_state, indicator);
        }
        
        // Add action buttons based on current state
        if (frm.doc.ups_state === "SCHEDULED") {
            frm.add_custom_button(__("Start Procedure"), function() {
                claim_procedure(frm);
            }).addClass("btn-primary");
            
            frm.add_custom_button(__("Cancel"), function() {
                cancel_procedure(frm);
            }, __("Actions"));
        }
        
        if (frm.doc.ups_state === "IN PROGRESS") {
            // Only show complete/cancel if user is the one who claimed
            if (frm.doc.claimed_by === frappe.session.user) {
                frm.add_custom_button(__("Complete Procedure"), function() {
                    complete_procedure(frm);
                }).addClass("btn-primary");
                
                frm.add_custom_button(__("Cancel Procedure"), function() {
                    cancel_procedure(frm);
                }, __("Actions"));
                
                frm.add_custom_button(__("Create Performed Step"), function() {
                    create_performed_step(frm);
                }, __("Actions"));
            } else {
                // Show request cancellation for other users
                frm.add_custom_button(__("Request Cancellation"), function() {
                    request_cancellation(frm);
                }, __("Actions"));
            }
        }
        
        // Show sync status
        if (frm.doc.ups_sync_status === "error" && frm.doc.ups_sync_error) {
            frm.set_intro(__("Sync Error: {0}", [frm.doc.ups_sync_error]), "red");
        } else if (frm.doc.ups_sync_status === "pending") {
            frm.set_intro(__("Pending sync with DICOM server"), "orange");
        }
        
        // Link to parent request
        if (frm.doc.imaging_service_request) {
            frm.add_custom_button(__("View Order"), function() {
                frappe.set_route("Form", "Imaging Service Request", frm.doc.imaging_service_request);
            });
        }
    }
});

function claim_procedure(frm) {
    frappe.confirm(
        __("Start this procedure? This will mark it as In Progress."),
        function() {
            frm.call({
                method: "claim",
                doc: frm.doc,
                freeze: true,
                freeze_message: __("Claiming procedure..."),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __("Procedure claimed. Transaction UID: {0}", [r.message.transaction_uid]),
                            indicator: "green"
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}

function complete_procedure(frm) {
    frappe.confirm(
        __("Complete this procedure?"),
        function() {
            frm.call({
                method: "complete",
                doc: frm.doc,
                args: {
                    transaction_uid: frm.doc.transaction_uid
                },
                freeze: true,
                freeze_message: __("Completing procedure..."),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __("Procedure completed"),
                            indicator: "green"
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}

function cancel_procedure(frm) {
    frappe.prompt([
        {
            label: __("Cancellation Reason"),
            fieldname: "reason",
            fieldtype: "Small Text",
            reqd: 1
        }
    ], function(values) {
        frm.call({
            method: "cancel_procedure",
            doc: frm.doc,
            args: {
                reason: values.reason,
                transaction_uid: frm.doc.transaction_uid
            },
            freeze: true,
            freeze_message: __("Canceling procedure..."),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: __("Procedure canceled"),
                        indicator: "orange"
                    });
                    frm.reload_doc();
                }
            }
        });
    }, __("Cancel Procedure"), __("Confirm Cancellation"));
}

function create_performed_step(frm) {
    frappe.new_doc("Performed Procedure Step", {
        scheduled_procedure_step: frm.doc.name,
        patient: frm.doc.patient
    });
}

function request_cancellation(frm) {
    frappe.prompt([
        {
            label: __("Reason for Cancellation Request"),
            fieldname: "reason",
            fieldtype: "Small Text",
            reqd: 1
        }
    ], function(values) {
        frappe.call({
            method: "frappe.client.insert",
            args: {
                doc: {
                    doctype: "Cancellation Request",
                    scheduled_procedure_step: frm.doc.name,
                    reason: values.reason
                }
            },
            freeze: true,
            callback: function(r) {
                if (r.message) {
                    frappe.show_alert({
                        message: __("Cancellation request submitted"),
                        indicator: "blue"
                    });
                }
            }
        });
    }, __("Request Cancellation"), __("Submit Request"));
}

function get_state_indicator(state) {
    const indicators = {
        "SCHEDULED": "blue",
        "IN PROGRESS": "yellow",
        "COMPLETED": "green",
        "CANCELED": "red"
    };
    return indicators[state] || "gray";
}
