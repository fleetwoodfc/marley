"""
Healthcare setup installation entrypoints.
Modeled after erpnext/setup/install.py but kept concise and focused on Healthcare needs.

Usage:
- Import healthcare.setup.install and call setup_healthcare() from your app's post-install hook
  or from a CLI command.
"""

try:
    import frappe
    from frappe import _
except Exception:
    frappe = None
    _ = lambda s: s

from . import utils, demo, default_success_action

def setup_healthcare(create_demo=False, user=None):
    """
    Run the main setup for Healthcare module.

    Args:
        create_demo (bool): if True, populate demo data (patients, providers, appointments).
        user (str): optional user to assign Healthcare role to.
    """
    if not frappe:
        print("Frappe not available; skipping setup.")
        return

    frappe.publish_realtime("progress", {"status": "Initializing Healthcare setup"}, user=frappe.session.user if frappe.session else user)

    # 1. create roles used by Healthcare
    _create_roles()

    # 2. create minimal doctypes/pages/workspace shortcuts
    _create_basic_doctypes_and_workspace()

    # 3. set single/doc default settings
    _set_default_settings()

    # 4. optionally create demo data
    if create_demo:
        demo.create_demo_data()

    # 5. If a user was provided, give them the Healthcare role
    if user:
        utils.add_user_role(user, "Healthcare User")

    # 6. Return a success payload for a setup wizard
    return default_success_action.get_default_success_action()

def _create_roles():
    """
    Create roles that make sense for Healthcare module.
    """
    utils.make_role("Healthcare User")
    utils.make_role("Healthcare Manager", role_type="System Manager")

def _create_basic_doctypes_and_workspace():
    """
    Ensure common doctypes are present (Patient, Provider, Appointment) and create workspace.
    These are simple helpers: in an ERPNext app you should use fixtures or proper DocType definitions.
    """
    # Create basic placeholders for doctypes (useful in development/demo environments)
    utils.create_doctype_link("Patient")
    utils.create_doctype_link("Provider")
    utils.create_doctype_link("Appointment")

    items = [
        {"type": "doctype", "name": "Patient"},
        {"type": "doctype", "name": "Provider"},
        {"type": "doctype", "name": "Appointment"},
        {"type": "page", "name": "Healthcare Dashboard"},
    ]
    utils.create_workspace_if_not_exists("Healthcare", items)

def _set_default_settings():
    """
    Set default configuration values for Healthcare (stored in Single DocType).
    """
    # Example single doctype settings name: Healthcare Settings
    values = {
        "default_appointment_duration_minutes": 30,
        "allow_walkins": True,
        "default_patient_country": "United States"
    }
    utils.make_or_update_single("Healthcare Settings", values)