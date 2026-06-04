"""
Script to load Procedure Step fixtures into the database.
Run with: bench --site development.localhost execute healthcare.healthcare.load_procedure_step_fixtures
"""

import json
import frappe
from frappe import _


def execute():
	"""Load procedure step fixtures from JSON file."""
	fixture_path = frappe.get_app_path("healthcare", "healthcare", "fixtures", "procedure_step_type.json")
	
	with open(fixture_path) as f:
		steps = json.load(f)
	
	created = 0
	exists = 0
	
	for step in steps:
		step_name = step.get("step_name")
		if not frappe.db.exists("Procedure Step Type", step_name):
			doc = frappe.get_doc(step)
			doc.insert(ignore_permissions=True)
			created += 1
			print(f"Created: {step_name}")
		else:
			exists += 1
			print(f"Exists: {step_name}")
	
	frappe.db.commit()
	print(f"\nSummary: {created} created, {exists} already existed")
