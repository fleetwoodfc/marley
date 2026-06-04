"""
Patch: Migrate data after renaming Procedure Step DocTypes.

In spec 011-procedure-steps-catalog, the two DocType names were inverted:
  - "Procedure Step" (master catalog/template) → renamed to "Procedure Step Type"
  - "Procedure Type Step" (child table row in Procedure Type) → renamed to "Procedure Step"

This patch migrates existing master catalog records from tabProcedure Step
to tabProcedure Step Type, handles any child table rows in tabProcedure Type Step,
and ensures tabProcedure Step has the parent/parentfield/parenttype columns required
for child tables (bench migrate does not add these when the table pre-existed as istable=0).
"""

import frappe
from frappe import _


def execute():
	"""Migrate Procedure Step data to correctly named DocTables."""

	# Ensure tabProcedure Step has child-table columns (parent/parentfield/parenttype).
	# bench migrate does not add these when the table already existed as istable=0.
	if frappe.db.table_exists("Procedure Step"):
		existing_cols = {row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabProcedure Step`")}
		if "parent" not in existing_cols:
			frappe.db.sql("""
				ALTER TABLE `tabProcedure Step`
				  ADD COLUMN `parent` varchar(140) DEFAULT NULL AFTER `idx`,
				  ADD COLUMN `parentfield` varchar(140) DEFAULT NULL AFTER `parent`,
				  ADD COLUMN `parenttype` varchar(140) DEFAULT NULL AFTER `parentfield`,
				  ADD KEY `parent` (`parent`)
			""")
			frappe.db.commit()
			print("Added parent/parentfield/parenttype columns to tabProcedure Step")

	# Migrate master catalog records: tabProcedure Step → tabProcedure Step Type
	# Only copy rows that have step_name (master catalog rows, not child table rows)
	if frappe.db.table_exists("Procedure Step") and frappe.db.table_exists("Procedure Step Type"):
		master_count = frappe.db.count("Procedure Step", {"step_name": ["is", "set"]})
		already_migrated = frappe.db.count("Procedure Step Type")

		if master_count > 0 and already_migrated == 0:
			frappe.db.sql("""
				INSERT INTO `tabProcedure Step Type`
				  (name, creation, modified, modified_by, owner, docstatus, idx,
				   step_name, description, radlex_rpid, radlex_name, radlex_description,
				   phase, typical_duration, required_role, is_active, is_system,
				   _user_tags, _comments, _assign, _liked_by)
				SELECT
				  name, creation, modified, modified_by, owner, docstatus, idx,
				  step_name, description, radlex_rpid, radlex_name, radlex_description,
				  phase, typical_duration, required_role, is_active, is_system,
				  _user_tags, _comments, _assign, _liked_by
				FROM `tabProcedure Step`
				WHERE step_name IS NOT NULL
			""")
			frappe.db.sql("DELETE FROM `tabProcedure Step` WHERE step_name IS NOT NULL")
			frappe.db.commit()
			migrated = frappe.db.count("Procedure Step Type")
			print(f"Migrated {migrated} Procedure Step Type records")
		else:
			print(f"Skipping migration: {master_count} source records, {already_migrated} already in target")

	# Migrate child table rows: tabProcedure Type Step → tabProcedure Step
	# These are rows with parent/parentfield/parenttype (child table pattern)
	if frappe.db.table_exists("Procedure Type Step") and frappe.db.table_exists("Procedure Step"):
		child_count = frappe.db.sql("SELECT COUNT(*) FROM `tabProcedure Type Step`")[0][0]
		if child_count > 0:
			frappe.db.sql("""
				INSERT INTO `tabProcedure Step`
				  (name, creation, modified, modified_by, owner, docstatus, idx,
				   procedure_step_type, sequence, phase, parent, parentfield, parenttype)
				SELECT
				  name, creation, modified, modified_by, owner, docstatus, idx,
				  procedure_step, sequence, phase, parent, parentfield, parenttype
				FROM `tabProcedure Type Step`
			""")
			frappe.db.sql("DELETE FROM `tabProcedure Type Step`")
			frappe.db.commit()
			print(f"Migrated {child_count} Procedure Step child table rows")
