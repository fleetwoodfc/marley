"""
Create demo data for the Healthcare module.
Modeled after erpnext.setup.demo.py but intentionally small and safe to run.
"""

try:
    import frappe
    from frappe.utils import nowdate
except Exception:
    frappe = None
    nowdate = lambda: "2025-01-01"

def create_demo_patient(name="John Doe", email="john@example.com", mobile="555-0100"):
    if not frappe:
        return
    if frappe.db.exists("Patient", {"patient_name": name}):
        return
    patient = frappe.get_doc({
        "doctype": "Patient",
        "patient_name": name,
        "email_id": email,
        "mobile_no": mobile,
        "date_of_birth": "1990-01-01"
    })
    patient.insert(ignore_permissions=True)
    frappe.db.commit()

def create_demo_provider(name="Dr. Alice", email="alice@example.com", specialty="General"):
    if not frappe:
        return
    if frappe.db.exists("Provider", {"provider_name": name}):
        return
    prov = frappe.get_doc({
        "doctype": "Provider",
        "provider_name": name,
        "email_id": email,
        "specialty": specialty
    })
    prov.insert(ignore_permissions=True)
    frappe.db.commit()

def create_demo_appointment(patient_name="John Doe", provider_name="Dr. Alice", date=None):
    if not frappe:
        return
    date = date or nowdate()
    # ensure referenced docs exist
    if not frappe.db.exists("Patient", {"patient_name": patient_name}):
        create_demo_patient(patient_name)
    if not frappe.db.exists("Provider", {"provider_name": provider_name}):
        create_demo_provider(provider_name)
    if frappe.db.exists("Appointment", {"patient": patient_name, "appointment_date": date}):
        return
    appt = frappe.get_doc({
        "doctype": "Appointment",
        "patient": patient_name,
        "provider": provider_name,
        "appointment_date": date,
        "status": "Scheduled"
    })
    appt.insert(ignore_permissions=True)
    frappe.db.commit()

def create_demo_data():
    """
    Top-level helper called by setup to create demo records.
    """
    if not frappe:
        return
    create_demo_patient()
    create_demo_provider()
    create_demo_appointment()