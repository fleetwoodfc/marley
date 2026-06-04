import frappe


def migrate():
    """Create standalone Requested Procedure Record docs from existing child rows.

    This is non-destructive: child rows are left in place. New docs include a
    link back to the parent Imaging Service Request via `imaging_service_request`.
    This migration is safe to run multiple times; it avoids creating duplicates
    when `requested_procedure_id` is present and already exists.
    """
    isrs = frappe.get_all("Imaging Service Request", fields=["name"])
    created = 0
    for isr in isrs:
        try:
            doc = frappe.get_doc("Imaging Service Request", isr.name)
        except Exception:
            continue

        rows = getattr(doc, "requested_procedures", []) or []
        for r in rows:
            try:
                # Skip if we've already created a record with same requested_procedure_id
                if r.get("requested_procedure_id") and frappe.db.exists("Requested Procedure Record", r.get("requested_procedure_id")):
                    continue

                rp = frappe.get_doc({
                    "doctype": "Requested Procedure Record",
                    "imaging_service_request": doc.name,
                    "study_instance_uid": r.get("study_instance_uid"),
                    "procedure_type": r.get("procedure_type"),
                    "procedure_description": r.get("procedure_description"),
                    "scheduled_datetime": r.get("scheduled_datetime"),
                    "modality": r.get("modality"),
                    "reason_for_request": r.get("reason_for_request"),
                    "comments": r.get("comments"),
                    "requested_procedure_id": r.get("requested_procedure_id") or frappe.generate_hash(length=8),
                })
                rp.insert(ignore_permissions=True)
                created += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(), "migrate_requested_procedures.error")

    frappe.msgprint(f"Created {created} Requested Procedure Record documents.")
