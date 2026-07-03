# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""
CIEL importer service for Marley.

Imports CIEL concepts from the OCL API into local Frappe DocTypes:
  - CIEL Terminology Version  (one row per import run)
  - CIEL Concept              (one row per concept x version)
  - CIEL Concept Name         (child table on CIEL Concept)
  - CIEL Concept Mapping      (child table on CIEL Concept)

The import is idempotent: if a version with status='ready' already
exists, the importer skips it (unless *force* is True).

Usage::

    from healthcare.terminology.importer import CIELImporter

    summary = CIELImporter().import_version("2024-01-01", make_default=True)
    print(summary)
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from healthcare.terminology.ocl_client import OCLClient


class CIELImporter:
	"""Service that downloads CIEL from OCL and stores it in local DocTypes."""

	DEFAULT_CHUNK_SIZE = 500

	def __init__(self, client: OCLClient | None = None):
		self.client = client or OCLClient()

	# ------------------------------------------------------------------
	# Public interface
	# ------------------------------------------------------------------

	def import_version(
		self,
		version_tag: str | None = None,
		make_default: bool = False,
		dry_run: bool = False,
		chunk_size: int = DEFAULT_CHUNK_SIZE,
		force: bool = False,
	) -> dict:
		"""
		Import a specific CIEL version (or the latest one if *version_tag* is
		``None`` or ``"latest"``).

		Returns a summary dict with keys:
		  version_tag, concepts_imported, names_imported, mappings_imported,
		  concepts_retired, import_errors, skipped, dry_run
		"""
		if not version_tag or version_tag.lower() == "latest":
			version_tag = self.client.get_latest_ciel_version()
			frappe.logger().info(f"Resolved latest CIEL version: {version_tag}")

		# Idempotency guard
		existing = frappe.db.get_value(
			"CIEL Terminology Version",
			{"version_tag": version_tag, "status": "ready"},
			"name",
		)
		if existing and not force:
			frappe.logger().info(
				f"CIEL version {version_tag} already imported (skipping). Use force=True to re-import."
			)
			return {
				"version_tag": version_tag,
				"skipped": True,
				"dry_run": dry_run,
			}

		summary = {
			"version_tag": version_tag,
			"concepts_imported": 0,
			"names_imported": 0,
			"mappings_imported": 0,
			"concepts_retired": 0,
			"import_errors": 0,
			"skipped": False,
			"dry_run": dry_run,
		}

		if dry_run:
			frappe.logger().info(f"[DRY RUN] Would import CIEL version {version_tag}.")
			return summary

		# Create / update the version record
		version_doc = self._get_or_create_version_doc(version_tag)

		try:
			self._stream_and_save(version_doc, chunk_size, summary)
			version_doc.reload()
			version_doc.status = "ready"
			version_doc.imported_at = now_datetime()
			version_doc.concepts_imported = summary["concepts_imported"]
			version_doc.names_imported = summary["names_imported"]
			version_doc.mappings_imported = summary["mappings_imported"]
			version_doc.concepts_retired = summary["concepts_retired"]
			version_doc.import_errors = summary["import_errors"]
			version_doc.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			version_doc.reload()
			version_doc.status = "failed"
			version_doc.save(ignore_permissions=True)
			frappe.db.commit()
			raise

		if make_default:
			version_doc.promote_to_default()

		frappe.logger().info(
			f"CIEL import complete: version={version_tag} "
			f"concepts={summary['concepts_imported']} "
			f"names={summary['names_imported']} "
			f"mappings={summary['mappings_imported']} "
			f"retired={summary['concepts_retired']} "
			f"errors={summary['import_errors']}"
		)
		return summary

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	def _get_or_create_version_doc(self, version_tag: str):
		existing_name = frappe.db.get_value("CIEL Terminology Version", {"version_tag": version_tag}, "name")
		if existing_name:
			doc = frappe.get_doc("CIEL Terminology Version", existing_name)
			doc.status = "importing"
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.new_doc("CIEL Terminology Version")
			doc.version_tag = version_tag
			doc.status = "importing"
			doc.ocl_org = self.client.org
			doc.ocl_source = self.client.source
			doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc

	def _stream_and_save(self, version_doc, chunk_size: int, summary: dict):
		"""Stream concepts from OCL and bulk-insert in chunks."""
		chunk: list[dict] = []

		for raw in self.client.stream_concepts(version_doc.version_tag):
			try:
				concept_data = self._parse_concept(raw, version_doc.name)
			except Exception as exc:
				frappe.logger().warning(f"Failed to parse concept {raw.get('id')}: {exc}")
				summary["import_errors"] += 1
				continue

			chunk.append(concept_data)
			if concept_data.get("retired"):
				summary["concepts_retired"] += 1
			summary["names_imported"] += len(concept_data.get("names", []))
			summary["mappings_imported"] += len(concept_data.get("mappings", []))

			if len(chunk) >= chunk_size:
				self._flush_chunk(chunk, summary)
				chunk = []

		if chunk:
			self._flush_chunk(chunk, summary)

	def _flush_chunk(self, chunk: list[dict], summary: dict):
		for concept_data in chunk:
			self._upsert_concept(concept_data)
			summary["concepts_imported"] += 1
		frappe.db.commit()

	@staticmethod
	def _parse_concept(raw: dict, version_name: str) -> dict:
		"""Normalise a raw OCL concept dict into the shape we need."""
		names = []
		for n in raw.get("names", []):
			names.append(
				{
					"name_type": (n.get("name_type") or "NULL").upper(),
					"locale": n.get("locale", "en"),
					"name_text": n.get("name", ""),
					"preferred": 1 if n.get("locale_preferred") else 0,
					"voided": 1 if n.get("voided") else 0,
				}
			)

		mappings = []
		for m in raw.get("mappings", []):
			mappings.append(
				{
					"map_type": m.get("map_type", ""),
					"target_system": m.get("to_source_url", m.get("to_concept_code", "")),
					"target_code": m.get("to_concept_code", ""),
					"target_display": m.get("to_concept_name", ""),
				}
			)

		return {
			"external_id": str(raw.get("id") or raw.get("external_id") or ""),
			"terminology_version": version_name,
			"concept_class": raw.get("concept_class", ""),
			"datatype": raw.get("datatype", ""),
			"retired": 1 if raw.get("retired") else 0,
			"names": names,
			"mappings": mappings,
		}

	@staticmethod
	def _upsert_concept(data: dict):
		"""Insert or update a CIEL Concept and its child rows."""
		existing_name = frappe.db.get_value(
			"CIEL Concept",
			{
				"external_id": data["external_id"],
				"terminology_version": data["terminology_version"],
			},
			"name",
		)
		if existing_name:
			doc = frappe.get_doc("CIEL Concept", existing_name)
			doc.concept_class = data["concept_class"]
			doc.datatype = data["datatype"]
			doc.retired = data["retired"]
			doc.names = []
			doc.mappings = []
		else:
			doc = frappe.new_doc("CIEL Concept")
			doc.external_id = data["external_id"]
			doc.terminology_version = data["terminology_version"]
			doc.concept_class = data["concept_class"]
			doc.datatype = data["datatype"]
			doc.retired = data["retired"]

		for name_row in data["names"]:
			doc.append("names", name_row)
		for mapping_row in data["mappings"]:
			doc.append("mappings", mapping_row)

		doc.save(ignore_permissions=True)
