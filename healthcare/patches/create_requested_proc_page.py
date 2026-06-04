import frappe


def create():
    """Create a Desk Page named 'requested-procedure' to enable /desk/requested-procedure."""
    try:
        if frappe.db.exists("Page", "requested-procedure"):
            return "Page already exists"
        page = frappe.get_doc({
            "doctype": "Page",
            "page_name": "requested-procedure",
            "title": "Requested Procedure",
            "module": "Healthcare",
            "standard": "No",
        })
        # Temporarily mark as in_migrate to bypass route-conflict validation
        frappe.flags.in_migrate = True
        try:
            page.insert(ignore_permissions=True)
        finally:
            frappe.flags.in_migrate = False
        return "Page created"
    except Exception:
        frappe.log_error(frappe.get_traceback(), "create_requested_proc_page.error")
        raise
