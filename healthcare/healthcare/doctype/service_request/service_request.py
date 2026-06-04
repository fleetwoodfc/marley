# Copyright (c) 2020, earthians and contributors
# For license information, please see license.txt


import json

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import now_datetime

from healthcare.controllers.service_request_controller import ServiceRequestController
from healthcare.healthcare.doctype.observation.observation import add_observation
from healthcare.healthcare.doctype.observation_template.observation_template import (
	get_observation_template_details,
)
from healthcare.healthcare.doctype.patient_insurance_coverage.patient_insurance_coverage import (
	make_insurance_coverage,
)
from healthcare.healthcare.doctype.sample_collection.sample_collection import (
	set_component_observation_data,
)


class ServiceRequest(ServiceRequestController):
	def validate(self):
		super().validate()
		if self.template_dt and self.template_dn and not self.codification_table:
			template_doc = frappe.get_doc(self.template_dt, self.template_dn)
			for mcode in template_doc.codification_table:
				self.append("codification_table", (frappe.copy_doc(mcode)).as_dict())

	def set_title(self):
		if frappe.flags.in_import and self.title:
			return
		self.title = f"{self.patient_name} - {self.template_dn}"

	def before_insert(self):
		self.status = "draft-Request Status"

		if self.amended_from:
			frappe.db.set_value("Service Request", self.amended_from, "status", "revoked-Request Status")

		if self.template_dt == "Observation Template" and self.template_dn:
			self.sample_collection_required = frappe.db.get_value(
				"Observation Template", self.template_dn, "sample_collection_required"
			)

	def on_submit(self):
		if self.insurance_policy and not self.insurance_coverage:
			self.make_insurance_coverage()

		# Bridge: Create Imaging Service Request for radiology orders
		if self.template_dt == "Radiology Procedure Template":
			self._create_imaging_service_request()

	def on_update_after_submit(self):
		if self.billing_status == "Pending" and self.insurance_policy and not self.insurance_coverage:
			self.make_insurance_coverage()

	def make_insurance_coverage(self):
		coverage = make_insurance_coverage(
			patient=self.patient,
			policy=self.insurance_policy,
			company=self.company,
			template_dt=self.template_dt,
			template_dn=self.template_dn,
			item_code=self.item_code,
			qty=self.quantity,
		)

		if coverage and coverage.get("coverage"):
			self.db_set(
				{
					"insurance_coverage": coverage.get("coverage"),
					"coverage_status": coverage.get("coverage_status"),
				}
			)

	def on_cancel(self):
		if self.insurance_coverage:
			coverage = frappe.get_doc("Patient Insurance Coverage", self.insurance_coverage)
			coverage.cancel()

		# Cancel linked ISR if it was created from this SR
		self._cancel_imaging_service_request()

	# ── Imaging Service Request bridge ────────────────────────────────────

	# Map human-readable RPT modality → DICOM modality code
	_MODALITY_MAP = {
		"X-Ray": "DX",
		"CT": "CT",
		"MRI": "MR",
		"Ultrasound": "US",
		"Fluoroscopy": "RF",
		"Nuclear Medicine": "NM",
		"PET": "PT",
		"Mammography": "MG",
	}

	# Map SR priority Code Value → ISR priority Select value
	_PRIORITY_MAP = {
		"Routine-Priority": "ROUTINE",
		"Urgent-Priority": "HIGH",
		"ASAP-Priority": "HIGH",
		"STAT-Priority": "STAT",
	}

	# Map RPT laterality → Procedure Type laterality
	_LATERALITY_MAP = {
		"N/A": "",
		"Left": "Left",
		"Right": "Right",
		"Bilateral": "Both",
	}

	def _create_imaging_service_request(self):
		"""
		Bridge a radiology Service Request to an Imaging Service Request.

		Flow:
		  1. Load the Radiology Procedure Template
		  2. Resolve or auto-create the DICOM Procedure Type
		  3. Create a Requested Procedure (standalone doc)
		  4. Create an ISR containing a Requested Procedure Link row
		  5. Submit the ISR (triggers accession number, SPS creation)
		  6. Store the back-references on both documents
		"""
		template = frappe.get_doc("Radiology Procedure Template", self.template_dn)

		# ── 1. Resolve Procedure Type ────────────────────────────────────
		procedure_type = self._resolve_procedure_type(template)

		# ── 2. Map priority ──────────────────────────────────────────────
		isr_priority = self._PRIORITY_MAP.get(self.priority, "ROUTINE")

		# ── 3. Create Requested Procedure ────────────────────────────────
		rp = frappe.get_doc({
			"doctype": "Requested Procedure",
			"procedure_type": procedure_type,
			"reason_for_request": self.comment or self.order_description or "",
			"scheduled_datetime": (
				f"{self.occurrence_date} {self.occurrence_time}"
				if self.occurrence_date
				else now_datetime()
			),
		})
		rp.insert(ignore_permissions=True)

		# ── 4. Build the ISR ─────────────────────────────────────────────
		isr = frappe.get_doc({
			"doctype": "Imaging Service Request",
			"order_datetime": now_datetime(),
			"priority": isr_priority,
			"patient": self.patient,
			"requesting_practitioner": self.practitioner,
			"clinical_indication": self.comment or self.order_description or "",
			"service_request": self.name,
			"radiology_procedure_template": self.template_dn,
			"requested_procedures": [
				{
					"requested_procedure": rp.name,
					"study_instance_uid": "",  # generated in ISR.validate()
				}
			],
		})
		isr.insert(ignore_permissions=True)
		isr.submit()

		# ── 5. Link ISR back to the Service Request ─────────────────────
		self.db_set({
			"order_reference_doctype": "Imaging Service Request",
			"order_reference_name": isr.name,
		})

		frappe.msgprint(
			_("Imaging Service Request {0} created with accession number {1}").format(
				frappe.utils.get_link_to_form("Imaging Service Request", isr.name),
				isr.accession_number,
			),
			indicator="green",
			alert=True,
		)

	def _resolve_procedure_type(self, template):
		"""
		Find or auto-create the DICOM Procedure Type for this RPT.

		Priority:
		  1. Explicit ``procedure_type`` link on the RPT
		  2. Matching Procedure Type by name
		  3. Auto-create a new Procedure Type from RPT attributes
		"""
		# 1. Explicit link
		if template.get("procedure_type"):
			return template.procedure_type

		# 2. Try name match
		if frappe.db.exists("Procedure Type", template.name):
			# persist the link for next time
			frappe.db.set_value(
				"Radiology Procedure Template", template.name,
				"procedure_type", template.name,
			)
			return template.name

		# 3. Auto-create
		dicom_modality = self._MODALITY_MAP.get(template.modality, "OT")
		pt_laterality = self._LATERALITY_MAP.get(template.laterality or "", "")
		pt = frappe.get_doc({
			"doctype": "Procedure Type",
			"procedure_name": template.name,
			"description": template.description,
			"default_modality": dicom_modality,
			"body_part": template.body_part,
			"laterality": pt_laterality,
			"contrast_required": "Required" if template.contrast_required else "No",
			"is_active": 1,
			"is_billable": template.is_billable,
			"item": template.item,
		})
		pt.insert(ignore_permissions=True)

		# persist the link on the RPT
		frappe.db.set_value(
			"Radiology Procedure Template", template.name,
			"procedure_type", pt.name,
		)

		frappe.msgprint(
			_("Auto-created Procedure Type {0}").format(
				frappe.utils.get_link_to_form("Procedure Type", pt.name)
			),
			indicator="blue",
			alert=True,
		)
		return pt.name

	def _cancel_imaging_service_request(self):
		"""Cancel the ISR that was created from this Service Request."""
		if self.order_reference_doctype != "Imaging Service Request":
			return
		if not self.order_reference_name:
			return

		isr = frappe.get_doc("Imaging Service Request", self.order_reference_name)
		if isr.docstatus == 1 and isr.status != "Cancelled":
			isr.cancel()
			frappe.msgprint(
				_("Imaging Service Request {0} cancelled").format(isr.name),
				indicator="orange",
				alert=True,
			)

	def set_order_details(self):
		if not self.template_dt and not self.template_dn:
			frappe.throw(
				_("Order Template Type and Order Template are mandatory to create Service Request"),
				title=_("Missing Mandatory Fields"),
			)

		template = frappe.get_doc(self.template_dt, self.template_dn)
		# set item code
		self.item_code = template.get("item")

		if not self.patient_care_type and template.get("patient_care_type"):
			self.patient_care_type = template.patient_care_type

		if not self.staff_role and template.get("staff_role"):
			self.staff_role = template.staff_role

		if not self.intent:
			self.intent = frappe.db.get_single_value("Healthcare Settings", "default_intent")

		if not self.priority:
			self.priority = frappe.db.get_single_value("Healthcare Settings", "default_priority")

	def update_invoice_details(self, qty):
		"""
		updates qty_invoiced and set billing status
		"""
		qty_invoiced = self.qty_invoiced + qty
		invoiced = 0
		if qty_invoiced == 0:
			status = "Pending"
		if qty_invoiced < self.quantity:
			status = "Partly Invoiced"
		else:
			invoiced = 1
			status = "Invoiced"

		self.db_set({"qty_invoiced": qty_invoiced, "billing_status": status})
		if self.template_dt == "Lab Test Template":
			dt = "Lab Test"
		elif self.template_dt == "Clinical Procedure Template":
			dt = "Clinical Procedure"
		elif self.template_dt == "Therapy Type":
			dt = "Therapy Session"
		elif self.template_dt == "Observation Template":
			dt = "Observation"
		elif self.template_dt == "Radiology Procedure Template":
			dt = "Radiology Procedure"
		else:
			return
		dt_name = frappe.db.get_value(dt, {"service_request": self.name})
		if dt_name:
			frappe.db.set_value(dt, dt_name, "invoiced", invoiced)


