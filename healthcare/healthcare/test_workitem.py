"""Test create workitem and state change directly"""
import frappe
import requests
import time
from healthcare.healthcare.dicom.ups_sync import _build_workitem, get_ups_client

def execute():
    sps = frappe.get_doc("Scheduled Procedure Step", "SPS-00001")
    
    print(f"SPS: {sps.name}")
    print(f"  UPS State: {sps.ups_state}")
    print(f"  SOP Instance UID: {sps.sop_instance_uid}")
    print(f"  Transaction UID: {sps.transaction_uid}")
    
    headers = {"Content-Type": "application/dicom+json", "Accept": "application/dicom+json"}
    
    # Check if workitem exists
    url = f"http://192.168.1.12:8080/dcm4chee-arc/aets/WORKLIST/rs/workitems/{sps.sop_instance_uid}"
    resp = requests.get(url, headers={"Accept": "application/dicom+json"}, timeout=30)
    print(f"\nChecking workitem: {resp.status_code}")
    
    actual_uid = sps.sop_instance_uid
    
    if resp.status_code == 404:
        print("Workitem not found, creating...")
        workitem = _build_workitem(sps)
        dicom_json = workitem.to_dicom_json()
        
        create_url = f"http://192.168.1.12:8080/dcm4chee-arc/aets/WORKLIST/rs/workitems?{sps.sop_instance_uid}"
        create_resp = requests.post(create_url, json=dicom_json, headers=headers, timeout=30)
        print(f"Create response: {create_resp.status_code}")
        print(f"Location header: {create_resp.headers.get('Location', 'None')}")
        
        if create_resp.status_code != 201:
            print(f"Create failed: {create_resp.text}")
            return
        
        # Extract actual UID from Location header
        location = create_resp.headers.get('Location', '')
        if location:
            actual_uid = location.split('/')[-1]
            print(f"Actual UID from Location: {actual_uid}")
            if actual_uid != sps.sop_instance_uid:
                print("WARNING: UID mismatch!")
        
        print("Workitem created! Waiting 2 seconds...")
        time.sleep(2)
        
        # Verify it exists now
        verify_url = f"http://192.168.1.12:8080/dcm4chee-arc/aets/WORKLIST/rs/workitems/{actual_uid}"
        verify_resp = requests.get(verify_url, headers={"Accept": "application/dicom+json"}, timeout=30)
        print(f"Verify after creation: {verify_resp.status_code}")
        if verify_resp.status_code != 200:
            print("Workitem still not found!")
            return
    else:
        print("Workitem exists, checking state...")
        data = resp.json()
        if isinstance(data, list):
            data = data[0]
        state = data.get("00741000", {}).get("Value", ["UNKNOWN"])[0]
        print(f"  Current state: {state}")
        if state != "SCHEDULED":
            print(f"  Workitem already in state {state}, cannot transition from Frappe.")
            return
    
    # Try state change to IN PROGRESS
    import uuid
    transaction_uid = f"2.25.{uuid.uuid4().int}"[:50]
    
    state_url = f"http://192.168.1.12:8080/dcm4chee-arc/aets/WORKLIST/rs/workitems/{actual_uid}/state/WORKLIST"
    state_data = {
        "00081195": {"vr": "UI", "Value": [transaction_uid]},
        "00741000": {"vr": "CS", "Value": ["IN PROGRESS"]}
    }
    
    print(f"\nChanging state to IN PROGRESS...")
    print(f"  PUT {state_url}")
    state_resp = requests.put(state_url, json=state_data, headers=headers, timeout=30)
    print(f"  Response: {state_resp.status_code}")
    print(f"  Warning: {state_resp.headers.get('Warning', 'None')}")
    if state_resp.status_code >= 400:
        print(f"  Error: {state_resp.text}")
    else:
        print(f"  SUCCESS! Transaction UID: {transaction_uid}")
