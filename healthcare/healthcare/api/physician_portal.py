import json
import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.utils import getdate, now_datetime


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _get_practitioner_for_session():
    """Return Healthcare Practitioner name linked to the logged-in user, or None."""
    user = frappe.session.user
    if not user or user == "Guest":
        return None
    practitioner = frappe.db.get_value(
        "Healthcare Practitioner", {"user_id": user, "status": "Active"}, "name"
    )
    if not practitioner:
        # Fallback: try matching by email_id
        practitioner = frappe.db.get_value(
            "Healthcare Practitioner", {"email_id": user, "status": "Active"}, "name"
        )
    if not practitioner:
        # Last resort: return the first active practitioner (for dev/demo environments)
        practitioner = frappe.db.get_value(
            "Healthcare Practitioner", {"status": "Active"}, "name"
        )
    return practitioner


def _get_default_company():
    return (
        frappe.defaults.get_user_default("company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )


# ---------------------------------------------------------------------------
# Portal access control
# ---------------------------------------------------------------------------

PORTAL_ROLES = {"Administrator", "Healthcare Administrator", "Physician", "System Manager"}


@frappe.whitelist(allow_guest=True)
def get_session_user():
    """Return session user info and portal access flag.

    Allowed by guests so the frontend can decide whether to show
    the login page or the main portal.
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return {"user": "Guest", "has_portal_access": False}

    roles = set(frappe.get_roles(user))
    has_access = bool(roles & PORTAL_ROLES)

    practitioner = _get_practitioner_for_session()
    full_name = frappe.db.get_value("User", user, "full_name") or user

    return {
        "user": user,
        "full_name": full_name,
        "roles": list(roles & PORTAL_ROLES),
        "has_portal_access": has_access,
        "practitioner": practitioner,
    }


# ---------------------------------------------------------------------------
# Portal API — settings & identity
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_logged_in_practitioner():
    """Return practitioner details for the current session user."""
    name = _get_practitioner_for_session()
    if not name:
        return None
    doc = frappe.get_doc("Healthcare Practitioner", name)
    return {
        "name": doc.name,
        "practitioner_name": doc.practitioner_name,
        "department": doc.department,
        "image": doc.image,
    }


@frappe.whitelist()
def get_settings():
    """Return Healthcare Settings relevant for the physician portal."""
    return frappe.get_single("Healthcare Settings")


# ---------------------------------------------------------------------------
# Patient management
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_patients(search=None, page=1, page_size=20):
    """Return paginated patient list. Optionally filter by search term."""
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    start = (page - 1) * page_size

    filters = {"status": "Active"}

    Patient = frappe.qb.DocType("Patient")
    query = (
        frappe.qb.from_(Patient)
        .select(
            Patient.name,
            Patient.patient_name,
            Patient.sex,
            Patient.dob,
            Patient.email,
            Patient.mobile,
            Patient.uid,
            Patient.image,
            Patient.status,
        )
        .where(Patient.status == "Active")
        .orderby(Patient.patient_name, order=Order.asc)
        .limit(page_size)
        .offset(start)
    )

    if search:
        s = f"%{search}%"
        query = query.where(
            (Patient.patient_name.like(s))
            | (Patient.uid.like(s))
            | (Patient.email.like(s))
            | (Patient.mobile.like(s))
            | (Patient.name.like(s))
        )

    patients = query.run(as_dict=True)

    # Get total count for pagination
    count_query = frappe.qb.from_(Patient).select(frappe.qb.terms.ValueWrapper(1)).where(Patient.status == "Active")
    if search:
        s = f"%{search}%"
        count_query = count_query.where(
            (Patient.patient_name.like(s))
            | (Patient.uid.like(s))
            | (Patient.email.like(s))
            | (Patient.mobile.like(s))
            | (Patient.name.like(s))
        )
    total = len(count_query.run())

    return {
        "patients": patients,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@frappe.whitelist()
def get_patient_detail(patient):
    """Return full patient record with recent appointments and orders."""
    if not frappe.db.exists("Patient", patient):
        frappe.throw(_("Patient not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Patient", patient)
    patient_data = {
        "name": doc.name,
        "patient_name": doc.patient_name,
        "sex": doc.sex,
        "dob": doc.dob,
        "blood_group": doc.blood_group,
        "email": doc.email,
        "mobile": doc.mobile,
        "uid": doc.uid,
        "image": doc.image,
        "status": doc.status,
    }

    # Recent appointments
    appointments = frappe.get_all(
        "Patient Appointment",
        filters={"patient": patient},
        fields=[
            "name", "appointment_date", "appointment_time", "status",
            "practitioner", "practitioner_name", "department", "duration",
        ],
        order_by="appointment_date desc",
        limit=10,
    )

    # Recent service requests (orders)
    orders = frappe.get_all(
        "Service Request",
        filters={"patient": patient, "docstatus": ["!=", 2]},
        fields=[
            "name", "order_date", "order_time", "status",
            "template_dt", "template_dn", "practitioner",
            "order_description", "billing_status",
        ],
        order_by="order_date desc",
        limit=10,
    )

    return {
        "patient": patient_data,
        "appointments": appointments,
        "orders": orders,
    }


@frappe.whitelist()
def register_patient(first_name, last_name=None, sex="Male", dob=None,
                     email=None, mobile=None, uid=None):
    """Register a new patient and return the created document name."""
    doc = frappe.new_doc("Patient")
    doc.first_name = first_name
    doc.last_name = last_name or ""
    doc.patient_name = f"{first_name} {last_name}".strip() if last_name else first_name
    doc.sex = sex or "Male"
    if dob:
        doc.dob = getdate(dob)
    if email:
        doc.email = email
    if mobile:
        doc.mobile = mobile
    if uid:
        doc.uid = uid

    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "patient_name": doc.patient_name}


# ---------------------------------------------------------------------------
# Diagnostic order management
# ---------------------------------------------------------------------------

# Map human-readable status labels ↔ Code Value names for Service Requests
_SR_STATUS_MAP = {
    "Draft": "draft-Request Status",
    "Active": "active-Request Status",
    "On Hold": "on-hold-Request Status",
    "Completed": "completed-Request Status",
    "Revoked": "revoked-Request Status",
    "Unknown": "unknown-Request Status",
}
_SR_STATUS_DISPLAY = {v: k for k, v in _SR_STATUS_MAP.items()}

_SR_PRIORITY_DISPLAY = {
    "Routine-Priority": "Routine",
    "Urgent-Priority": "Urgent",
    "ASAP-Priority": "ASAP",
    "STAT-Priority": "STAT",
}


@frappe.whitelist()
def get_orders(practitioner=None, patient=None, status=None,
               page=1, page_size=20):
    """Return paginated Service Requests (diagnostic/imaging orders).

    Filters:
    - practitioner: restrict to orders by a specific practitioner
    - patient: restrict to a specific patient
    - status: filter by order status (human-readable: Draft, Active, etc.)
    - page/page_size: pagination
    """
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    start = (page - 1) * page_size

    # Map the human-readable status filter to the Code Value stored in DB
    status_code = _SR_STATUS_MAP.get(status, status) if status else None

    SR = frappe.qb.DocType("Service Request")
    Patient = frappe.qb.DocType("Patient")
    Practitioner = frappe.qb.DocType("Healthcare Practitioner")

    query = (
        frappe.qb.from_(SR)
        .left_join(Patient).on(SR.patient == Patient.name)
        .left_join(Practitioner).on(SR.practitioner == Practitioner.name)
        .select(
            SR.name,
            SR.order_date,
            SR.order_time,
            SR.status,
            SR.priority,
            SR.patient,
            SR.practitioner,
            SR.template_dt,
            SR.template_dn,
            SR.order_description,
            SR.billing_status,
            SR.docstatus,
            Patient.patient_name,
            Patient.image.as_("patient_image"),
            Practitioner.practitioner_name,
        )
        .where(SR.docstatus != 2)
        .orderby(SR.order_date, order=Order.desc)
        .orderby(SR.order_time, order=Order.desc)
        .limit(page_size)
        .offset(start)
    )

    if practitioner:
        query = query.where(SR.practitioner == practitioner)
    elif not patient:
        # Default: scope to logged-in practitioner if no explicit filters
        session_practitioner = _get_practitioner_for_session()
        if session_practitioner:
            query = query.where(SR.practitioner == session_practitioner)

    if patient:
        query = query.where(SR.patient == patient)

    if status_code:
        query = query.where(SR.status == status_code)

    orders = query.run(as_dict=True)

    # Convert Code Value status/priority to human-readable labels
    for order in orders:
        order["status"] = _SR_STATUS_DISPLAY.get(order.get("status"), order.get("status", ""))
        order["priority"] = _SR_PRIORITY_DISPLAY.get(order.get("priority"), order.get("priority", ""))

    # Count total
    count_q = frappe.qb.from_(SR).select(frappe.qb.terms.ValueWrapper(1)).where(SR.docstatus != 2)
    if practitioner:
        count_q = count_q.where(SR.practitioner == practitioner)
    elif not patient:
        session_practitioner = _get_practitioner_for_session()
        if session_practitioner:
            count_q = count_q.where(SR.practitioner == session_practitioner)
    if patient:
        count_q = count_q.where(SR.patient == patient)
    if status_code:
        count_q = count_q.where(SR.status == status_code)
    total = len(count_q.run())

    return {
        "orders": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@frappe.whitelist()
def get_order_detail(order_name):
    """Return detailed Service Request with template info."""
    if not frappe.db.exists("Service Request", order_name):
        frappe.throw(_("Order not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Service Request", order_name)
    result = {
        "name": doc.name,
        "order_date": doc.order_date,
        "order_time": doc.order_time,
        "status": _SR_STATUS_DISPLAY.get(doc.status, doc.status),
        "priority": _SR_PRIORITY_DISPLAY.get(doc.priority, doc.priority),
        "patient": doc.patient,
        "patient_name": frappe.db.get_value("Patient", doc.patient, "patient_name") if doc.patient else None,
        "practitioner": doc.practitioner,
        "practitioner_name": frappe.db.get_value("Healthcare Practitioner", doc.practitioner, "practitioner_name") if doc.practitioner else None,
        "template_dt": doc.template_dt,
        "template_dn": doc.template_dn,
        "order_description": doc.order_description,
        "billing_status": doc.billing_status,
        "company": doc.company,
        "docstatus": doc.docstatus,
        # Raw values needed to pre-populate the edit form
        "raw": {
            "priority": doc.priority,
            "order_date": str(doc.order_date) if doc.order_date else None,
            "order_time": str(doc.order_time) if doc.order_time else None,
            "template_dt": doc.template_dt,
            "template_dn": doc.template_dn,
            "order_description": doc.order_description or "",
        },
    }

    # Add template details if available
    if doc.template_dt and doc.template_dn and frappe.db.exists(doc.template_dt, doc.template_dn):
        tpl = frappe.get_doc(doc.template_dt, doc.template_dn)
        result["template"] = {
            "doctype": doc.template_dt,
            "name": tpl.name,
            "label": getattr(tpl, "template", None) or getattr(tpl, "observation", None) or tpl.name,
        }

    return result


@frappe.whitelist()
def get_imaging_service_requests(patient=None, status=None, page=1, page_size=20):
    """Return Imaging Service Requests with requested procedures."""
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    start = (page - 1) * page_size

    ISR = frappe.qb.DocType("Imaging Service Request")
    Patient = frappe.qb.DocType("Patient")

    query = (
        frappe.qb.from_(ISR)
        .left_join(Patient).on(ISR.patient == Patient.name)
        .select(
            ISR.name,
            ISR.accession_number,
            ISR.order_datetime,
            ISR.status,
            ISR.priority,
            ISR.patient,
            ISR.requesting_practitioner,
            ISR.requesting_practitioner_name,
            ISR.service_request,
            ISR.radiology_procedure_template,
            ISR.clinical_indication,
            ISR.docstatus,
            Patient.patient_name,
            Patient.image.as_("patient_image"),
        )
        .orderby(ISR.creation, order=Order.desc)
        .limit(page_size)
        .offset(start)
    )

    if patient:
        query = query.where(ISR.patient == patient)
    if status:
        query = query.where(ISR.status == status)

    requests = query.run(as_dict=True)

    # Attach requested procedures to each ISR via the Requested Procedure Link child table
    for req in requests:
        rp_links = frappe.get_all(
            "Requested Procedure Link",
            filters={"parent": req["name"], "parenttype": "Imaging Service Request"},
            fields=["requested_procedure", "study_instance_uid"],
        )
        procedures = []
        for link in rp_links:
            if link.requested_procedure and frappe.db.exists("Requested Procedure", link.requested_procedure):
                rp = frappe.get_doc("Requested Procedure", link.requested_procedure)
                procedures.append({
                    "name": rp.name,
                    "procedure_type": rp.procedure_type,
                    "procedure_description": rp.procedure_description,
                    "modality": rp.modality,
                    "study_instance_uid": link.study_instance_uid or rp.study_instance_uid,
                    "status": rp.status,
                    "scheduled_datetime": str(rp.scheduled_datetime) if rp.scheduled_datetime else None,
                })
        req["requested_procedures"] = procedures

    count_q = frappe.qb.from_(ISR).select(frappe.qb.terms.ValueWrapper(1))
    if patient:
        count_q = count_q.where(ISR.patient == patient)
    if status:
        count_q = count_q.where(ISR.status == status)
    total = len(count_q.run())

    return {
        "requests": requests,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@frappe.whitelist()
def create_service_request(patient, template_dt, template_dn, priority="Routine",
                           occurrence=None, clinical_question=None,
                           submit_request=False):
    """Create a Service Request from the physician portal.

    Args:
        patient: Patient doctype name
        template_dt: Template Doctype (e.g. 'Radiology Procedure Template', 'Observation Template')
        template_dn: Template document name
        priority: 'Routine', 'Urgent', or 'STAT'
        occurrence: Optional scheduled datetime
        clinical_question: Reason / clinical question
        submit_request: If truthy, submit the document after creation
    """
    if not frappe.db.exists("Patient", patient):
        frappe.throw(_("Patient not found"))
    if not frappe.db.exists(template_dt, template_dn):
        frappe.throw(_(f"Template {template_dn} not found"))

    practitioner = _get_practitioner_for_session()
    if not practitioner:
        frappe.throw(_("No active Healthcare Practitioner found. Please link your user to a practitioner."))
    company = _get_default_company()

    doc = frappe.new_doc("Service Request")
    doc.company = company
    doc.patient = patient
    doc.practitioner = practitioner
    doc.template_dt = template_dt
    doc.template_dn = template_dn
    doc.order_date = getdate(occurrence) if occurrence else frappe.utils.today()
    doc.order_description = clinical_question or ""

    try:
        doc.order_time = now_datetime().strftime("%H:%M:%S")
    except Exception:
        doc.order_time = "00:00:00"

    # Map user-friendly priority names to Code Value names
    priority_map = {
        "Routine": "Routine-Priority",
        "Urgent": "Urgent-Priority",
        "ASAP": "ASAP-Priority",
        "Stat": "STAT-Priority",
        "STAT": "STAT-Priority",
    }
    if priority:
        mapped = priority_map.get(priority, priority)
        if frappe.db.exists("Code Value", mapped):
            doc.priority = mapped
        elif frappe.db.exists("Code Value", priority):
            doc.priority = priority
        # else: leave unset, set_order_details will apply default

    doc.insert(ignore_permissions=True)

    if submit_request:
        try:
            frappe.flags.ignore_permissions = True
            doc.submit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "physician_portal.create_service_request.submit")
        finally:
            frappe.flags.ignore_permissions = False

    return {
        "name": doc.name,
        "status": doc.status,
        "order_date": doc.order_date,
    }


@frappe.whitelist()
def update_service_request(order_name, priority=None, occurrence=None,
                          clinical_question=None, template_dt=None,
                          template_dn=None, submit_request=False):
    """Update an existing Draft Service Request from the physician portal.

    Args:
        order_name: Name of the Service Request to update
        priority: Optional priority code value (e.g. 'Routine-Priority')
        occurrence: Optional scheduled date or datetime string
        clinical_question: Updated reason / clinical question / notes
        template_dt: Optional new template DocType
        template_dn: Optional new template document name
        submit_request: If truthy, submit the document after saving
    """
    if not frappe.db.exists("Service Request", order_name):
        frappe.throw(_("Order not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Service Request", order_name)

    if doc.docstatus != 0:
        frappe.throw(_("Only Draft orders can be edited"))

    if priority is not None:
        priority_map = {
            "Routine": "Routine-Priority",
            "Urgent": "Urgent-Priority",
            "ASAP": "ASAP-Priority",
            "Stat": "STAT-Priority",
            "STAT": "STAT-Priority",
        }
        mapped = priority_map.get(priority, priority)
        if frappe.db.exists("Code Value", mapped):
            doc.priority = mapped
        elif frappe.db.exists("Code Value", priority):
            doc.priority = priority

    if occurrence is not None:
        if occurrence:
            doc.order_date = getdate(occurrence)
        else:
            doc.order_date = frappe.utils.today()

    if clinical_question is not None:
        doc.order_description = clinical_question

    if template_dt and template_dn:
        if not frappe.db.exists(template_dt, template_dn):
            frappe.throw(_(f"Template {template_dn} not found"))
        doc.template_dt = template_dt
        doc.template_dn = template_dn

    doc.save(ignore_permissions=True)

    if submit_request:
        try:
            frappe.flags.ignore_permissions = True
            doc.submit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "physician_portal.update_service_request.submit")
        finally:
            frappe.flags.ignore_permissions = False

    return {
        "name": doc.name,
        "status": _SR_STATUS_DISPLAY.get(doc.status, doc.status),
        "order_date": str(doc.order_date) if doc.order_date else None,
    }


@frappe.whitelist()
def get_orderable_templates(search=None, template_type=None):
    """Return available templates that can be ordered.

    Searches across Radiology Procedure Template, Observation Template,
    Clinical Procedure Template, and Lab Test Template.
    """
    results = []
    template_configs = [
        {
            "doctype": "Radiology Procedure Template",
            "name_field": "template",
            "type_label": "Radiology",
            "extra_fields": ["modality"],
        },
        {
            "doctype": "Observation Template",
            "name_field": "observation",
            "type_label": "Observation",
            "extra_fields": ["observation_category"],
        },
        {
            "doctype": "Clinical Procedure Template",
            "name_field": "template",
            "type_label": "Clinical Procedure",
            "extra_fields": [],
        },
        {
            "doctype": "Lab Test Template",
            "name_field": "lab_test_name",
            "type_label": "Lab Test",
            "extra_fields": ["lab_test_group"],
        },
    ]

    if template_type:
        # Accept both short keys and full DocType names
        type_map = {
            "radiology": "Radiology Procedure Template",
            "observation": "Observation Template",
            "clinical": "Clinical Procedure Template",
            "lab": "Lab Test Template",
            "radiology procedure template": "Radiology Procedure Template",
            "observation template": "Observation Template",
            "clinical procedure template": "Clinical Procedure Template",
            "lab test template": "Lab Test Template",
        }
        target = type_map.get(template_type.lower().strip(), template_type)
        if target:
            template_configs = [c for c in template_configs if c["doctype"] == target]

    for config in template_configs:
        dt = config["doctype"]
        if not frappe.db.table_exists(dt):
            continue

        filters = {}
        fields = ["name"] + config["extra_fields"]

        if search:
            filters["name"] = ["like", f"%{search}%"]

        try:
            templates = frappe.get_all(dt, filters=filters, fields=fields, limit=50)
            for t in templates:
                results.append({
                    "name": t.name,
                    "template_dt": dt,
                    "template_dn": t.name,
                    "label": t.name,
                    "type_label": config["type_label"],
                    **{k: t.get(k) for k in config["extra_fields"] if t.get(k)},
                })
        except Exception:
            pass

    # Sort alphabetically
    results.sort(key=lambda r: r.get("label", ""))
    return results


@frappe.whitelist()
def get_practitioner_appointments(practitioner=None, page=1, page_size=20):
    """Return appointments for a practitioner with patient details."""
    practitioner = practitioner or _get_practitioner_for_session()
    if not practitioner:
        return {"appointments": [], "total": 0, "page": 1, "page_size": page_size, "total_pages": 1}

    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    start = (page - 1) * page_size

    Appointment = frappe.qb.DocType("Patient Appointment")
    Patient = frappe.qb.DocType("Patient")

    query = (
        frappe.qb.from_(Appointment)
        .left_join(Patient).on(Appointment.patient == Patient.name)
        .select(
            Appointment.name,
            Appointment.patient,
            Appointment.appointment_date,
            Appointment.appointment_time,
            Appointment.status,
            Appointment.duration,
            Appointment.department,
            Appointment.practitioner_name,
            Patient.patient_name,
            Patient.image.as_("patient_image"),
            Patient.sex,
        )
        .where(Appointment.practitioner == practitioner)
        .where(Appointment.status != "Cancelled")
        .orderby(Appointment.appointment_date, order=Order.desc)
        .orderby(Appointment.appointment_time, order=Order.desc)
        .limit(page_size)
        .offset(start)
    )

    appointments = query.run(as_dict=True)

    total = frappe.db.count("Patient Appointment", {
        "practitioner": practitioner,
        "status": ["!=", "Cancelled"],
    })

    return {
        "appointments": appointments,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


# ---------------------------------------------------------------------------
# Diagnostic Report management
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_diagnostic_reports(patient=None, status=None, practitioner=None,
                           page=1, page_size=20):
    """Return paginated Diagnostic Reports.

    Filters:
    - patient: restrict to a specific patient
    - status: filter by report status (Open, Pending Review, Approved, etc.)
    - practitioner: restrict to a specific practitioner
    - page/page_size: pagination
    """
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    start = (page - 1) * page_size

    DR = frappe.qb.DocType("Diagnostic Report")
    Patient = frappe.qb.DocType("Patient")
    Practitioner = frappe.qb.DocType("Healthcare Practitioner")

    query = (
        frappe.qb.from_(DR)
        .left_join(Patient).on(DR.patient == Patient.name)
        .left_join(Practitioner).on(DR.practitioner == Practitioner.name)
        .select(
            DR.name,
            DR.naming_series,
            DR.patient,
            DR.patient_name,
            DR.gender,
            DR.age,
            DR.practitioner,
            DR.practitioner_name,
            DR.status,
            DR.ref_doctype,
            DR.docname,
            DR.creation,
            DR.modified,
            Patient.image.as_("patient_image"),
            Practitioner.practitioner_name.as_("practitioner_display"),
        )
        .orderby(DR.creation, order=Order.desc)
        .limit(page_size)
        .offset(start)
    )

    if practitioner:
        query = query.where(DR.practitioner == practitioner)
    elif not patient:
        # Admins see all reports; physicians see only their own
        user_roles = set(frappe.get_roles(frappe.session.user))
        if not user_roles & {"Administrator", "System Manager", "Healthcare Administrator"}:
            session_practitioner = _get_practitioner_for_session()
            if session_practitioner:
                query = query.where(DR.practitioner == session_practitioner)

    if patient:
        query = query.where(DR.patient == patient)

    if status:
        query = query.where(DR.status == status)

    reports = query.run(as_dict=True)

    # Count total
    count_q = frappe.qb.from_(DR).select(frappe.qb.terms.ValueWrapper(1))
    if practitioner:
        count_q = count_q.where(DR.practitioner == practitioner)
    elif not patient:
        user_roles = set(frappe.get_roles(frappe.session.user))
        if not user_roles & {"Administrator", "System Manager", "Healthcare Administrator"}:
            session_practitioner = _get_practitioner_for_session()
            if session_practitioner:
                count_q = count_q.where(DR.practitioner == session_practitioner)
    if patient:
        count_q = count_q.where(DR.patient == patient)
    if status:
        count_q = count_q.where(DR.status == status)
    total = len(count_q.run())

    return {
        "reports": reports,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@frappe.whitelist()
def get_diagnostic_report_detail(report_name):
    """Return detailed Diagnostic Report with observations."""
    if not frappe.db.exists("Diagnostic Report", report_name):
        frappe.throw(_("Diagnostic Report not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Diagnostic Report", report_name)
    result = {
        "name": doc.name,
        "patient": doc.patient,
        "patient_name": doc.patient_name,
        "gender": doc.gender,
        "age": doc.age,
        "practitioner": doc.practitioner,
        "practitioner_name": doc.practitioner_name,
        "status": doc.status,
        "ref_doctype": doc.ref_doctype,
        "docname": doc.docname,
        "creation": str(doc.creation) if doc.creation else None,
        "modified": str(doc.modified) if doc.modified else None,
    }

    # Fetch observations linked to this DR's patient
    # Observations are top-level (parent_observation = '') and not cancelled
    observations = []
    obs_list = frappe.get_all(
        "Observation",
        filters={
            "patient": doc.patient,
            "parent_observation": ["in", ["", None]],
            "status": ["!=", "Cancelled"],
        },
        fields=[
            "name", "observation_template", "observation_category",
            "permitted_data_type", "status", "posting_date",
            "healthcare_practitioner", "practitioner_name",
            "result_data", "result_text", "result_float",
            "result_boolean", "result_select", "result_attach",
            "has_component", "service_request",
            "permitted_unit", "reference", "note",
            "time_of_result", "time_of_approval",
        ],
        order_by="creation asc",
    )

    for obs in obs_list:
        obs_entry = {
            "name": obs.name,
            "template": obs.observation_template,
            "category": obs.observation_category,
            "data_type": obs.permitted_data_type,
            "status": obs.status,
            "posting_date": str(obs.posting_date) if obs.posting_date else None,
            "practitioner": obs.practitioner_name or obs.healthcare_practitioner,
            "unit": obs.permitted_unit,
            "reference_range": obs.reference,
            "note": obs.note,
            "result_time": str(obs.time_of_result) if obs.time_of_result else None,
            "approval_time": str(obs.time_of_approval) if obs.time_of_approval else None,
            "service_request": obs.service_request,
        }

        # Set result value based on data type
        if obs.permitted_data_type == "Quantity":
            obs_entry["result"] = obs.result_float if obs.result_float else obs.result_data
        elif obs.permitted_data_type == "Boolean":
            obs_entry["result"] = obs.result_boolean
        elif obs.permitted_data_type == "Select":
            obs_entry["result"] = obs.result_select or obs.result_data
        elif obs.permitted_data_type == "Text":
            obs_entry["result"] = obs.result_text or obs.result_data
        elif obs.permitted_data_type == "Attach":
            obs_entry["result"] = obs.result_attach
        else:
            obs_entry["result"] = obs.result_data

        # Get child observations if parent has components
        if obs.has_component:
            children = frappe.get_all(
                "Observation",
                filters={
                    "parent_observation": obs.name,
                    "status": ["!=", "Cancelled"],
                },
                fields=[
                    "name", "observation_template", "permitted_data_type",
                    "status", "result_data", "result_float", "result_text",
                    "result_boolean", "result_select", "result_attach",
                    "permitted_unit", "reference",
                ],
                order_by="observation_idx asc",
            )
            obs_entry["components"] = []
            for child in children:
                child_entry = {
                    "name": child.name,
                    "template": child.observation_template,
                    "data_type": child.permitted_data_type,
                    "status": child.status,
                    "unit": child.permitted_unit,
                    "reference_range": child.reference,
                }
                if child.permitted_data_type == "Quantity":
                    child_entry["result"] = child.result_float if child.result_float else child.result_data
                elif child.permitted_data_type == "Text":
                    child_entry["result"] = child.result_text or child.result_data
                elif child.permitted_data_type == "Boolean":
                    child_entry["result"] = child.result_boolean
                elif child.permitted_data_type == "Select":
                    child_entry["result"] = child.result_select or child.result_data
                else:
                    child_entry["result"] = child.result_data
                obs_entry["components"].append(child_entry)

        observations.append(obs_entry)

    result["observations"] = observations
    return result


# ---------------------------------------------------------------------------
# Diagnostic Report – Status Update
# ---------------------------------------------------------------------------

_VALID_DR_STATUSES = {"Open", "Pending Review", "Partially Approved", "Approved", "Rejected"}

# Define which transitions are allowed from each status
_DR_TRANSITIONS = {
    "Open":               {"Pending Review"},
    "Pending Review":     {"Approved", "Rejected", "Open"},
    "Partially Approved": {"Approved", "Rejected"},
    "Approved":           set(),           # terminal – no further transitions
    "Rejected":           {"Open"},        # allow re-opening
}


@frappe.whitelist()
def update_diagnostic_report_status(report_name, status):
    """
    Update the status of a Diagnostic Report.

    When the new status is Approved or Rejected the controller helper
    ``set_observation_status`` is called so that linked observations are
    cascaded accordingly (submitted / cancelled+cloned).
    """
    from healthcare.healthcare.doctype.diagnostic_report.diagnostic_report import (
        set_observation_status,
    )

    if status not in _VALID_DR_STATUSES:
        frappe.throw(
            _("Invalid status '{0}'. Must be one of: {1}").format(
                status, ", ".join(sorted(_VALID_DR_STATUSES))
            )
        )

    if not frappe.db.exists("Diagnostic Report", report_name):
        frappe.throw(_("Diagnostic Report not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("Diagnostic Report", report_name)

    # Check allowed transitions
    allowed_next = _DR_TRANSITIONS.get(doc.status, set())
    if status not in allowed_next:
        frappe.throw(
            _("Cannot change status from '{0}' to '{1}'. Allowed: {2}").format(
                doc.status,
                status,
                ", ".join(sorted(allowed_next)) if allowed_next else "none (terminal status)",
            )
        )

    doc.status = status
    doc.save(ignore_permissions=False)

    # Cascade to linked observations when approving / rejecting
    if status in ("Approved", "Rejected"):
        set_observation_status(report_name)

    frappe.db.commit()

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_allowed_status_transitions(report_name):
    """Return the list of statuses the DR can transition to from its current state."""
    if not frappe.db.exists("Diagnostic Report", report_name):
        frappe.throw(_("Diagnostic Report not found"), frappe.DoesNotExistError)

    current = frappe.db.get_value("Diagnostic Report", report_name, "status")
    allowed = sorted(_DR_TRANSITIONS.get(current, set()))
    return {"current_status": current, "allowed": allowed}
