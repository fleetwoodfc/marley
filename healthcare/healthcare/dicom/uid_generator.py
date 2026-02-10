# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
DICOM UID Generation Utilities

Generates compliant DICOM UIDs for:
- Study Instance UID
- SOP Instance UID (for UPS Workitems)
- Transaction UID (for UPS locking)

UIDs follow the format: {org_root}.{timestamp}.{random}
"""

import time
import random
import frappe

# DICOM UID root for this implementation
# In production, organizations should register their own root with IANA
# This is a placeholder root under the "2.25" UUID-derived UID space
DEFAULT_UID_ROOT = "2.25"


def generate_dicom_uid(uid_type: str = "general") -> str:
    """
    Generate a unique DICOM UID.
    
    UIDs are generated using the 2.25 (UUID-derived) root combined with
    a timestamp and random component to ensure uniqueness.
    
    Args:
        uid_type: Type of UID being generated (for logging/debugging)
                  Options: "study", "sop", "transaction", "general"
    
    Returns:
        A valid DICOM UID string (max 64 characters)
    
    Example:
        >>> uid = generate_dicom_uid("study")
        >>> uid
        '2.25.123456789012345678901234567890123456'
    """
    # Get timestamp component (microseconds since epoch)
    timestamp = int(time.time() * 1000000)
    
    # Get random component (ensures uniqueness even with same timestamp)
    random_component = random.randint(100000000000, 999999999999)
    
    # Combine into UID
    uid = f"{DEFAULT_UID_ROOT}.{timestamp}.{random_component}"
    
    # DICOM UIDs must not exceed 64 characters
    if len(uid) > 64:
        uid = uid[:64]
    
    return uid


def generate_study_instance_uid() -> str:
    """
    Generate a unique Study Instance UID.
    
    Used for DICOM Study identification. Each Requested Procedure
    gets a unique Study Instance UID.
    
    Returns:
        A valid DICOM Study Instance UID
    """
    return generate_dicom_uid("study")


def generate_sop_instance_uid() -> str:
    """
    Generate a unique SOP Instance UID.
    
    Used for UPS Workitem identification. Each Scheduled Procedure Step
    gets a unique SOP Instance UID that identifies the workitem.
    
    Returns:
        A valid DICOM SOP Instance UID
    """
    return generate_dicom_uid("sop")


def generate_transaction_uid() -> str:
    """
    Generate a unique Transaction UID.
    
    Used for locking UPS Workitems during IN PROGRESS state.
    The Transaction UID must be provided for state changes from IN PROGRESS.
    
    Returns:
        A valid DICOM Transaction UID
    """
    return generate_dicom_uid("transaction")


def validate_dicom_uid(uid: str) -> bool:
    """
    Validate that a string is a valid DICOM UID.
    
    DICOM UID rules:
    - Max 64 characters
    - Only digits and periods
    - Cannot start or end with period
    - No consecutive periods
    - Each component is a valid number
    
    Args:
        uid: The UID string to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not uid:
        return False
    
    # Max length check
    if len(uid) > 64:
        return False
    
    # Character check
    valid_chars = set("0123456789.")
    if not all(c in valid_chars for c in uid):
        return False
    
    # Cannot start or end with period
    if uid.startswith(".") or uid.endswith("."):
        return False
    
    # No consecutive periods
    if ".." in uid:
        return False
    
    # Each component must be a valid number (no leading zeros except for "0")
    components = uid.split(".")
    for comp in components:
        if not comp:
            return False
        if len(comp) > 1 and comp.startswith("0"):
            return False
    
    return True


@frappe.whitelist()
def get_new_study_uid() -> str:
    """
    Whitelisted method to generate a new Study Instance UID.
    Can be called from frontend JavaScript.
    
    Returns:
        A new Study Instance UID
    """
    return generate_study_instance_uid()


@frappe.whitelist()
def get_new_sop_uid() -> str:
    """
    Whitelisted method to generate a new SOP Instance UID.
    Can be called from frontend JavaScript.
    
    Returns:
        A new SOP Instance UID
    """
    return generate_sop_instance_uid()
