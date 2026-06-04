"""
Demo data for the Report Template Manager feature (014).

Run with:
  bench --site development.localhost execute \
    healthcare.radiology_reporting.demo_data.load --kwargs='{"dry_run": false}'

Or from bench console:
  from healthcare.radiology_reporting.demo_data import load; load()
"""

import frappe
from frappe.utils import today

# ---------------------------------------------------------------------------
# MRRT template content snippets
# ---------------------------------------------------------------------------

def _mrrt(title, sections):
	"""Build minimal valid MRRT HTML from a title and list of (id, heading, body) tuples."""
	section_html = "\n".join(
		f"""    <section data-section-id="{sid}">
      <header>{heading}</header>
      <p>{body}</p>
    </section>"""
		for sid, heading, body in sections
	)
	return f"""<html>
  <head>
    <title>{title}</title>
    <meta name="dcterms.title" content="{title}" />
    <meta name="dcterms.language" content="en" />
    <meta name="dcterms.type" content="IMAGE_REPORT_TEMPLATE" />
  </head>
  <body>
    <section data-section-id="report-header">
      <header>{title}</header>
    </section>
{section_html}
    <section data-section-id="impression">
      <header>Impression</header>
      <p></p>
    </section>
  </body>
</html>"""


TEMPLATES = [
	{
		"template_code": "CT-CHEST-001",
		"title": "CT Chest — Standard",
		"description": "Standard CT chest protocol covering lungs, mediastinum, and pleura.",
		"specialty": "Radiology",
		"default_modality": "CT",
		"default_body_part": "Chest",
		"default_language": "en",
		"versions": [
			{
				"version_label": "1.0",
				"notes": "Initial release",
				"mrrt_html": _mrrt("CT Chest — Standard", [
					("technique", "Technique", "CT of the chest was performed with and without intravenous contrast."),
					("lungs", "Lungs and Airways", "The lungs are clear. No focal consolidation, pleural effusion, or pneumothorax."),
					("mediastinum", "Mediastinum", "The mediastinum is unremarkable. No lymphadenopathy."),
					("pleura", "Pleura", "No pleural effusion or thickening."),
					("heart", "Heart and Pericardium", "Normal cardiac size. No pericardial effusion."),
					("bones", "Osseous Structures", "No acute osseous abnormality."),
				]),
				"publish": True,
				"modality": "CT",
				"body_part": "Chest",
				"priority": 10,
			},
			{
				"version_label": "2.0",
				"notes": "Added dedicated pulmonary nodule tracking section; supersedes v1.0",
				"replaces_label": "1.0",
				"mrrt_html": _mrrt("CT Chest — Standard v2", [
					("technique", "Technique", "CT of the chest was performed with intravenous contrast per lung mass protocol."),
					("lungs", "Lungs and Airways", "The lungs are clear. No focal consolidation, pleural effusion, or pneumothorax."),
					("nodules", "Pulmonary Nodules", "No pulmonary nodules identified. Fleischner follow-up: N/A."),
					("mediastinum", "Mediastinum", "The mediastinum is unremarkable. No pathologic lymphadenopathy."),
					("pleura", "Pleura", "No pleural effusion or thickening."),
					("heart", "Heart and Pericardium", "Normal cardiac size. No pericardial effusion."),
					("bones", "Osseous Structures", "No acute osseous abnormality."),
				]),
				"publish": True,
				"modality": "CT",
				"body_part": "Chest",
				"priority": 10,
			},
		],
	},
	{
		"template_code": "MRI-BRAIN-001",
		"title": "MRI Brain — Routine",
		"description": "Routine brain MRI without contrast for headache, seizure, or screening.",
		"specialty": "Radiology",
		"default_modality": "MRI",
		"default_body_part": "Brain",
		"default_language": "en",
		"versions": [
			{
				"version_label": "1.0",
				"notes": "Initial release",
				"mrrt_html": _mrrt("MRI Brain — Routine", [
					("technique", "Technique", "MRI of the brain was performed without contrast using standard sequences (T1, T2, FLAIR, DWI, GRE)."),
					("parenchyma", "Brain Parenchyma", "Normal signal intensity throughout cortical and subcortical white matter. No diffusion restriction."),
					("ventricles", "Ventricles and CSF Spaces", "Normal ventricular size and configuration. No midline shift or mass effect."),
					("posterior-fossa", "Posterior Fossa", "Cerebellum and brainstem are unremarkable."),
					("vascular", "Vascular Structures", "Major intracranial flow voids are preserved."),
					("calvarium", "Calvarium and Scalp", "No calvarial abnormality."),
				]),
				"publish": True,
				"modality": "MRI",
				"body_part": "Brain",
				"priority": 10,
			},
		],
	},
	{
		"template_code": "XR-CHEST-001",
		"title": "X-Ray Chest — PA and Lateral",
		"description": "Standard two-view chest radiograph for screening and follow-up.",
		"specialty": "Radiology",
		"default_modality": "CR",
		"default_body_part": "Chest",
		"default_language": "en",
		"versions": [
			{
				"version_label": "1.0",
				"notes": "Initial release",
				"mrrt_html": _mrrt("X-Ray Chest — PA and Lateral", [
					("technique", "Technique", "PA and lateral chest radiographs were obtained."),
					("lungs", "Lungs", "The lungs are clear bilaterally. No focal opacity, consolidation, or effusion."),
					("cardiac", "Cardiac Silhouette", "Normal cardiac size and contour."),
					("mediastinum", "Mediastinum", "Mediastinal contour is normal. No widening."),
					("pleura", "Pleural Spaces", "No pleural effusion or pneumothorax."),
					("osseous", "Osseous and Soft Tissues", "Visualised osseous structures are intact."),
				]),
				"publish": True,
				"modality": "CR",
				"body_part": "Chest",
				"priority": 20,
			},
		],
	},
	{
		"template_code": "CT-ABD-001",
		"title": "CT Abdomen and Pelvis — With Contrast",
		"description": "Contrast-enhanced CT of the abdomen and pelvis for oncology and acute abdomen.",
		"specialty": "Radiology",
		"default_modality": "CT",
		"default_body_part": "Abdomen",
		"default_language": "en",
		"versions": [
			{
				"version_label": "1.0",
				"notes": "Initial release",
				"mrrt_html": _mrrt("CT Abdomen and Pelvis — With Contrast", [
					("technique", "Technique", "CT of the abdomen and pelvis was performed with intravenous and oral contrast."),
					("liver", "Liver", "The liver is normal in size and attenuation. No focal lesion."),
					("biliary", "Biliary System", "The gallbladder and bile ducts are unremarkable."),
					("pancreas", "Pancreas", "The pancreas is unremarkable with normal parenchymal attenuation."),
					("spleen", "Spleen", "Normal size and attenuation."),
					("kidneys", "Kidneys and Ureters", "The kidneys are normal in size and enhancement. No hydronephrosis."),
					("bowel", "Bowel", "No bowel wall thickening or obstruction. Normal appendix."),
					("pelvis", "Pelvis", "Pelvic organs are unremarkable."),
					("vasculature", "Vasculature", "The aorta and major abdominal vessels are unremarkable."),
					("lymph-nodes", "Lymph Nodes", "No pathologic lymphadenopathy."),
					("osseous", "Osseous Structures", "No acute osseous abnormality."),
				]),
				"publish": True,
				"modality": "CT",
				"body_part": "Abdomen",
				"priority": 10,
			},
		],
	},
	{
		"template_code": "MRI-KNEE-001",
		"title": "MRI Knee — Routine",
		"description": "Routine MRI of the knee for internal derangement evaluation.",
		"specialty": "Radiology",
		"default_modality": "MRI",
		"default_body_part": "Knee",
		"default_language": "en",
		"versions": [
			{
				"version_label": "1.0",
				"notes": "Draft — pending approval",
				"mrrt_html": _mrrt("MRI Knee — Routine", [
					("technique", "Technique", "MRI of the knee was performed without contrast."),
					("acl", "Anterior Cruciate Ligament", "The ACL is intact with normal signal and course."),
					("pcl", "Posterior Cruciate Ligament", "The PCL is intact."),
					("medial-meniscus", "Medial Meniscus", "No tear or degeneration of the medial meniscus."),
					("lateral-meniscus", "Lateral Meniscus", "No tear or degeneration of the lateral meniscus."),
					("cartilage", "Articular Cartilage", "Articular cartilage is preserved throughout."),
					("soft-tissue", "Soft Tissues", "No soft tissue mass or significant joint effusion."),
				]),
				"publish": False,
			},
		],
	},
]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load(dry_run: bool = False):
	"""Create demo Report Templates, versions, and assignments."""
	frappe.set_user("Administrator")

	summary = {"templates": 0, "versions": 0, "assignments": 0, "skipped": 0}

	for tpl in TEMPLATES:
		code = tpl["template_code"]

		# --- Template ---
		if frappe.db.exists("Radiology Report Template", code):
			print(f"  SKIP template {code} (already exists)")
			summary["skipped"] += 1
			existing_versions = {
				v.version_label: v.name
				for v in frappe.get_all(
					"Radiology Report Template Version",
					filters={"report_template": code},
					fields=["name", "version_label"],
				)
			}
		else:
			if not dry_run:
				doc = frappe.new_doc("Radiology Report Template")
				doc.template_code = code
				doc.title = tpl["title"]
				doc.description = tpl.get("description", "")
				doc.specialty = tpl.get("specialty", "Radiology")
				doc.default_modality = tpl.get("default_modality", "")
				doc.default_body_part = tpl.get("default_body_part", "")
				doc.default_language = tpl.get("default_language", "en")
				doc.status = "Active"
				doc.insert(ignore_permissions=True)
				print(f"  CREATE template {code}: {tpl['title']}")
				summary["templates"] += 1
			else:
				print(f"  [DRY RUN] Would create template {code}: {tpl['title']}")
			existing_versions = {}

		# --- Versions ---
		versions_by_label = dict(existing_versions)

		for ver in tpl.get("versions", []):
			label = ver["version_label"]

			if label in versions_by_label:
				print(f"    SKIP version {code} v{label} (already exists)")
				summary["skipped"] += 1
				continue

			if dry_run:
				print(f"    [DRY RUN] Would create version {code} v{label}")
				continue

			# Determine replaces_version name from label
			replaces_label = ver.get("replaces_label", "")
			replaces_name = versions_by_label.get(replaces_label, "")

			# Create draft version
			v_doc = frappe.new_doc("Radiology Report Template Version")
			v_doc.report_template = code
			v_doc.version_label = label
			v_doc.mrrt_title = tpl["title"]
			v_doc.mrrt_html = ver["mrrt_html"]
			v_doc.language = tpl.get("default_language", "en")
			v_doc.replaces_version = replaces_name
			v_doc.lifecycle_status = "Draft"
			v_doc.validation_status = "Not Run"
			v_doc.insert(ignore_permissions=True)
			v_doc.append_governance_event("Created", "", "Draft", ver.get("notes", "Demo data"))
			v_doc.save(ignore_permissions=True)

			versions_by_label[label] = v_doc.name
			summary["versions"] += 1
			print(f"    CREATE version {code} v{label} → {v_doc.name}")

			if not ver.get("publish", False):
				print(f"    SKIP lifecycle for {v_doc.name} (left as Draft)")
				continue

			# Validate using the source HTML directly (avoids stale reload)
			from healthcare.radiology_reporting.api.report_template_manager import (
				_run_mrrt_validation,
			)
			mrrt_html_src = ver["mrrt_html"]
			findings = _run_mrrt_validation(mrrt_html_src)
			v_doc.reload()
			v_doc.validation_findings = []
			for f in findings:
				v_doc.append("validation_findings", f)
			has_blocking = any(f["blocking"] for f in findings)
			has_errors = any(f["severity"] == "Error" for f in findings)
			has_warnings = any(f["severity"] == "Warning" for f in findings)
			if has_blocking or has_errors:
				v_doc.validation_status = "Failed"
			elif has_warnings:
				v_doc.validation_status = "Warnings"
			else:
				v_doc.validation_status = "Passed"
			error_count = sum(1 for f in findings if f["severity"] == "Error")
			warning_count = sum(1 for f in findings if f["severity"] == "Warning")
			v_doc.validation_summary = f"{error_count} error(s), {warning_count} warning(s)"
			# Save validation result before lifecycle transitions so the gate check sees it
			v_doc.save(ignore_permissions=True)
			frappe.db.commit()
			print(f"    VALIDATE {v_doc.name}: {v_doc.validation_status}")

			# Submit for review → Approve → Publish
			from healthcare.radiology_reporting.api.report_template_manager import _transition_version
			_transition_version(v_doc.name, "Review Ready", "Demo: submitted for review")
			_transition_version(v_doc.name, "Approved", "Demo: approved")
			_transition_version(v_doc.name, "Published", "Demo: published")

			# Supersede the version being replaced
			if replaces_name:
				_transition_version(replaces_name, "Superseded", f"Superseded by {v_doc.name}")
				# Update replacement pointer on old version
				old_doc = frappe.get_doc("Radiology Report Template Version", replaces_name)
				old_doc.replacement_version = v_doc.name
				old_doc.save(ignore_permissions=True)
				print(f"    SUPERSEDE {replaces_name} → replaced by {v_doc.name}")

			# Update current_published_version on template
			t_doc = frappe.get_doc("Radiology Report Template", code)
			t_doc.current_published_version = v_doc.name
			t_doc.save(ignore_permissions=True)

			print(f"    PUBLISH {v_doc.name} ✓")

			# --- Assignment ---
			if ver.get("modality") or ver.get("body_part"):
				a_filters = {
					"report_template": code,
					"template_version": v_doc.name,
					"modality": ver.get("modality", ""),
					"body_part": ver.get("body_part", ""),
				}
				if not frappe.db.exists("Radiology Report Template Assignment", a_filters):
					a_doc = frappe.new_doc("Radiology Report Template Assignment")
					a_doc.report_template = code
					a_doc.template_version = v_doc.name
					a_doc.modality = ver.get("modality", "")
					a_doc.body_part = ver.get("body_part", "")
					a_doc.priority = ver.get("priority", 10)
					a_doc.active = 1
					a_doc.insert(ignore_permissions=True)
					summary["assignments"] += 1
					print(f"    CREATE assignment {code} [{ver.get('modality', '*')}/{ver.get('body_part', '*')}]")
				else:
					print(f"    SKIP assignment {code} (already exists)")
					summary["skipped"] += 1

	frappe.db.commit()

	print("\n--- Demo Data Summary ---")
	print(f"  Templates created : {summary['templates']}")
	print(f"  Versions created  : {summary['versions']}")
	print(f"  Assignments created: {summary['assignments']}")
	print(f"  Skipped (existing): {summary['skipped']}")
	print("Done.")
	return summary


