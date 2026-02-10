# Copyright (c) 2026, healthcare and contributors
# For license information, please see license.txt

"""
Accession Number Generation

Generates unique accession numbers for Imaging Service Requests
using configurable format from Healthcare Settings.
"""

import frappe
from frappe.model.naming import make_autoname


def generate_accession_number() -> str:
    """
    Generate a unique Accession Number for an Imaging Service Request.
    
    Uses the format configured in Healthcare Settings > DICOM > Accession Number Format.
    Falls back to default format if not configured.
    
    Format syntax follows Frappe naming series:
    - .YYYY. = 4-digit year
    - .YY. = 2-digit year
    - .MM. = 2-digit month
    - .DD. = 2-digit day
    - .##### = 5-digit counter (auto-incrementing)
    
    Examples:
        - ACC-.YYYY.-.##### -> ACC-2026-00001
        - IMG-.YY..MM.-.#### -> IMG-2602-0001
    
    Returns:
        A unique accession number string
    """
    # Get format from Healthcare Settings
    accession_format = frappe.db.get_single_value(
        "Healthcare Settings", 
        "accession_number_format"
    )
    
    # Default format if not configured
    if not accession_format:
        accession_format = "ACC-.YYYY.-.#####"
    
    # Generate using Frappe's naming series
    return make_autoname(accession_format, "Imaging Service Request")


def get_accession_number_issuer() -> str:
    """
    Get the Accession Number Issuer from Healthcare Settings.
    
    The issuer identifies the organization that generated the accession number,
    used in DICOM Issuer of Accession Number Sequence.
    
    Returns:
        Issuer string, or empty string if not configured
    """
    issuer = frappe.db.get_single_value(
        "Healthcare Settings",
        "accession_number_issuer"
    )
    return issuer or ""


def validate_accession_number(accession_number: str) -> bool:
    """
    Validate that an accession number is unique.
    
    Args:
        accession_number: The accession number to validate
    
    Returns:
        True if unique (doesn't exist), False if duplicate
    """
    if not accession_number:
        return False
    
    # Check if already exists
    exists = frappe.db.exists(
        "Imaging Service Request",
        {"accession_number": accession_number}
    )
    
    return not exists


def parse_accession_number(accession_number: str) -> dict:
    """
    Parse an accession number to extract components.
    
    Attempts to extract year and sequence number from standard formats.
    
    Args:
        accession_number: The accession number to parse
    
    Returns:
        Dictionary with parsed components:
        - prefix: The prefix portion (e.g., "ACC")
        - year: The year if present
        - sequence: The sequence number if present
        - raw: The original accession number
    
    Example:
        >>> parse_accession_number("ACC-2026-00001")
        {'prefix': 'ACC', 'year': '2026', 'sequence': '00001', 'raw': 'ACC-2026-00001'}
    """
    result = {
        "prefix": None,
        "year": None,
        "sequence": None,
        "raw": accession_number
    }
    
    if not accession_number:
        return result
    
    # Try common format: PREFIX-YYYY-NNNNN
    parts = accession_number.split("-")
    if len(parts) >= 3:
        result["prefix"] = parts[0]
        result["year"] = parts[1]
        result["sequence"] = parts[2]
    elif len(parts) == 2:
        result["prefix"] = parts[0]
        result["sequence"] = parts[1]
    
    return result


@frappe.whitelist()
def get_new_accession_number() -> str:
    """
    Whitelisted method to generate a new Accession Number.
    Can be called from frontend JavaScript.
    
    Returns:
        A new unique Accession Number
    """
    return generate_accession_number()
