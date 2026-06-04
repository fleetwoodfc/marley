# Copyright (c) 2026, Healthcare Dev and contributors
# SPDX-License-Identifier: MIT

import frappe
from frappe.model.document import Document


class UPSDICOMCode(Document):
    """
    A DICOM Coded Entry as specified in IHE RRR-WF §40.4.1.2.

    Stores the three standard codesets used in UPS workitems:
      - Table 40.4.1.2-1  Modality-to-Read (concept RRR004, 99IHE)
      - Table 40.4.1.2-2  Specialty-to-Read (concept RRR005, 99IHE)
      - Table 40.4.1.2-3  Report Requested  (concept RRR000, 99IHE)

    Also stores Workitem codes (e.g. 99IHE:Addendum) and Concept codes
    (e.g. DCM:123014 Target Region, SRT:R-42453 Screening).
    """

    # autoname = "prompt" — name is set explicitly (e.g. "99IHE:ReadCT")
    pass
