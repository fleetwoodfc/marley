def create_code_values():
    import frappe

    def ensure_code_system(name):
        cs = frappe.db.get_value("Code System", {"code_system": name}, "name")
        if cs:
            return cs
        doc = frappe.get_doc({"doctype": "Code System", "code_system": name, "code_system_name": name})
        doc.insert(ignore_permissions=True)
        return doc.name

    def ensure_code_value(system_name, val):
        csn = ensure_code_system(system_name)
        cv = frappe.db.get_value("Code Value", {"code_system": csn, "code_value": val}, "name")
        if cv:
            return cv
        doc = frappe.get_doc({"doctype": "Code Value", "code_system": csn, "code_value": val})
        doc.insert(ignore_permissions=True)
        return doc.name

    created = []
    created.append(("Intent", "Order", ensure_code_value("Intent", "Order")))
    created.append(("Priority", "Routine", ensure_code_value("Priority", "Routine")))
    created.append(("Priority", "Urgent", ensure_code_value("Priority", "Urgent")))

    for cs, val, name in created:
        print(f"{cs}:{val} -> {name}")

    return created


def submit_pending_service_requests():
    import frappe, traceback

    drafts = frappe.get_all("Service Request", filters={"docstatus": 0}, fields=["name"])[:100]
    results = {"submitted": [], "failed": []}

    for d in drafts:
        name = d["name"] if isinstance(d, dict) else d
        try:
            doc = frappe.get_doc("Service Request", name)
            doc.submit()
            results["submitted"].append(name)
            print(f"SUBMITTED: {name}")
        except Exception as e:
            results["failed"].append({"name": name, "error": str(e), "tb": traceback.format_exc()})
            print(f"FAILED: {name} -> {e}")

    print("SUMMARY:\n", results)
    return results


def create_missing_priorities():
    import frappe

    # gather distinct priority values referenced by draft Service Requests
    priorities = frappe.db.sql(
        """
        SELECT DISTINCT IFNULL(priority, '') as priority
        FROM `tabService Request`
        WHERE docstatus = 0
        """,
        as_dict=1,
    )

    # resolve Priority Code System
    pcsn = frappe.db.get_value("Code System", {"code_system": "Priority"}, "name")
    if not pcsn:
        pcs_doc = frappe.get_doc({"doctype": "Code System", "code_system": "Priority", "code_system_name": "Priority"})
        pcs_doc.insert(ignore_permissions=True)
        pcsn = pcs_doc.name

    created = []
    for row in priorities:
        val = (row.priority or "").strip()
        if not val:
            continue
        cv = frappe.db.get_value("Code Value", {"code_system": pcsn, "code_value": val}, "name")
        if not cv:
            doc = frappe.get_doc({"doctype": "Code Value", "code_system": pcsn, "code_value": val})
            doc.insert(ignore_permissions=True)
            created.append(val)
            print(f"Created Priority Code Value: {val} -> {doc.name}")

    if not created:
        print("No missing Priority Code Values found")
    return created


def create_priority_stat():
    import frappe

    pcsn = frappe.db.get_value("Code System", {"code_system": "Priority"}, "name")
    if not pcsn:
        pcs_doc = frappe.get_doc({"doctype": "Code System", "code_system": "Priority", "code_system_name": "Priority"})
        pcs_doc.insert(ignore_permissions=True)
        pcsn = pcs_doc.name

    val = "Stat"
    cv = frappe.db.get_value("Code Value", {"code_system": pcsn, "code_value": val}, "name")
    if cv:
        print(f"Priority Code Value already exists: {val} -> {cv}")
        return cv

    doc = frappe.get_doc({"doctype": "Code Value", "code_system": pcsn, "code_value": val})
    doc.insert(ignore_permissions=True)
    print(f"Created Priority Code Value: {val} -> {doc.name}")
    return doc.name


def normalize_service_request_code_links():
    import frappe

    srs = frappe.get_all("Service Request", filters={"docstatus": 0}, fields=["name", "intent", "priority"])[:200]
    updated = []
    for s in srs:
        name = s["name"] if isinstance(s, dict) else s
        intent = (s.get("intent") or "").strip()
        priority = (s.get("priority") or "").strip()

        changed = False
        if intent:
            # find Code Value whose code_value/value/label matches intent
            cv = frappe.db.get_value(
                "Code Value",
                {"code_value": intent},
                "name",
            )
            if not cv:
                cv = frappe.db.get_value("Code Value", {"value": intent}, "name")
            if not cv:
                cv = frappe.db.get_value("Code Value", {"label": intent}, "name")
            if cv and cv != intent:
                frappe.db.set_value("Service Request", name, "intent", cv)
                changed = True

        if priority:
            cv = frappe.db.get_value("Code Value", {"code_value": priority}, "name")
            if not cv:
                cv = frappe.db.get_value("Code Value", {"value": priority}, "name")
            if not cv:
                cv = frappe.db.get_value("Code Value", {"label": priority}, "name")
            if cv and cv != priority:
                frappe.db.set_value("Service Request", name, "priority", cv)
                changed = True

        if changed:
            updated.append(name)
            print(f"Updated links for {name}: intent->{intent} priority->{priority} to CodeValue names")

    if not updated:
        print("No Service Requests needed link normalization")
    return updated
