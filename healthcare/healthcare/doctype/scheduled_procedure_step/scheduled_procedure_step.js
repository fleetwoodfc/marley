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
        
        // Show MWL sync status indicator (T038)
        if (frm.doc.modality) {
            setup_mwl_status_indicator(frm);
            
            // Add MWL sync buttons for SCHEDULED procedures (T037)
            if (frm.doc.ups_state === "SCHEDULED" || !frm.doc.ups_state) {
                // Show Sync to MWL button if not synced or has error
                if (frm.doc.mwl_sync_status !== "synced") {
                    frm.add_custom_button(__("Sync to MWL"), function() {
                        sync_to_mwl(frm);
                    }, __("MWL"));
                }
                
                // Show Remove from MWL button if synced
                if (frm.doc.mwl_sync_status === "synced") {
                    frm.add_custom_button(__("Remove from MWL"), function() {
                        remove_from_mwl(frm);
                    }, __("MWL"));
                }
            }
        }
        
        // Link to parent request
        if (frm.doc.imaging_service_request) {
            frm.add_custom_button(__("View Order"), function() {
                frappe.set_route("Form", "Imaging Service Request", frm.doc.imaging_service_request);
            });
        }
        
        // Display workflow steps from linked Procedure Type (T020-T022)
        if (frm.doc.procedure_type) {
            render_workflow_steps(frm);
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

// ==============================================================================
// MWL Sync Functions (T037, T038)
// ==============================================================================

function setup_mwl_status_indicator(frm) {
    // Show MWL sync status in intro
    if (frm.doc.mwl_sync_status === "error" && frm.doc.mwl_sync_error) {
        frm.dashboard.add_comment(__("MWL Sync Error: {0}", [frm.doc.mwl_sync_error]), "red", true);
    } else if (frm.doc.mwl_sync_status === "synced") {
        let sync_time = frm.doc.mwl_sync_at ? frappe.datetime.prettyDate(frm.doc.mwl_sync_at) : "";
        frm.dashboard.add_comment(__("Synced to Modality Worklist {0}", [sync_time]), "green", true);
    } else if (frm.doc.mwl_sync_status === "pending") {
        frm.dashboard.add_comment(__("MWL sync pending"), "orange", true);
    }
}

function sync_to_mwl(frm) {
    frappe.call({
        method: "healthcare.healthcare.dicom.mwl_sync.sync_sps_to_mwl",
        args: {
            procedure_step: frm.doc.name
        },
        freeze: true,
        freeze_message: __("Syncing to Modality Worklist..."),
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: r.message.message,
                    indicator: "green"
                });
                frm.reload_doc();
            } else if (r.message) {
                frappe.show_alert({
                    message: r.message.message,
                    indicator: "red"
                });
                frm.reload_doc();
            }
        }
    });
}

function remove_from_mwl(frm) {
    frappe.confirm(
        __("Remove this procedure from the Modality Worklist?"),
        function() {
            frappe.call({
                method: "healthcare.healthcare.dicom.mwl_sync.remove_sps_from_mwl",
                args: {
                    procedure_step: frm.doc.name
                },
                freeze: true,
                freeze_message: __("Removing from Modality Worklist..."),
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: "green"
                        });
                        frm.reload_doc();
                    } else if (r.message) {
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: "red"
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}

// ==============================================================================
// Workflow Steps Display (T020-T022)
// ==============================================================================

function render_workflow_steps(frm) {
    // Fetch workflow steps from the linked Procedure Type
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Procedure Type",
            name: frm.doc.procedure_type,
            fields: ["workflow_steps"]
        },
        callback: function(r) {
            if (r.message && r.message.workflow_steps && r.message.workflow_steps.length > 0) {
                const steps = r.message.workflow_steps;
                
                // Fetch full step details
                const step_names = steps.map(s => s.procedure_step_type).filter(n => n);
                if (step_names.length === 0) return;
                
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Procedure Step Type",
                        filters: { name: ["in", step_names] },
                        fields: ["step_name", "phase", "typical_duration", "required_role", "is_active"]
                    },
                    callback: function(r2) {
                        if (r2.message) {
                            const step_details = {};
                            r2.message.forEach(s => {
                                step_details[s.step_name] = s;
                            });
                            
                            // Build workflow HTML grouped by phase
                            const phases = ["Acquisition", "Post Processing", "Reporting"];
                            let html = `<div class="workflow-steps-section" style="margin-top: 15px;">
                                <h6 class="text-muted" style="cursor: pointer;" onclick="$(this).next('.workflow-steps-content').slideToggle();">
                                    <i class="fa fa-chevron-down"></i> Workflow Steps
                                </h6>
                                <div class="workflow-steps-content">`;
                            
                            phases.forEach(phase => {
                                const phase_steps = steps
                                    .filter(s => {
                                        const detail = step_details[s.procedure_step_type];
                                        return detail && detail.phase === phase;
                                    })
                                    .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
                                
                                if (phase_steps.length > 0) {
                                    html += `<div class="phase-group" style="margin-bottom: 10px;">
                                        <strong class="text-muted small">${phase}</strong>
                                        <table class="table table-sm table-bordered" style="margin-top: 5px; font-size: 12px;">
                                            <thead><tr>
                                                <th style="width: 40px;">#</th>
                                                <th>Step</th>
                                                <th style="width: 80px;">Duration</th>
                                                <th style="width: 120px;">Role</th>
                                            </tr></thead>
                                            <tbody>`;
                                    
                                    phase_steps.forEach(s => {
                                        const detail = step_details[s.procedure_step_type] || {};
                                        const inactive_class = detail.is_active ? "" : "text-muted";
                                        const inactive_badge = detail.is_active ? "" : " <span class='badge badge-secondary'>Inactive</span>";
                                        html += `<tr class="${inactive_class}">
                                            <td>${s.sequence || "-"}</td>
                                            <td>${s.procedure_step_type}${inactive_badge}</td>
                                            <td>${detail.typical_duration ? detail.typical_duration + " min" : "-"}</td>
                                            <td>${detail.required_role || "-"}</td>
                                        </tr>`;
                                    });
                                    
                                    html += `</tbody></table></div>`;
                                }
                            });
                            
                            html += `</div></div>`;
                            
                            // Add to form
                            $(frm.fields_dict.procedure_type.wrapper).after(html);
                        }
                    }
                });
            }
        }
    });
}
