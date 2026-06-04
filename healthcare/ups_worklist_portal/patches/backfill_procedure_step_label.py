"""
Patch: backfill procedure_description from DICOM tag (0074,1204) Procedure Step Label
stored in raw_payload for all UPS Instance records that lack it.
"""
import json
import frappe


def execute():
    rows = frappe.db.sql(
        "SELECT name, raw_payload FROM `tabUPS Instance` WHERE raw_payload IS NOT NULL",
        as_dict=True,
    )

    updated = 0
    for row in rows:
        if not row.raw_payload:
            continue
        payload = json.loads(row.raw_payload)
        tag = payload.get("00741204")
        if not tag:
            continue
        values = tag.get("Value") or []
        step_label = values[0] if values else None
        if not step_label:
            continue
        frappe.db.set_value(
            "UPS Instance",
            row.name,
            "procedure_description",
            step_label,
            update_modified=False,
        )
        updated += 1

    frappe.db.commit()
    print(f"backfill_procedure_step_label: {updated} of {len(rows)} records updated")
