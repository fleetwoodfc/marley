// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Procedure Type", {
    refresh(frm) {
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
        }
        
        // Set query for body part if Body Part doctype exists
        frm.set_query("body_part", function() {
            return {
                filters: {}
            };
        });
    },
    
    is_billable(frm) {
        // Clear billing item if not billable
        if (!frm.doc.is_billable) {
            frm.set_value("item", null);
        }
    }
});
