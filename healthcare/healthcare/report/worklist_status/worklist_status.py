# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""Worklist Status Report

Shows summary of Scheduled Procedure Step statuses with filters for
modality, date range, and station.
"""

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime


def execute(filters=None):
    """Execute the report and return columns, data, message, and chart."""
    filters = frappe._dict(filters or {})
    
    columns = get_columns(filters)
    data = get_data(filters)
    chart = get_chart_data(data, filters)
    summary = get_summary(data)
    
    return columns, data, None, chart, summary


def get_columns(filters):
    """Define report columns."""
    columns = [
        {
            "label": _("Procedure Step"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Scheduled Procedure Step",
            "width": 150,
        },
        {
            "label": _("Patient"),
            "fieldname": "patient",
            "fieldtype": "Link",
            "options": "Patient",
            "width": 120,
        },
        {
            "label": _("Patient Name"),
            "fieldname": "patient_name",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Status"),
            "fieldname": "ups_state",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Modality"),
            "fieldname": "modality",
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "label": _("Scheduled"),
            "fieldname": "scheduled_datetime",
            "fieldtype": "Datetime",
            "width": 150,
        },
        {
            "label": _("Station"),
            "fieldname": "station_name",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Claimed By"),
            "fieldname": "claimed_by",
            "fieldtype": "Link",
            "options": "User",
            "width": 120,
        },
        {
            "label": _("Description"),
            "fieldname": "procedure_step_label",
            "fieldtype": "Data",
            "width": 200,
        },
    ]
    
    return columns


def get_data(filters):
    """Get report data based on filters."""
    conditions = get_conditions(filters)
    
    data = frappe.db.sql(
        """
        SELECT
            sps.name,
            sps.patient,
            sps.patient_name,
            sps.ups_state,
            sps.modality,
            sps.scheduled_datetime,
            sps.station_name,
            sps.station_aet,
            sps.claimed_by,
            sps.procedure_step_label,
            sps.imaging_service_request
        FROM
            `tabScheduled Procedure Step` sps
        WHERE
            1=1
            {conditions}
        ORDER BY
            sps.scheduled_datetime DESC
        """.format(conditions=conditions),
        filters,
        as_dict=True,
    )
    
    return data


def get_conditions(filters):
    """Build WHERE conditions from filters."""
    conditions = []
    
    if filters.get("from_date"):
        conditions.append("AND sps.scheduled_datetime >= %(from_date)s")
    
    if filters.get("to_date"):
        conditions.append("AND sps.scheduled_datetime <= %(to_date)s")
    
    if filters.get("modality"):
        conditions.append("AND sps.modality = %(modality)s")
    
    if filters.get("ups_state"):
        conditions.append("AND sps.ups_state = %(ups_state)s")
    
    if filters.get("station_name"):
        conditions.append("AND sps.station_name = %(station_name)s")
    
    if filters.get("patient"):
        conditions.append("AND sps.patient = %(patient)s")
    
    return " ".join(conditions)


def get_chart_data(data, filters):
    """Generate chart data for status distribution."""
    # Count by status
    status_counts = {}
    for row in data:
        status = row.get("ups_state", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Define colors for each status
    status_colors = {
        "SCHEDULED": "#318AD8",      # Blue
        "IN PROGRESS": "#ECAD4B",    # Yellow
        "COMPLETED": "#36AE7C",      # Green
        "CANCELED": "#E24C4C",       # Red
    }
    
    labels = list(status_counts.keys())
    values = list(status_counts.values())
    colors = [status_colors.get(s, "#7575FF") for s in labels]
    
    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": _("Procedures"),
                    "values": values,
                }
            ],
        },
        "type": "donut",
        "colors": colors,
        "height": 280,
    }
    
    return chart


def get_summary(data):
    """Generate summary cards."""
    total = len(data)
    scheduled = sum(1 for row in data if row.get("ups_state") == "SCHEDULED")
    in_progress = sum(1 for row in data if row.get("ups_state") == "IN PROGRESS")
    completed = sum(1 for row in data if row.get("ups_state") == "COMPLETED")
    canceled = sum(1 for row in data if row.get("ups_state") == "CANCELED")
    
    return [
        {
            "value": total,
            "label": _("Total Procedures"),
            "datatype": "Int",
        },
        {
            "value": scheduled,
            "label": _("Scheduled"),
            "datatype": "Int",
            "indicator": "blue",
        },
        {
            "value": in_progress,
            "label": _("In Progress"),
            "datatype": "Int",
            "indicator": "yellow",
        },
        {
            "value": completed,
            "label": _("Completed"),
            "datatype": "Int",
            "indicator": "green",
        },
        {
            "value": canceled,
            "label": _("Canceled"),
            "datatype": "Int",
            "indicator": "red",
        },
    ]
