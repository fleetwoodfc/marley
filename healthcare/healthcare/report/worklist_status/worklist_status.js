// Copyright (c) 2026, healthcare and contributors
// For license information, please see license.txt

frappe.query_reports["Worklist Status"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
            reqd: 0
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), 7),
            reqd: 0
        },
        {
            fieldname: "ups_state",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nSCHEDULED\nIN PROGRESS\nCOMPLETED\nCANCELED",
            reqd: 0
        },
        {
            fieldname: "modality",
            label: __("Modality"),
            fieldtype: "Select",
            options: "\nCT\nMR\nDX\nCR\nUS\nMG\nRF\nNM\nPT\nXA\nOT",
            reqd: 0
        },
        {
            fieldname: "station_name",
            label: __("Station"),
            fieldtype: "Data",
            reqd: 0
        },
        {
            fieldname: "patient",
            label: __("Patient"),
            fieldtype: "Link",
            options: "Patient",
            reqd: 0
        }
    ],
    
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        if (column.fieldname === "ups_state") {
            if (data.ups_state === "SCHEDULED") {
                value = `<span class="indicator-pill blue">${value}</span>`;
            } else if (data.ups_state === "IN PROGRESS") {
                value = `<span class="indicator-pill yellow">${value}</span>`;
            } else if (data.ups_state === "COMPLETED") {
                value = `<span class="indicator-pill green">${value}</span>`;
            } else if (data.ups_state === "CANCELED") {
                value = `<span class="indicator-pill red">${value}</span>`;
            }
        }
        
        return value;
    },
    
    onload: function(report) {
        // Add refresh button
        report.page.add_inner_button(__("Refresh"), function() {
            report.refresh();
        });
        
        // Add quick filters
        report.page.add_inner_button(__("Today Only"), function() {
            const today = frappe.datetime.get_today();
            report.set_filter_value("from_date", today);
            report.set_filter_value("to_date", today);
            report.refresh();
        }, __("Quick Filters"));
        
        report.page.add_inner_button(__("This Week"), function() {
            const today = frappe.datetime.get_today();
            report.set_filter_value("from_date", frappe.datetime.week_start());
            report.set_filter_value("to_date", frappe.datetime.week_end());
            report.refresh();
        }, __("Quick Filters"));
        
        report.page.add_inner_button(__("Pending Only"), function() {
            report.set_filter_value("ups_state", "SCHEDULED");
            report.refresh();
        }, __("Quick Filters"));
        
        report.page.add_inner_button(__("In Progress Only"), function() {
            report.set_filter_value("ups_state", "IN PROGRESS");
            report.refresh();
        }, __("Quick Filters"));
    }
};
