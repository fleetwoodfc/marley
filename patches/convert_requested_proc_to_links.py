import frappe


def migrate():
    """For each Imaging Service Request, create Requested Procedure Link rows
    that point to the corresponding standalone Requested Procedure documents.

    This assumes Requested Procedure standalone docs already exist (created
    by earlier migration). It is idempotent and non-destructive.
    """
    isrs = frappe.get_all("Imaging Service Request", fields=["name"])
    updated = 0
    for isr in isrs:
        try:
            doc = frappe.get_doc("Imaging Service Request", isr.name)
        except Exception:
            continue

        # existing child rows from old model may be present in attribute 'requested_procedures'
        rows = getattr(doc, "requested_procedures", []) or []
        # If first child row is a dict with key 'requested_procedure', assume already migrated
        already_migrated = False
        if rows and isinstance(rows[0], dict) and rows[0].get("requested_procedure"):
            already_migrated = True

        if already_migrated:
            continue

        new_rows = []
        for r in rows:
            # Try to find a matching Requested Procedure by requested_procedure_id or study_instance_uid
            rp = None
            rp_id = r.get("requested_procedure_id")
            if rp_id:
                rp = frappe.db.get_value("Requested Procedure", {"requested_procedure_id": rp_id}, "name")
            if not rp and r.get("study_instance_uid"):
                rp = frappe.db.get_value("Requested Procedure", {"study_instance_uid": r.get("study_instance_uid")}, "name")
            if not rp:
                # try match by description
                if r.get("procedure_description"):
                    rp = frappe.db.get_value("Requested Procedure", {"procedure_description": r.get("procedure_description")}, "name")

            if not rp:
                # nothing to link, skip
                continue

            new_rows.append({"doctype": "Requested Procedure Link", "requested_procedure": rp, "study_instance_uid": r.get("study_instance_uid")})

        if new_rows:
            # Clear existing child rows and set new linked rows
            doc.set("requested_procedures", [])
            for nr in new_rows:
                doc.append("requested_procedures", nr)
            try:
                doc.save(ignore_permissions=True)
                updated += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(), "convert_requested_proc_to_links.error")

    frappe.msgprint(f"Updated {updated} Imaging Service Request documents to link Requested Procedure records.")
