// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cancellation Request", {
    refresh(frm) {
        // Set page indicator based on status
        if (frm.doc.status === "Pending") {
            frm.page.set_indicator(__("Pending"), "orange");
        } else if (frm.doc.status === "Accepted") {
            frm.page.set_indicator(__("Accepted"), "green");
        } else if (frm.doc.status === "Declined") {
            frm.page.set_indicator(__("Declined"), "red");
        } else if (frm.doc.status === "Withdrawn") {
            frm.page.set_indicator(__("Withdrawn"), "gray");
        }
        
        // Add action buttons for pending requests
        if (!frm.is_new() && frm.doc.status === "Pending") {
            healthcare.cancellation_request.add_action_buttons(frm);
        }
        
        // Link to SPS
        if (frm.doc.scheduled_procedure_step) {
            frm.add_custom_button(__("View Procedure"), function() {
                frappe.set_route("Form", "Scheduled Procedure Step", frm.doc.scheduled_procedure_step);
            });
        }
    },
    
    scheduled_procedure_step(frm) {
        // Fetch patient info when SPS is selected
        if (frm.doc.scheduled_procedure_step) {
            frappe.db.get_doc("Scheduled Procedure Step", frm.doc.scheduled_procedure_step)
                .then(sps => {
                    frm.set_value("patient", sps.patient);
                    frm.set_value("patient_name", sps.patient_name);
                });
        }
    }
});

// Cancellation Request helpers
frappe.provide("healthcare.cancellation_request");

$.extend(healthcare.cancellation_request, {
    /**
     * Add accept/decline/withdraw buttons
     */
    add_action_buttons(frm) {
        const is_requester = frm.doc.requester === frappe.session.user;
        
        if (is_requester) {
            // Requester can withdraw
            frm.add_custom_button(__("Withdraw Request"), function() {
                frappe.confirm(
                    __("Are you sure you want to withdraw this cancellation request?"),
                    function() {
                        frappe.call({
                            method: "healthcare.healthcare.doctype.cancellation_request.cancellation_request.withdraw_cancellation",
                            args: { name: frm.doc.name },
                            callback(r) {
                                if (!r.exc) {
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("Actions"));
        } else {
            // Operator can accept or decline
            frm.add_custom_button(__("Accept"), function() {
                healthcare.cancellation_request.show_accept_dialog(frm);
            }, __("Decision")).addClass("btn-success");
            
            frm.add_custom_button(__("Decline"), function() {
                healthcare.cancellation_request.show_decline_dialog(frm);
            }, __("Decision")).addClass("btn-danger");
        }
    },
    
    /**
     * Show dialog to accept cancellation
     */
    show_accept_dialog(frm) {
        const d = new frappe.ui.Dialog({
            title: __("Accept Cancellation Request"),
            fields: [
                {
                    fieldname: "info",
                    fieldtype: "HTML",
                    options: `<p>${__("This will cancel the procedure and notify the requester.")}</p>
                        <p class="text-warning"><strong>${__("This action cannot be undone.")}</strong></p>`
                },
                {
                    fieldname: "decision_reason",
                    fieldtype: "Small Text",
                    label: __("Notes (optional)"),
                }
            ],
            primary_action_label: __("Accept & Cancel Procedure"),
            primary_action(values) {
                frappe.call({
                    method: "healthcare.healthcare.doctype.cancellation_request.cancellation_request.accept_cancellation",
                    args: {
                        name: frm.doc.name,
                        decision_reason: values.decision_reason
                    },
                    callback(r) {
                        if (!r.exc) {
                            d.hide();
                            frm.reload_doc();
                        }
                    }
                });
            }
        });
        d.show();
    },
    
    /**
     * Show dialog to decline cancellation
     */
    show_decline_dialog(frm) {
        const d = new frappe.ui.Dialog({
            title: __("Decline Cancellation Request"),
            fields: [
                {
                    fieldname: "info",
                    fieldtype: "HTML",
                    options: `<p>${__("Please provide a reason for declining this request.")}</p>`
                },
                {
                    fieldname: "decision_reason",
                    fieldtype: "Small Text",
                    label: __("Reason for Declining"),
                    reqd: 1
                }
            ],
            primary_action_label: __("Decline Request"),
            primary_action(values) {
                frappe.call({
                    method: "healthcare.healthcare.doctype.cancellation_request.cancellation_request.decline_cancellation",
                    args: {
                        name: frm.doc.name,
                        decision_reason: values.decision_reason
                    },
                    callback(r) {
                        if (!r.exc) {
                            d.hide();
                            frm.reload_doc();
                        }
                    }
                });
            }
        });
        d.show();
    }
});
