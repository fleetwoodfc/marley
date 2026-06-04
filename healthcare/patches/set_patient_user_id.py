import frappe

def execute():
    """Set user_id for all Patients with an email but missing user_id."""
    patients = frappe.get_all("Patient", filters={"status": "Active"}, fields=["name", "user_id", "email"])
    updated = 0
    for p in patients:
        if not p.user_id and p.email:
            frappe.db.set_value("Patient", p.name, "user_id", p.email)
            updated += 1
    frappe.db.commit()
    print(f"Updated {updated} Patient records with user_id = email.")
