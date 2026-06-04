import frappe
from .radlex_api import search_radlex


@frappe.whitelist()
def search(query, modality=None, body_part=None):
    """
    Frappe REST endpoint for RadLex search.
    Returns list of dicts: {rpid, name, description}
    """
    try:
        # normalize empty strings to None
        modality = modality or None
        body_part = body_part or None
        results = search_radlex(query, modality=modality, body_part=body_part)
        return results
    except Exception as e:
        frappe.log_error(f"RadLex search failed: {e}")
        return []
