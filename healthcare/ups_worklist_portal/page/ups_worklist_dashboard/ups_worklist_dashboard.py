"""
Server-side module for the UPS Dashboard desk page.

NOTE: get_context() is only invoked for web/portal pages, NOT for Frappe desk
pages.  AE Mappings and user context are therefore fetched by the JavaScript
at runtime via healthcare.ups_worklist_portal.api.ups_actions.get_ae_mappings().
This file is retained for any future web-page variant or utility functions.
"""

import frappe


def get_context(context):
    """Populate template context for ups_dashboard page."""
    context.update(
        {
            "title": "UPS Dashboard",
            "ae_mappings": frappe.get_list(
                "AE Mapping",
                filters={"active": 1},
                fields=["ae_title", "display_name", "modality", "assigned_user"],
                order_by="ae_title asc",
            ),
            "current_user": frappe.session.user,
            "current_user_roles": frappe.get_roles(frappe.session.user),
            "ups_rs_host": _get_ups_rs_host(),
        }
    )
    return context


def _get_ups_rs_host():
    """Return only the host portion of the UPS-RS URL (no credentials)."""
    try:
        url = frappe.db.get_single_value("UPS Integration Settings", "ups_rs_url") or ""
        # Return only scheme + host to avoid leaking credentials in page HTML
        from urllib.parse import urlparse  # noqa: PLC0415

        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url
    except Exception:
        return ""
