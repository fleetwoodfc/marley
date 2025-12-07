"""
Default success action shown after running the Healthcare setup.
Modeled after erpnext.setup.default_success_action.py
"""
def get_default_success_action():
    """
    Return a minimal structure describing what the setup did and next actions.
    This can be used by a setup wizard front-end to render a success page.
    """
    return {
        "title": "Healthcare setup complete",
        "message": (
            "The Healthcare module is ready. You can now create Patients, "
            "Schedule Appointments and configure Providers."
        ),
        "actions": [
            {"label": "Create Patient", "route": "/app/patient/new"},
            {"label": "Create Provider", "route": "/app/provider/new"},
            {"label": "Create Appointment", "route": "/app/appointment/new"},
            {"label": "View Healthcare Dashboard", "route": "/app/healthcare-dashboard"}
        ]
    }