# ---------------------------------------------------------------------------
# Demo patients
# ---------------------------------------------------------------------------

_DEMO_PATIENTS = [
	{"name": "John Smith",      "first_name": "John",     "last_name": "Smith",    "sex": "Male",   "dob": "1965-03-14"},
	{"name": "Mary Johnson",    "first_name": "Mary",     "last_name": "Johnson",  "sex": "Female", "dob": "1972-07-22"},
	{"name": "Michael Jones",   "first_name": "Michael",  "last_name": "Jones",    "sex": "Male",   "dob": "1958-11-05"},
	{"name": "William Miller",  "first_name": "William",  "last_name": "Miller",   "sex": "Male",   "dob": "1980-01-30"},
	{"name": "Margaret Wilson", "first_name": "Margaret", "last_name": "Wilson",   "sex": "Female", "dob": "1949-09-18"},
	{"name": "Susan Martinez",  "first_name": "Susan",    "last_name": "Martinez", "sex": "Female", "dob": "1988-04-07"},
]


def create_demo_patients():
	"""Create demo Patient records whose names match the patient links in the seeded Radiology Reports.

	Patients are inserted with an explicit ``name`` matching the free-text patient
	value already stored in those reports, so no report updates are required.
	"""
	frappe.set_user("Administrator")

	# Ensure Gender master records exist
	for gender in ("Male", "Female"):
		if not frappe.db.exists("Gender", gender):
			frappe.get_doc({"doctype": "Gender", "gender": gender}).insert(ignore_permissions=True)

	created = 0
	skipped = 0
	for p in _DEMO_PATIENTS:
		if frappe.db.exists("Patient", p["name"]):
			print(f"  SKIP  Patient '{p['name']}' (already exists)")
			skipped += 1
			continue

		doc = frappe.new_doc("Patient")
		doc.name = p["name"]          # lock the name so link fields resolve
		doc.first_name = p["first_name"]
		doc.last_name = p["last_name"]
		doc.patient_name = p["name"]
		doc.sex = p["sex"]
		doc.dob = p["dob"]
		doc.status = "Active"
		doc.flags.name_set = True      # prevent autoname from overriding
		doc.insert(ignore_permissions=True)
		created += 1
		print(f"  CREATE Patient '{p['name']}'")

	frappe.db.commit()
	print(f"\nDone — {created} created, {skipped} skipped.")


