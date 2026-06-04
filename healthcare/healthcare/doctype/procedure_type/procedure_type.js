// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Procedure Type", {
    refresh(frm) {
        // Check for inactive workflow steps and show warning (T016)
        healthcare.procedure_type.check_inactive_workflow_steps(frm);
        
        // Add button to create a new Procedure Plan
        if (!frm.is_new()) {
            frm.add_custom_button(__("Create Procedure Plan"), function() {
                frappe.new_doc("Procedure Plan", {
                    procedure_type: frm.doc.name
                });
            }, __("Actions"));
            
            // Add button to view all plans
            frm.add_custom_button(__("View Plans"), function() {
                frappe.set_route("List", "Procedure Plan", {
                    procedure_type: frm.doc.name
                });
            }, __("Actions"));
            
            // Show linked plans count in the sidebar
            frm.add_custom_button(__("Set Default Plan"), function() {
                healthcare.procedure_type.show_set_default_plan_dialog(frm);
            }, __("Actions"));
        }
        
        // Set query for body part if Body Part doctype exists
        frm.set_query("body_part", function() {
            return {
                filters: {}
            };
        });
        
        // Set query for code_value in procedure_codes child table
        frm.set_query("code_value", "procedure_codes", function(doc, cdt, cdn) {
            return {
                filters: {}
            };
        });
        
        // Add quick entry for procedure codes
        if (!frm.is_new()) {
            healthcare.procedure_type.setup_code_quick_entry(frm);
        }
    },
    
    is_billable(frm) {
        // Clear billing item if not billable
        if (!frm.doc.is_billable) {
            frm.set_value("item", null);
        }
    }
});

// Procedure Type helpers
frappe.provide("healthcare.procedure_type");

$.extend(healthcare.procedure_type, {
    /**
     * Check for inactive workflow steps and show warning indicator (T016)
     */
    check_inactive_workflow_steps(frm) {
        if (!frm.doc.workflow_steps || frm.doc.workflow_steps.length === 0) {
            return;
        }
        
        // Get unique procedure step names from the workflow
        const step_names = frm.doc.workflow_steps
            .map(row => row.procedure_step_type)
            .filter(name => name);
        
        if (step_names.length === 0) {
            return;
        }
        
        // Check if any linked steps are inactive
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Procedure Step Type",
                filters: {
                    name: ["in", step_names],
                    is_active: 0
                },
                fields: ["step_name"]
            },
            callback(r) {
                if (r.message && r.message.length > 0) {
                    const inactive_names = r.message.map(s => s.step_name).join(", ");
                    frm.dashboard.add_comment(
                        __("Warning: This procedure type contains inactive workflow steps: {0}. Consider removing or replacing them.", [inactive_names]),
                        "yellow",
                        true
                    );
                }
            }
        });
    },
    
    /**
     * Setup quick entry for procedure codes
     */
    setup_code_quick_entry(frm) {
        // Add button to add CPT code
        frm.add_custom_button(__("Add CPT Code"), function() {
            healthcare.procedure_type.add_code_dialog(frm, "CPT");
        }, __("Add Code"));
        
        // Add button to add LOINC code
        frm.add_custom_button(__("Add LOINC Code"), function() {
            healthcare.procedure_type.add_code_dialog(frm, "LOINC");
        }, __("Add Code"));
        
        // Add button to add SNOMED-CT code
        frm.add_custom_button(__("Add SNOMED-CT Code"), function() {
            healthcare.procedure_type.add_code_dialog(frm, "SNOMED-CT");
        }, __("Add Code"));
    },
    
    /**
     * Show dialog to add a code
     */
    add_code_dialog(frm, code_system) {
        const d = new frappe.ui.Dialog({
            title: __("Add {0} Code", [code_system]),
            fields: [
                {
                    fieldname: "code_value",
                    fieldtype: "Link",
                    label: __("Code"),
                    options: "Code Value",
                    reqd: 1,
                    get_query() {
                        return {
                            filters: {
                                code_system: ["like", `%${code_system}%`]
                            }
                        };
                    }
                },
                {
                    fieldname: "description",
                    fieldtype: "Small Text",
                    label: __("Description"),
                    read_only: 1
                }
            ],
            primary_action_label: __("Add"),
            primary_action(values) {
                // Add the code to the child table
                let row = frm.add_child("procedure_codes", {
                    code_value: values.code_value
                });
                frm.refresh_field("procedure_codes");
                d.hide();
                frm.dirty();
            }
        });
        
        // Fetch code description when code is selected
        d.fields_dict.code_value.$input.on("awesomplete-selectcomplete", function() {
            const code_value = d.get_value("code_value");
            if (code_value) {
                frappe.db.get_value("Code Value", code_value, "code_meaning", (r) => {
                    if (r) {
                        d.set_value("description", r.code_meaning);
                    }
                });
            }
        });
        
        d.show();
    },
    
    /**
     * Show dialog to set default plan
     */
    show_set_default_plan_dialog(frm) {
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Procedure Plan",
                filters: {
                    procedure_type: frm.doc.name
                },
                fields: ["name", "plan_name", "is_default"]
            },
            callback(r) {
                if (!r.message || r.message.length === 0) {
                    frappe.msgprint(__("No Procedure Plans found for this Procedure Type. Create a plan first."));
                    return;
                }
                
                const plans = r.message;
                const options = plans.map(p => ({
                    label: `${p.plan_name || p.name}${p.is_default ? " (Current Default)" : ""}`,
                    value: p.name
                }));
                
                const d = new frappe.ui.Dialog({
                    title: __("Set Default Plan"),
                    fields: [
                        {
                            fieldname: "plan",
                            fieldtype: "Select",
                            label: __("Select Plan"),
                            options: options.map(o => o.value),
                            reqd: 1
                        }
                    ],
                    primary_action_label: __("Set as Default"),
                    primary_action(values) {
                        frappe.call({
                            method: "frappe.client.set_value",
                            args: {
                                doctype: "Procedure Plan",
                                name: values.plan,
                                fieldname: "is_default",
                                value: 1
                            },
                            callback() {
                                frappe.show_alert({
                                    message: __("Default plan updated"),
                                    indicator: "green"
                                });
                                d.hide();
                            }
                        });
                    }
                });
                d.show();
            }
        });
    }
});
