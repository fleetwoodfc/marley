"""Check UPS sync status and errors"""
import frappe

def execute():
    settings = frappe.get_single("Healthcare Settings")
    print("UPS Sync Enabled:", settings.enable_ups_sync)
    print("UPS RS URL:", settings.ups_rs_url)
    print()
    
    # Check error log - get full details
    errors = frappe.get_all("Error Log", 
        filters={"error": ["like", "%UPS%"]}, 
        fields=["name", "error", "creation"], 
        order_by="creation desc", 
        limit=1
    )
    
    print("Latest UPS Error:")
    if not errors:
        print("  No UPS errors found")
    else:
        print(errors[0].error)
    
    # Check SPS sync status
    print()
    sps_list = frappe.get_all("Scheduled Procedure Step",
        fields=["name", "ups_state", "ups_sync_status", "ups_sync_error"],
        limit=10
    )
    print("Scheduled Procedure Steps:")
    if not sps_list:
        print("  No SPS records found")
    for sps in sps_list:
        print(f"  {sps.name}: state={sps.ups_state}, sync={sps.ups_sync_status}, error={sps.ups_sync_error or 'None'}")
