"""
Demo teardown: all modules
==========================

Removes every record in the UPS Worklist Portal demo environment:

    Phase 1 — UPS Instances + UPS Events (ALL rows, regardless of origin)
               This catches workitems seeded by demo scripts AND any
               workitems synced from dcm4chee-arc during testing.

    Phase 2 — All Imaging Service Requests, Scheduled Procedure Steps,
               and Requested Procedures (regardless of patient).

    Phase 3 — All Patient records EXCEPT known framework test records
               (_Test IPD Patient, urn:uuid:patient-1).

    Phase 4 — Healthcare Practitioners, Procedure Types, Procedure Plans,
               and AE Mappings added by order_filling_examples.

    Phase 5 — AI AE Mappings added by aiw_i_use_cases
               (these are NOT in the fixtures).

Idempotent — safe to run multiple times, missing records are skipped.

Usage::

    bench --site development.localhost execute \\
        healthcare.demo.teardown_all.run
"""

import frappe

# Patient names that belong to the Frappe/healthcare framework test suite
# and must never be deleted by demo teardown.
_SYSTEM_PATIENTS = {"_Test IPD Patient", "urn:uuid:patient-1"}


def _purge_all_ups_instances():
    """Delete every UPS Event then every UPS Instance in the site."""
    print("\n── Phase 1: UPS Instances + Events (all) ────────────────────────")

    event_count = frappe.db.count("UPS Event")
    if event_count:
        frappe.db.sql("DELETE FROM `tabUPS Event`")
        print(f"  ✗  Deleted {event_count} UPS Event(s)")
    else:
        print("  —  No UPS Events found")

    count = frappe.db.count("UPS Instance")
    if count:
        frappe.db.sql("DELETE FROM `tabUPS Instance`")
        print(f"  ✗  Deleted {count} UPS Instance(s)")
    else:
        print("  —  No UPS Instances found")

    frappe.db.commit()


def _purge_all_isr_chain():
    """Cancel + delete all Service Requests, ISRs, SPSs, and Requested Procedures."""
    print("\n── Phase 2: Service Requests / ISRs / SPSs / Requested Procedures ─")

    # Healthcare Service Requests (tabService Request) — created alongside ISRs
    # by the healthcare app. Use direct SQL to skip all submitted-doc checks.
    count = frappe.db.sql("SELECT COUNT(*) FROM `tabService Request`")[0][0]
    if count:
        frappe.db.sql("DELETE FROM `tabService Request`")
        frappe.db.commit()
        print(f"  ✗  Deleted {count} Service Request(s)")
    else:
        print("  —  No Service Requests found")

    # Force-delete ISRs / SPSs / RPs via direct SQL — bypasses all docstatus
    # and link checks, which would fail for submitted records.
    for dt, table in [
        ("Imaging Service Request",  "tabImaging Service Request"),
        ("Scheduled Procedure Step", "tabScheduled Procedure Step"),
        ("Requested Procedure",      "tabRequested Procedure"),
    ]:
        count = frappe.db.sql(f"SELECT COUNT(*) FROM `{table}`")[0][0]
        if count:
            frappe.db.sql(f"DELETE FROM `{table}`")
            frappe.db.commit()
            print(f"  ✗  Deleted {count} {dt}(s)")
        else:
            print(f"  —  No {dt}s found")


def purge_all_patients():
    """
    Delete every Patient record except known framework test records.

    Safe to call independently::

        bench --site development.localhost execute \\
            healthcare.demo.teardown_all.purge_all_patients
    """
    frappe.set_user("Administrator")
    print("\n── Phase 3: Patients (all except system records) ────────────────")

    all_patients = frappe.get_all("Patient", pluck="name")
    to_delete = [p for p in all_patients if p not in _SYSTEM_PATIENTS]
    skipped   = [p for p in all_patients if p in _SYSTEM_PATIENTS]

    for name in skipped:
        print(f"  —  Skipped (system): {name}")

    for name in to_delete:
        frappe.delete_doc("Patient", name, force=True, ignore_permissions=True)
        frappe.db.commit()
        print(f"  ✗  Deleted Patient: {name}")

    if not to_delete:
        print("  —  No demo patients found")


def run():
    """Remove all demo data from the UPS Worklist Portal."""
    frappe.set_user("Administrator")

    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║          UPS Worklist Portal — Remove All Demo Data              ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    # ── Phase 1: all UPS Instances + Events ──────────────────────────────────
    _purge_all_ups_instances()

    # ── Phase 2: all ISRs / SPSs / RPs ───────────────────────────────────────
    _purge_all_isr_chain()

    # ── Phase 3: all demo patients ────────────────────────────────────────────
    purge_all_patients()

    # ── Phase 4: practitioners / procedure types & plans / AE Mappings ───────
    print("\n── Phase 4: Practitioners / Procedure Types & Plans / AE Mappings ─")
    try:
        from healthcare.ups_worklist_portal.demo import order_filling_examples
        # Call only the practitioner + master-data steps; ISR/patient steps
        # already handled above so they will silently report nothing to delete.
        order_filling_examples.teardown()
    except Exception as exc:
        print(f"\n  ⚠  order_filling_examples teardown error: {exc}")
        frappe.log_error(title="Demo teardown_all: order_filling_examples", message=str(exc))

    # ── Phase 5: AI AE Mappings (not in fixtures, added by aiw_i_use_cases) ──
    print("\n── Phase 5: AI AE Mappings ──────────────────────────────────────")
    try:
        from healthcare.demo.aiw_i_use_cases import _AI_AE_TITLES
        for ae in _AI_AE_TITLES:
            if frappe.db.exists("AE Mapping", ae):
                frappe.delete_doc("AE Mapping", ae, force=True, ignore_permissions=True)
                print(f"  ✗  Deleted AE Mapping: {ae}")
        frappe.db.commit()
    except Exception as exc:
        print(f"\n  ⚠  AI AE Mapping cleanup error: {exc}")
        frappe.log_error(title="Demo teardown_all: AI AE Mappings", message=str(exc))

    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║                  All demo data removed.                          ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()
