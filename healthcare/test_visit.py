"""Test Visit creation."""
import frappe
from frappe.utils import today


def check_custom_fields():
    """Check if custom fields exist for Visit."""
    custom_fields = frappe.get_all(
        'Custom Field',
        filters={'fieldname': 'is_demo_data'},
        fields=['name', 'dt', 'fieldname']
    )
    print("Custom fields with is_demo_data:")
    for cf in custom_fields:
        print(f"  - {cf.name} (DocType: {cf.dt})")

    # Check if Visit has the column
    has_column = frappe.db.has_column('Visit', 'is_demo_data')
    print(f"Visit table has is_demo_data column: {has_column}")
    return has_column


def add_visit_column():
    """Add is_demo_data column to Visit table."""
    # First check if Custom Field exists
    if frappe.db.exists('Custom Field', 'Visit-is_demo_data'):
        print("Custom Field already exists, just syncing...")
        frappe.reload_doc('healthcare', 'doctype', 'visit', force=True)
    else:
        print("Creating Custom Field for Visit...")
        cf = frappe.new_doc('Custom Field')
        cf.dt = 'Visit'
        cf.fieldname = 'is_demo_data'
        cf.fieldtype = 'Check'
        cf.label = 'Is Demo Data'
        cf.insert_after = 'amended_from'
        cf.hidden = 1
        cf.print_hide = 1
        cf.no_copy = 1
        cf.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"Created Custom Field: {cf.name}")

    # Now add column if needed
    if not frappe.db.has_column('Visit', 'is_demo_data'):
        frappe.db.sql('ALTER TABLE tabVisit ADD COLUMN is_demo_data TINYINT(1) DEFAULT 0')
        frappe.db.commit()
        print("Added is_demo_data column to Visit table")


def test_create_visit():
    """Test creating a single Visit document."""
    # First check/create the column
    if not check_custom_fields():
        print("Adding column...")
        add_visit_column()

    patient_names = frappe.get_all('Patient', filters={'is_demo_data': 1}, pluck='name', limit=1)
    practitioner_names = frappe.get_all('Healthcare Practitioner', filters={'is_demo_data': 1}, pluck='name', limit=1)
    company = frappe.db.get_single_value('Global Defaults', 'default_company')

    print(f"Patient: {patient_names}")
    print(f"Practitioner: {practitioner_names}")
    print(f"Company: {company}")

    if not patient_names or not practitioner_names:
        print("No patients or practitioners found!")
        return

    doc = frappe.new_doc('Visit')
    doc.patient = patient_names[0]
    doc.company = company
    doc.visit_date = today()
    doc.visit_type = 'Outpatient'
    doc.status = 'Scheduled'
    doc.chief_complaint = 'Test visit'
    doc.primary_practitioner = practitioner_names[0]
    doc.priority = 'Routine'

    try:
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f'Created Visit: {doc.name}')
    except Exception as e:
        print(f'Error creating visit: {e}')
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_create_visit()
