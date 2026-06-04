"""Check SPS details"""
import frappe

def execute():
    sps = frappe.get_doc("Scheduled Procedure Step", "SPS-00001")
    print("SPS Details:")
    print(f"  Name: {sps.name}")
    print(f"  UPS State: {sps.ups_state}")
    print(f"  SOP Instance UID: {sps.sop_instance_uid}")
    print(f"  Transaction UID: {sps.transaction_uid}")
    print(f"  Sync Status: {sps.ups_sync_status}")
    print(f"  Sync Error: {sps.ups_sync_error}")
    
    # Check if workitem exists on dcm4chee
    import requests
    url = f"http://192.168.1.12:8080/dcm4chee-arc/aets/WORKLIST/rs/workitems/{sps.sop_instance_uid}"
    print(f"\nChecking dcm4chee for workitem: {url}")
    try:
        resp = requests.get(url, timeout=5)
        print(f"  Response: {resp.status_code}")
        if resp.status_code == 200:
            print(f"  Workitem exists!")
        elif resp.status_code == 404:
            print(f"  Workitem NOT found - needs to be created first")
    except Exception as e:
        print(f"  Error: {e}")
