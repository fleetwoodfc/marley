"""
Custom permission hooks for healthcare.ups_worklist_portal.

ups_instance_permission() is registered as the has_permission handler
for the UPS Instance DocType in hooks.py.
"""

import frappe


def ups_instance_permission(doc, ptype, user):
    """
    Returns False to deny write access to COMPLETED/CANCELED workitems
    for non-Supervisor users.  Returns None to defer to standard Frappe
    permission checks for all other cases.

    Registered in hooks.py:
        has_permission = {
            "UPS Instance": "healthcare.ups_worklist_portal.permissions.ups_instance_permission"
        }
    """
    # TODO (T011): implement full permission logic
    if ptype == "write":
        terminal_states = ("COMPLETED", "CANCELED")
        if doc.get("ups_state") in terminal_states:
            roles = frappe.get_roles(user)
            if "UPS Supervisor" not in roles:
                return False
    return None