@frappe.whitelist()
def set_service_request_status(service_request, status):
	frappe.db.set_value("Service Request", service_request, "status", status)


@frappe.whitelist()
def make_clinical_procedure(service_request, appointment=None):
	if not service_request:
		return

	service_request = frappe.get_cached_doc("Service Request", service_request)

	if (
		frappe.db.get_single_value("Healthcare Settings", "process_service_request_only_if_paid")
		and service_request.billing_status != "Invoiced"
	):
		frappe.throw(
			_("Service Request need to be invoiced before proceeding"),
			title=_("Payment Required"),
		)

	procedure_template = frappe.get_doc("Clinical Procedure Template", service_request.template_dn)

	doc = frappe.new_doc("Clinical Procedure")
	doc.procedure_template = service_request.template_dn
	doc.service_request = service_request.name
	doc.appointment = appointment
	doc.company = service_request.company
	doc.patient = service_request.patient
	doc.patient_name = service_request.patient_name
	doc.patient_sex = service_request.patient_gender
	doc.patient_age = service_request.patient_age_data
	doc.inpatient_record = service_request.inpatient_record
	doc.practitioner = service_request.practitioner
	doc.start_date = service_request.occurrence_date
	doc.start_time = service_request.occurrence_time
	doc.medical_department = service_request.medical_department
	doc.invoiced = 1 if service_request.billing_status == "Invoiced" else 0
	doc.insurance_policy = service_request.insurance_policy
	doc.insurance_payor = service_request.insurance_payor
	doc.insurance_coverage = service_request.insurance_coverage
	doc.coverage_status = service_request.coverage_status
	doc.consume_stock = procedure_template.consume_stock
	doc.warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")

	if not doc.codification_table and procedure_template.codification_table:
		for code in procedure_template.codification_table:
			doc.append(
				"codification_table",
				(frappe.copy_doc(code)).as_dict(),
			)

	if not doc.items and procedure_template.items:
		for item in procedure_template.items:
			doc.append(
				"items",
				(frappe.copy_doc(item)).as_dict(),
			)

	return doc


