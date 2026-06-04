"""Create demo CPT codes for radiology procedures"""
import frappe


def execute():
    """Create CPT Code System and demo radiology CPT codes"""
    # Create CPT Code System
    if not frappe.db.exists("Code System", "CPT"):
        cpt_system = frappe.get_doc({
            "doctype": "Code System",
            "code_system": "CPT",
            "uri": "http://www.ama-assn.org/go/cpt",
            "description": "Current Procedural Terminology - Medical procedure codes maintained by the American Medical Association",
            "is_fhir_defined": 1,
            "experimental": 0
        })
        cpt_system.insert(ignore_permissions=True)
        print(f"Created Code System: {cpt_system.name}")
    else:
        print("Code System CPT already exists")
    
    # Demo radiology CPT codes
    cpt_codes = [
        # X-Ray procedures
        ("71046", "Chest X-Ray, 2 views"),
        ("71047", "Chest X-Ray, 3 views"),
        ("73560", "Knee X-Ray, 1 or 2 views"),
        ("73110", "Wrist X-Ray, complete, minimum 3 views"),
        ("72100", "Spine, lumbosacral, 2 or 3 views"),
        # CT procedures
        ("70450", "CT Head/Brain without contrast"),
        ("70460", "CT Head/Brain with contrast"),
        ("71250", "CT Chest without contrast"),
        ("71260", "CT Chest with contrast"),
        ("74176", "CT Abdomen and Pelvis without contrast"),
        ("74177", "CT Abdomen and Pelvis with contrast"),
        # MRI procedures
        ("70551", "MRI Brain without contrast"),
        ("70553", "MRI Brain without and with contrast"),
        ("74181", "MRI Abdomen without contrast"),
        ("72148", "MRI Lumbar Spine without contrast"),
        # Ultrasound
        ("76700", "Ultrasound, abdominal, complete"),
        ("76856", "Ultrasound, pelvic, complete"),
        # Mammography
        ("77067", "Mammography, screening, bilateral"),
        # Nuclear Medicine
        ("78306", "Bone scan, whole body"),
        ("78815", "PET with CT, skull base to mid-thigh"),
    ]
    
    created = 0
    for code, display in cpt_codes:
        if not frappe.db.exists("Code Value", {"code_value": code, "code_system": "CPT"}):
            doc = frappe.get_doc({
                "doctype": "Code Value",
                "code_system": "CPT",
                "code_value": code,
                "display": display,
                "definition": display
            })
            doc.insert(ignore_permissions=True)
            created += 1
            print(f"  Created: {code} - {display}")
    
    frappe.db.commit()
    print(f"\nCreated {created} CPT codes")
    total = frappe.db.count("Code Value", {"code_system": "CPT"})
    print(f"Total CPT codes in system: {total}")
