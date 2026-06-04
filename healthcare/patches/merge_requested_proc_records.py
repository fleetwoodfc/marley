import frappe


def migrate():
    """Merge Requested Procedure Record docs into Requested Procedure.

    For each Requested Procedure Record (RPR):
    - If a Requested Procedure (RP) exists with same `requested_procedure_id` or `study_instance_uid`, update it.
    - Otherwise create a new RP copying fields from RPR.
    - Remove the RPR document after migrating.

    This script is idempotent.
    """
    rprs = frappe.get_all("Requested Procedure Record", fields=["name"])
    migrated = 0
    for r in rprs:
        try:
            rec = frappe.get_doc("Requested Procedure Record", r.name)
        except Exception:
            continue

        rp_name = None
        if rec.requested_procedure_id:
            rp_name = frappe.db.get_value("Requested Procedure", {"requested_procedure_id": rec.requested_procedure_id}, "name")

        if not rp_name and rec.study_instance_uid:
            rp_name = frappe.db.get_value("Requested Procedure", {"study_instance_uid": rec.study_instance_uid}, "name")

        if rp_name:
            # update existing RP with any missing fields
            try:
                rp = frappe.get_doc("Requested Procedure", rp_name)
                changed = False
                for field in ["procedure_type", "procedure_description", "scheduled_datetime", "modality", "reason_for_request", "comments"]:
                    if getattr(rp, field, None) in (None, "") and getattr(rec, field, None):
                        setattr(rp, field, getattr(rec, field))
                        changed = True
                if not getattr(rp, "requested_procedure_id", None) and getattr(rec, "requested_procedure_id", None):
                    rp.requested_procedure_id = rec.requested_procedure_id
                    changed = True
                if changed:
                    rp.save(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "merge_requested_proc.update_error")
        else:
            # create new Requested Procedure
            try:
                new_rp = frappe.get_doc({
                    "doctype": "Requested Procedure",
                    "study_instance_uid": rec.study_instance_uid,
                    "procedure_type": rec.procedure_type,
                    "procedure_description": rec.procedure_description,
                    "scheduled_datetime": rec.scheduled_datetime,
                    "modality": rec.modality,
                    "reason_for_request": rec.reason_for_request,
                    "comments": rec.comments,
                    "requested_procedure_id": rec.requested_procedure_id,
                })
                new_rp.insert(ignore_permissions=True)
                rp_name = new_rp.name
            except Exception:
                frappe.log_error(frappe.get_traceback(), "merge_requested_proc.create_error")
                continue

        # Update any child links that reference the RPR name (if any exist)
        try:
            # Look for any doctypes that may store the RPR name in Link fields referencing Requested Procedure Record
            # This is best-effort: update known child tables referencing Requested Procedure Record
            # Example: check Imaging Service Request old child rows
            isrs = frappe.get_all("Imaging Service Request", fields=["name"])
            for isr in isrs:
                doc = frappe.get_doc("Imaging Service Request", isr.name)
                updated = False
                rows = getattr(doc, "requested_procedures", []) or []
                for row in rows:
                    # If the child row is a dict containing a link to RPR by name, update to RP
                    if isinstance(row, dict) and row.get("requested_procedure") == rec.name:
                        row.requested_procedure = rp_name
                        updated = True
                if updated:
                    doc.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "merge_requested_proc.link_update_error")

        # Delete the RPR doc
        try:
            rec.delete()
            migrated += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "merge_requested_proc.delete_error")

    frappe.msgprint(f"Migrated {migrated} Requested Procedure Record documents into Requested Procedure.")
