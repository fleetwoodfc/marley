"""
Helper utilities for Healthcare setup.
This is a lightweight, self-contained implementation modeled after erpnext/setup/utils.py
so it can be adapted into a Frappe/ERPNext app or used as a reference for another system.
"""

# NOTE: This module assumes a Frappe-like environment when imported into ERPNext/Frappe.
# If you're not using Frappe, you can adapt the helper functions to your frameworks'
# database/ORM methods.

try:
	import frappe
except Exception:
	frappe = None  # allow importing for static analysis outside Frappe


def safe_get_doc(doctype, name):
	"""Return document if exists, else None (Frappe helper)."""
	if not frappe:
		return None
	try:
		return frappe.get_doc(doctype, name)
	except Exception:
		return None


def make_or_update_single(doctype, values):
	"""
	Create or update a single DocType (like a Settings doctype with only one record).
	values: dict of field->value
	"""
	if not frappe:
		return
	existing = frappe.db.get_single_value(doctype, "name") if frappe.db else None
	# fallback: try to get single doc
	try:
		doc = frappe.get_single(doctype)
		for k, v in values.items():
			doc.set(k, v)
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		# try creating new doc
		try:
			doc = frappe.new_doc(doctype)
			for k, v in values.items():
				doc.set(k, v)
			doc.insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error(f"Failed to make or update single {doctype}")


def make_role(role_name, role_type="All"):
	"""
	Create role if not present. Compatible with Frappe's Role doctype.
	"""
	if not frappe:
		return
	if frappe.db.exists("Role", role_name):
		return
	role = frappe.get_doc({"doctype": "Role", "role_name": role_name, "role_type": role_type})
	role.insert(ignore_permissions=True)
	frappe.db.commit()


def add_user_role(user, role):
	"""
	Assign a role to a user if not already assigned.
	"""
	if not frappe:
		return
	user_doc = frappe.get_doc("User", user)
	roles = [r.role for r in user_doc.roles]
	if role in roles:
		return
	user_doc.add_roles(role)
	frappe.db.commit()


def create_workspace_if_not_exists(title, items=None):
	"""
	Create a simple workspace (desktop page) to surface Healthcare features.
	items is a list of dicts: {"type": "doctype"|"page", "name": "Patient"}
	"""
	if not frappe:
		return
	if frappe.db.exists("Workspace", title):
		return

	workspace = frappe.get_doc({"doctype": "Workspace", "title": title, "public": 1})

	if items:
		for item in items:
			workspace.append(
				"links",
				{
					"type": item.get("type", "Link"),
					"link_type": item.get("link_type", "DocType"),
					"link_to": item.get("name"),
					"label": item.get("label", item.get("name")),
				},
			)

	workspace.insert(ignore_permissions=True)
	frappe.db.commit()