@frappe.whitelist()
def make_lab_test(service_request):
	if not service_request:
		return

	service_request = frappe.get_cached_doc("Service Request", service_request)

	if (
		frappe.db.get_single_value("Healthcare Settings", "process_service_request_only_if_paid")
		and service_request.billing_status != "Invoiced"
	):
		frappe.throw(
			_("Service Request need to be invoiced before proceeding"),
			title=_("Payment Required"),
		)

	doc = frappe.new_doc("Lab Test")
	doc.template = service_request.template_dn
	doc.service_request = service_request.name
	doc.company = service_request.company
	doc.patient = service_request.patient
	doc.patient_name = service_request.patient_name
	doc.patient_sex = service_request.patient_gender
	doc.patient_age = service_request.patient_age_data
	doc.inpatient_record = service_request.inpatient_record
	doc.email = service_request.patient_email
	doc.mobile = service_request.patient_mobile
	doc.practitioner = service_request.practitioner
	doc.requesting_department = service_request.medical_department
	doc.date = service_request.occurrence_date
	doc.time = service_request.occurrence_time
	doc.invoiced = 1 if service_request.billing_status == "Invoiced" else 0
	doc.insurance_policy = service_request.insurance_policy
	doc.insurance_payor = service_request.insurance_payor
	doc.insurance_coverage = service_request.insurance_coverage
	doc.coverage_status = service_request.coverage_status

	return doc


