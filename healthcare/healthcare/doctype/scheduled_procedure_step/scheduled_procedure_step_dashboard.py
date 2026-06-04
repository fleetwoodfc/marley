# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""Dashboard configuration for Scheduled Procedure Step."""


def get_data():
    """Return dashboard configuration for Scheduled Procedure Step."""
    return {
        "heatmap": True,
        "heatmap_message": __(
            "Procedures scheduled and completed over the past year"
        ),
        "fieldname": "scheduled_procedure_step",
        "non_standard_fieldnames": {
            "Performed Procedure Step": "scheduled_procedure_step",
            "Cancellation Request": "scheduled_procedure_step",
        },
        "transactions": [
            {
                "label": __("Performance"),
                "items": ["Performed Procedure Step"],
            },
            {
                "label": __("Requests"),
                "items": ["Cancellation Request"],
            },
        ],
        "reports": [
            {
                "label": __("Worklist Status"),
                "name": "Worklist Status",
                "is_query_report": True,
            }
        ],
    }


def __(text):
    """Translation function placeholder."""
    return text
