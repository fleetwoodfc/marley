# Copyright (c) 2026, earthians Health Informatics and contributors
# For license information, please see license.txt
"""
OCL (OpenConceptLab) API client for Marley.

Configuration is driven by environment variables (or frappe.conf):
  OCL_BASE_URL   - Base URL of the OCL API  (default: https://api.openconceptlab.org)
  OCL_TOKEN      - API authentication token  (required for private sources)
  OCL_ORG        - OCL organisation slug     (default: CIEL)
  OCL_SOURCE     - OCL source slug           (default: CIEL)

Usage::

    from healthcare.terminology.ocl_client import OCLClient

    client = OCLClient()
    version = client.get_latest_ciel_version()
    concepts = list(client.stream_concepts(version))
"""

import os
import time

import requests

import frappe
from frappe import _


class OCLClientError(Exception):
	"""Raised when the OCL API returns an unexpected response."""


class OCLClient:
	"""Thin HTTP client for the OpenConceptLab REST API."""

	DEFAULT_BASE_URL = "https://api.openconceptlab.org"
	DEFAULT_ORG = "CIEL"
	DEFAULT_SOURCE = "CIEL"
	PAGE_SIZE = 200
	MAX_RETRIES = 3
	RETRY_BACKOFF = 2  # seconds

	def __init__(self):
		self.base_url = self._cfg("OCL_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")
		self.token = self._cfg("OCL_TOKEN", "")
		self.org = self._cfg("OCL_ORG", self.DEFAULT_ORG)
		self.source = self._cfg("OCL_SOURCE", self.DEFAULT_SOURCE)
		self._session = requests.Session()
		if self.token:
			self._session.headers.update({"Authorization": f"Token {self.token}"})
		self._session.headers.update({"Accept": "application/json"})

	# ------------------------------------------------------------------
	# Public interface
	# ------------------------------------------------------------------

	def get_latest_ciel_version(self) -> str:
		"""Return the tag of the most recently released CIEL version."""
		url = f"{self.base_url}/orgs/{self.org}/sources/{self.source}/versions/"
		params = {"released": "true", "limit": 1, "sortDesc": "created_at"}
		data = self._get(url, params=params)
		versions = data if isinstance(data, list) else data.get("results", [])
		if not versions:
			frappe.throw(_("No released CIEL versions found on OCL."))
		return versions[0].get("version_id") or versions[0].get("id")

	def get_version_metadata(self, version_tag: str) -> dict:
		"""Return metadata for a specific CIEL version."""
		url = f"{self.base_url}/orgs/{self.org}/sources/{self.source}/{version_tag}/"
		return self._get(url)

	def stream_concepts(self, version_tag: str):
		"""
		Yield concept dicts for the given version, page by page.

		Each dict contains at minimum:
		  id, external_id, concept_class, datatype, retired,
		  names (list), mappings (list)
		"""
		url = f"{self.base_url}/orgs/{self.org}/sources/{self.source}/{version_tag}/concepts/"
		params = {"limit": self.PAGE_SIZE, "offset": 0, "verbose": "true"}
		while True:
			data = self._get(url, params=params)
			results = data if isinstance(data, list) else data.get("results", [])
			if not results:
				break
			yield from results
			# Pagination: if we got fewer records than page size, we are done
			if len(results) < self.PAGE_SIZE:
				break
			params["offset"] += self.PAGE_SIZE

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	@staticmethod
	def _cfg(key: str, default: str = "") -> str:
		"""Read a config value from environment → frappe.conf → default."""
		value = os.environ.get(key)
		if value:
			return value
		try:
			return frappe.conf.get(key.lower(), default)
		except Exception:
			return default

	def _get(self, url: str, params: dict | None = None) -> dict | list:
		"""Perform a GET with retry/backoff and return parsed JSON."""
		last_exc = None
		for attempt in range(self.MAX_RETRIES):
			try:
				response = self._session.get(url, params=params, timeout=30)
				response.raise_for_status()
				return response.json()
			except requests.HTTPError as exc:
				last_exc = exc
				if exc.response is not None and exc.response.status_code < 500:
					# Client errors (4xx) are not retriable
					raise OCLClientError(
						_("OCL API error {0}: {1}").format(exc.response.status_code, exc.response.text)
					) from exc
			except requests.RequestException as exc:
				last_exc = exc
			if attempt < self.MAX_RETRIES - 1:
				time.sleep(self.RETRY_BACKOFF * (attempt + 1))
		raise OCLClientError(
			_("OCL API request failed after {0} attempts: {1}").format(self.MAX_RETRIES, last_exc)
		)