def create_demo_worklist_items():
	"""Create demo Reporting Worklist Items for testing the template selection dialog (T011).

	Creates one CT/Chest item in 'In Progress' status (matches the published CT Chest
	demo template) and one Nuclear Medicine item without a body part (no matching
	template — tests the blank-report fallback path).

	Ensures required Body Part records exist before inserting worklist items.

	Run via:
	  bench --site development.localhost execute \\
	    healthcare.radiology_reporting.demo_data.create_demo_worklist_items
	"""
	from frappe.utils import now_datetime

	# Ensure Body Part records exist for the body parts we reference
	for bp_name in ("Chest", "Brain", "Abdomen"):
		if not frappe.db.exists("Body Part", bp_name):
			frappe.get_doc({"doctype": "Body Part", "body_part": bp_name}).insert(ignore_permissions=True)
			print(f"  CREATE Body Part '{bp_name}'")

	items = [
		{
			"title": "Demo CT Chest — template-guided",
			"patient": "John Smith",
			"modality": "CT",
			"body_part": "Chest",
			"status": "In Progress",
			"priority": "Routine",
		},
		{
			"title": "Demo NM — blank fallback (no body part)",
			"patient": "Mary Johnson",
			"modality": "Nuclear Medicine",
			"body_part": "",
			"status": "In Progress",
			"priority": "Routine",
		},
	]

	created = skipped = 0
	for item in items:
		# Skip if an identical in-progress item already exists for this patient+modality
		if frappe.db.exists(
			"Reporting Worklist Item",
			{"patient": item["patient"], "modality": item["modality"], "status": ["in", ["Pending", "In Progress"]]},
		):
			print(f"  SKIP  '{item['title']}' (already exists)")
			skipped += 1
			continue

		doc = frappe.new_doc("Reporting Worklist Item")
		doc.patient = item["patient"]
		doc.modality = item["modality"]
		doc.body_part = item.get("body_part", "") or None
		doc.status = "In Progress"
		doc.priority = item.get("priority", "Routine")
		doc.queued_at = now_datetime()
		doc.started_at = now_datetime()
		doc.insert(ignore_permissions=True)
		created += 1
		print(f"  CREATE '{item['title']}' → {doc.name}")

	frappe.db.commit()
	print(f"\nDone — {created} created, {skipped} skipped.")


if __name__ == "__main__":
	load()