@frappe.whitelist()
def make_observation(service_request, appointment=None):
	if not service_request:
		return

	service_request = frappe.get_cached_doc("Service Request", service_request)

	if (
		frappe.db.get_single_value("Healthcare Settings", "process_service_request_only_if_paid")
		and service_request.billing_status != "Invoiced"
	):
		frappe.throw(
			_("Service Request need to be invoiced before proceeding"),
			title=_("Payment Required"),
		)

	patient = frappe.get_doc("Patient", service_request.patient)
	template = frappe.get_doc("Observation Template", service_request.template_dn)

	sample_collection = ""
	name_ref_in_child = check_observation_sample_exist(service_request)

	if name_ref_in_child:
		return name_ref_in_child[0], name_ref_in_child[1], "New"
	else:
		exist_sample_collection = frappe.db.exists(
			"Sample Collection",
			{
				"reference_name": service_request.order_group,
				"docstatus": 0,
				"patient": service_request.patient,
			},
		)

	if template.has_component:
		if exist_sample_collection:
			sample_collection = frappe.get_doc("Sample Collection", exist_sample_collection)
		else:
			sample_collection = create_sample_collection(patient, service_request, appointment)

		# parent
		observation = create_observation(service_request, appointment)

		save_sample_collection = False
		(
			sample_reqd_component_obs,
			non_sample_reqd_component_obs,
		) = get_observation_template_details(service_request.template_dn)
		if len(non_sample_reqd_component_obs) > 0:
			for comp in non_sample_reqd_component_obs:
				add_observation(
					patient=service_request.patient,
					template=comp,
					doc="Patient Encounter",
					docname=service_request.order_group,
					parent=observation.name,
				)

		if len(sample_reqd_component_obs) > 0:
			save_sample_collection = True
			obs_template = frappe.get_doc("Observation Template", service_request.template_dn)
			data = set_component_observation_data(service_request.template_dn)
			# append parent template
			sample_collection.append(
				"observation_sample_collection",
				{
					"observation_template": service_request.template_dn,
					"sample": obs_template.sample,
					"sample_type": obs_template.sample_type,
					"container_closure_color": frappe.db.get_value(
						"Observation Template",
						service_request.template_dn,
						"container_closure_color",
					),
					"component_observations": json.dumps(data),
					"uom": obs_template.uom,
					"status": "Open",
					"sample_qty": obs_template.sample_qty,
					"component_observation_parent": observation.name,
					"service_request": service_request.name,
				},
			)

		if save_sample_collection:
			sample_collection.save(ignore_permissions=True)

	else:
		if template.get("sample_collection_required"):
			if exist_sample_collection:
				sample_collection = frappe.get_doc("Sample Collection", exist_sample_collection)
				sample_collection.append(
					"observation_sample_collection",
					{
						"observation_template": service_request.template_dn,
						"sample": template.sample,
						"sample_type": template.sample_type,
						"container_closure_color": frappe.db.get_value(
							"Observation Template",
							service_request.template_dn,
							"container_closure_color",
						),
						"uom": template.uom,
						"status": "Open",
						"sample_qty": template.sample_qty,
						"service_request": service_request.name,
					},
				)
				sample_collection.save(ignore_permissions=True)
			else:
				sample_collection = create_sample_collection(patient, service_request, appointment, template)
				sample_collection.save(ignore_permissions=True)
		else:
			observation = create_observation(service_request, appointment)

	diagnostic_report = frappe.db.exists("Diagnostic Report", {"docname": service_request.order_group})
	if not diagnostic_report:
		insert_diagnostic_report(service_request, sample_collection.name if sample_collection else None)

	if sample_collection:
		if diagnostic_report and not frappe.db.get_value(
			"Diagnostic Report", diagnostic_report, "sample_collection"
		):
			frappe.db.set_value(
				"Diagnostic Report", diagnostic_report, "sample_collection", sample_collection.name
			)
		return sample_collection.name, "Sample Collection"
	elif observation:
		return observation.name, "Observation"


def create_sample_collection(patient, service_request, appointment=None, template=None):
	sample_collection = frappe.new_doc("Sample Collection")
	sample_collection.patient = patient.name
	sample_collection.patient_age = patient.get_age()
	sample_collection.patient_sex = patient.sex
	sample_collection.appointment = appointment
	sample_collection.company = service_request.company
	sample_collection.reference_doc = service_request.source_doc
	sample_collection.reference_name = service_request.order_group
	if template:
		sample_collection.append(
			"observation_sample_collection",
			{
				"observation_template": service_request.template_dn,
				"sample": template.sample,
				"sample_type": template.sample_type,
				"container_closure_color": frappe.db.get_value(
					"Observation Template", service_request.template_dn, "container_closure_color"
				),
				"uom": template.uom,
				"sample_qty": template.sample_qty,
				"service_request": service_request.name,
			},
		)
		sample_collection.save(ignore_permissions=True)
	return sample_collection


