# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from healthcare.healthcare.dicom import generate_study_instance_uid


class RequestedProcedure(Document):
    """
    Requested Procedure DocType (Child Table)
    
    Represents a specific imaging procedure requested as part of an
    Imaging Service Request. Each Requested Procedure gets a unique
    Study Instance UID and can have one or more Scheduled Procedure Steps.
    """
    
    def before_insert(self):
        """Generate Study Instance UID before inserting."""
        if not self.study_instance_uid:
            self.study_instance_uid = generate_study_instance_uid()
    
    def after_insert(self):
        """Actions after the Requested Procedure is inserted."""
        # Study Instance UID should already be set in before_insert
        pass
