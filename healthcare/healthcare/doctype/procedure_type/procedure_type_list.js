// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.listview_settings["Procedure Type"] = {
    add_fields: ["modality", "body_part", "is_billable"],
    
    filters: [
        // Default: show all
    ],
    
    get_indicator(doc) {
        if (doc.is_billable) {
            return [__("Billable"), "green", "is_billable,=,1"];
        }
        return [__("Non-Billable"), "gray", "is_billable,=,0"];
    },
    
    formatters: {
        modality(value, field, doc) {
            if (value) {
                // Color code by modality type
                const colors = {
                    "CT": "blue",
                    "MR": "purple",
                    "XR": "orange",
                    "US": "cyan",
                    "NM": "green",
                    "PT": "red",
                    "RF": "yellow",
                    "DX": "orange",
                    "CR": "orange",
                    "MG": "pink",
                };
                const color = colors[value] || "gray";
                return `<span class="indicator-pill ${color}">${value}</span>`;
            }
            return value;
        }
    },
    
    onload(listview) {
        // Add modality filter
        listview.page.add_field({
            fieldtype: "Select",
            fieldname: "modality_filter",
            label: __("Modality"),
            options: [
                "",
                "CT",
                "MR",
                "XR",
                "US",
                "NM",
                "PT",
                "RF",
                "DX",
                "CR",
                "MG",
            ].join("\n"),
            change() {
                const modality = listview.page.fields_dict.modality_filter.get_value();
                if (modality) {
                    listview.filter_area.add([[listview.doctype, "modality", "=", modality]]);
                } else {
                    listview.filter_area.remove("modality");
                }
                listview.refresh();
            }
        });
        
        // Add body part filter if Body Part doctype exists
        if (frappe.boot.doctypes && frappe.boot.doctypes.includes("Body Part")) {
            listview.page.add_field({
                fieldtype: "Link",
                fieldname: "body_part_filter",
                label: __("Body Part"),
                options: "Body Part",
                change() {
                    const bodyPart = listview.page.fields_dict.body_part_filter.get_value();
                    if (bodyPart) {
                        listview.filter_area.add([[listview.doctype, "body_part", "=", bodyPart]]);
                    } else {
                        listview.filter_area.remove("body_part");
                    }
                    listview.refresh();
                }
            });
        }
    },
    
    button: {
        show(doc) {
            return true;
        },
        get_label() {
            return __("View Plans");
        },
        get_description(doc) {
            return __("View Procedure Plans for {0}", [doc.name]);
        },
        action(doc) {
            frappe.set_route("List", "Procedure Plan", {
                procedure_type: doc.name
            });
        }
    }
};
