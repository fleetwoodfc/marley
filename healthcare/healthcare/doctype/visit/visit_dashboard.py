"""Dashboard configuration for Visit DocType."""


def get_data():
    """Return dashboard configuration for Visit.

    Since Visit uses child tables to track related documents (appointments,
    encounters, service_requests), we define internal_links to look up
    these relationships from the child tables.

    For Sales Invoice, the Visit has a reference field (ref_sales_invoice)
    rather than Sales Invoice having a field pointing to Visit, so we use
    internal_links with the direct field.
    """
    return {
        "fieldname": "visit",
        "non_standard_fieldnames": {},
        "internal_links": {
            "Patient Appointment": ["appointments", "appointment"],
            "Patient Encounter": ["encounters", "encounter"],
            "Service Request": ["service_requests", "service_request"],
            "Sales Invoice": "ref_sales_invoice",
        },
        "transactions": [
            {
                "label": "Clinical",
                "items": ["Patient Appointment", "Patient Encounter"],
            },
            {
                "label": "Orders",
                "items": ["Service Request"],
            },
            {
                "label": "Billing",
                "items": ["Sales Invoice"],
            },
        ],
    }