def create_observation(service_request, appointment=None):
	doc = frappe.new_doc("Observation")
	doc.posting_datetime = now_datetime()
	doc.patient = service_request.patient
	doc.appointment = appointment
	doc.observation_template = service_request.template_dn
	doc.reference_doctype = "Patient Encounter"
	doc.reference_docname = service_request.order_group
	doc.service_request = service_request.name
	doc.insert()
	return doc


def insert_diagnostic_report(doc, sample_collection=None):
	diagnostic_report = frappe.new_doc("Diagnostic Report")
	diagnostic_report.category = "LAB"
	diagnostic_report.company = doc.company
	diagnostic_report.patient = doc.patient
	diagnostic_report.ref_doctype = doc.source_doc
	diagnostic_report.docname = doc.order_group
	diagnostic_report.practitioner = doc.practitioner
	diagnostic_report.sample_collection = sample_collection
	diagnostic_report.save(ignore_permissions=True)


def check_observation_sample_exist(service_request):
	name_ref_in_child = frappe.db.get_value(
		"Observation Sample Collection",
		{
			"service_request": service_request.name,
			"parenttype": "Sample Collection",
			"docstatus": ["!=", 2],
		},
		"parent",
	)
	if name_ref_in_child:
		return name_ref_in_child, "Sample Collection"
	else:
		exist_observation = frappe.db.exists(
			"Observation",
			{
				"service_request": service_request.name,
				"parent_observation": "",
				"docstatus": ["!=", 2],
			},
		)
		if exist_observation:
			return exist_observation, "Observation"


@frappe.whitelist()
def make_appointment(source_name, target_doc=None, ignore_permissions=False):
	def postprocess(source, target):
		set_missing_values(source, target)

	def set_missing_values(source, target):
		target.department = frappe.db.get_value(
			"Healthcare Practitioner", source.referred_to_practitioner, "department"
		)

	doclist = get_mapped_doc(
		"Service Request",
		source_name,
		{
			"Service Request": {
				"doctype": "Patient Appointment",
				"field_map": {
					"name": "service_request",
					"referred_to_practitioner": "practitioner",
					"template_dn": "appointment_type",
					"source_doc": "reference_doctype",
					"order_group": "reference_docname",
				},
				"field_no_map": ["naming_series", "status"],
			},
		},
		target_doc,
		postprocess,
		ignore_permissions=ignore_permissions,
	)

	return doclist


@frappe.whitelist()
def make_radiology_procedure(service_request, appointment=None):
	"""Create a Radiology Procedure from a Service Request."""
	if not service_request:
		return

	service_request = frappe.get_cached_doc("Service Request", service_request)

	if service_request.template_dt != "Radiology Procedure Template":
		frappe.throw(
			_("Service Request is not for Radiology Procedure"),
			title=_("Invalid Template Type"),
		)

	if (
		frappe.db.get_single_value("Healthcare Settings", "process_service_request_only_if_paid")
		and service_request.billing_status != "Invoiced"
	):
		frappe.throw(
			_("Service Request need to be invoiced before proceeding"),
			title=_("Payment Required"),
		)

	radiology_template = frappe.get_doc("Radiology Procedure Template", service_request.template_dn)

	doc = frappe.new_doc("Radiology Procedure")
	doc.radiology_template = service_request.template_dn
	doc.service_request = service_request.name
	doc.appointment = appointment
	doc.company = service_request.company
	doc.patient = service_request.patient
	doc.patient_name = service_request.patient_name
	doc.patient_sex = service_request.patient_gender
	doc.patient_age = service_request.patient_age_data
	doc.inpatient_record = service_request.inpatient_record
	doc.practitioner = service_request.practitioner
	doc.start_date = service_request.occurrence_date
	doc.start_time = service_request.occurrence_time
	doc.medical_department = service_request.medical_department or radiology_template.medical_department
	doc.invoiced = 1 if service_request.billing_status == "Invoiced" else 0
	doc.status = "Scheduled"

	# Copy radiology-specific fields from template
	doc.modality = radiology_template.modality
	doc.body_part = radiology_template.body_part
	doc.laterality = radiology_template.laterality
	doc.contrast_used = radiology_template.contrast_required
	doc.contrast_type = radiology_template.contrast_type

	# Copy codification table
	if not doc.codification_table and radiology_template.codification_table:
		for code in radiology_template.codification_table:
			doc.append(
				"codification_table",
				(frappe.copy_doc(code)).as_dict(),
			)

	return doc
