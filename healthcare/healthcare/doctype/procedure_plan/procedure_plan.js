// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Procedure Plan", {
    refresh(frm) {
        // Show indicator for default plan
        if (frm.doc.is_default) {
            frm.page.set_indicator(__("Default Plan"), "green");
        }
        
        // Add actions if not new
        if (!frm.is_new()) {
            // Set as default button
            if (!frm.doc.is_default) {
                frm.add_custom_button(__("Set as Default"), function() {
                    frm.set_value("is_default", 1);
                    frm.save().then(() => {
                        frappe.show_alert({
                            message: __("This plan is now the default for {0}", [frm.doc.procedure_type]),
                            indicator: "green"
                        });
                    });
                }, __("Actions"));
            }
            
            // Duplicate plan button
            frm.add_custom_button(__("Duplicate Plan"), function() {
                healthcare.procedure_plan.duplicate_plan(frm);
            }, __("Actions"));
            
            // Preview what SPS will be created
            frm.add_custom_button(__("Preview SPS"), function() {
                healthcare.procedure_plan.preview_sps(frm);
            }, __("Actions"));
        }
        
        // Setup queries
        healthcare.procedure_plan.setup_queries(frm);
    },
    
    procedure_type(frm) {
        // When procedure type changes, optionally copy codes
        if (frm.doc.procedure_type && !frm.doc.plan_items?.length) {
            frappe.confirm(
                __("Would you like to copy protocol codes from the Procedure Type?"),
                function() {
                    healthcare.procedure_plan.copy_protocol_codes_from_type(frm);
                }
            );
        }
    },
    
    is_default(frm) {
        // Warn if setting as default
        if (frm.doc.is_default && !frm.doc.__islocal) {
            frappe.show_alert({
                message: __("This will be the default plan for {0}. Any previous default will be unset.", [frm.doc.procedure_type]),
                indicator: "orange"
            }, 5);
        }
    }
});

// Plan Item child table events
frappe.ui.form.on("Procedure Plan Item", {
    protocol_codes_add(frm, cdt, cdn) {
        // Set default values for new protocol code items
        const row = frappe.get_doc(cdt, cdn);
        if (!row.sequence) {
            row.sequence = frm.doc.plan_items?.length || 1;
        }
    },
    
    form_render(frm, cdt, cdn) {
        // Custom rendering for plan items
    }
});

// Procedure Plan helpers
frappe.provide("healthcare.procedure_plan");

$.extend(healthcare.procedure_plan, {
    /**
     * Setup queries for link fields
     */
    setup_queries(frm) {
        // Filter plan items by modality if procedure type has modality
        frm.set_query("code_value", "plan_items", function(doc, cdt, cdn) {
            return {
                filters: {}
            };
        });
    },
    
    /**
     * Copy protocol codes from Procedure Type
     */
    copy_protocol_codes_from_type(frm) {
        if (!frm.doc.procedure_type) return;
        
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Procedure Type",
                name: frm.doc.procedure_type
            },
            callback(r) {
                if (r.message && r.message.procedure_codes) {
                    // Clear existing items
                    frm.clear_table("plan_items");
                    
                    // Add each code as a plan item
                    r.message.procedure_codes.forEach((code, idx) => {
                        frm.add_child("plan_items", {
                            code_value: code.code_value,
                            sequence: idx + 1
                        });
                    });
                    
                    frm.refresh_field("plan_items");
                    frappe.show_alert({
                        message: __("Copied {0} protocol codes from Procedure Type", [r.message.procedure_codes.length]),
                        indicator: "green"
                    });
                }
            }
        });
    },
    
    /**
     * Duplicate the current plan
     */
    duplicate_plan(frm) {
        frappe.prompt([
            {
                fieldname: "plan_name",
                fieldtype: "Data",
                label: __("New Plan Name"),
                reqd: 1,
                default: frm.doc.plan_name + " (Copy)"
            }
        ], function(values) {
            frappe.call({
                method: "frappe.client.insert",
                args: {
                    doc: {
                        doctype: "Procedure Plan",
                        procedure_type: frm.doc.procedure_type,
                        plan_name: values.plan_name,
                        is_default: 0,
                        plan_items: frm.doc.plan_items?.map(item => ({
                            code_value: item.code_value,
                            sequence: item.sequence,
                            expected_duration: item.expected_duration,
                            notes: item.notes
                        })) || []
                    }
                },
                callback(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __("Plan duplicated successfully"),
                            indicator: "green"
                        });
                        frappe.set_route("Form", "Procedure Plan", r.message.name);
                    }
                }
            });
        }, __("Duplicate Plan"), __("Create"));
    },
    
    /**
     * Preview what SPS would be created from this plan
     */
    preview_sps(frm) {
        let html = `<div class="procedure-plan-preview">
            <h5>${__("This plan will create the following Scheduled Procedure Step(s):")}</h5>
            <table class="table table-bordered">
                <thead>
                    <tr>
                        <th>${__("Sequence")}</th>
                        <th>${__("Protocol Code")}</th>
                        <th>${__("Expected Duration")}</th>
                    </tr>
                </thead>
                <tbody>`;
        
        if (frm.doc.plan_items && frm.doc.plan_items.length > 0) {
            frm.doc.plan_items.forEach(item => {
                html += `<tr>
                    <td>${item.sequence || "-"}</td>
                    <td>${item.code_value || "-"}</td>
                    <td>${item.expected_duration ? item.expected_duration + " min" : "-"}</td>
                </tr>`;
            });
        } else {
            html += `<tr><td colspan="3">${__("No plan items defined")}</td></tr>`;
        }
        
        html += `</tbody></table>
            <p class="text-muted">${__("One SPS will be created for each plan item when a Requested Procedure uses this plan.")}</p>
        </div>`;
        
        frappe.msgprint({
            title: __("SPS Preview"),
            message: html,
            indicator: "blue"
        });
    }
});
