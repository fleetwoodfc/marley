# DICOM UPS-RS Client for Frappe Healthcare

A Python implementation of the DICOM UPS-RS (Unified Procedure Step - RESTful Services) client for integrating radiology worklist management with Frappe Healthcare.

## Overview

UPS-RS is part of the DICOMweb standard (DICOM PS3.18) for managing worklists and procedure steps in radiology workflows. This implementation provides:

- **Workitem Management**: Create, retrieve, update, and search workitems
- **State Transitions**: Start, complete, and cancel procedures
- **Event Subscriptions**: Subscribe to workitem/worklist events via WebSocket
- **Frappe Integration**: Real-time event forwarding to Frappe's Socket.IO

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frappe Healthcare                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │ UpsRSClient │───▶│  UpsWorker   │───▶│ Frappe Realtime   │  │
│  │  (HTTP/WS)  │    │ (Background) │    │   (Socket.IO)     │  │
│  └──────┬──────┘    └──────────────┘    └─────────┬─────────┘  │
│         │                                         │             │
│         ▼                                         ▼             │
│  ┌─────────────┐                         ┌───────────────────┐  │
│  │ DICOM Server│                         │  Browser Client   │  │
│  │ (dcm4chee)  │                         │  (ups_client.js)  │  │
│  └─────────────┘                         └───────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

The UPS-RS client is included in the Healthcare app. Ensure required dependencies are installed:

```bash
pip install requests websockets
```

## Configuration

Add DICOM server settings to Healthcare Settings:

| Field | Description | Example |
|-------|-------------|---------|
| `ups_rs_url` | Base URL of DICOMweb server | `http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs` |
| `dicom_aet` | Application Entity Title | `FRAPPE_AET` |
| `dicom_bearer_token` | OAuth2 token (optional) | `eyJ...` |
| `dicom_verify_ssl` | Verify SSL certificates | `True` |
| `enable_ups_worker` | Auto-start WebSocket worker | `True` |

## Usage

### Python (Backend)

#### Basic Operations

```python
from healthcare.healthcare.dicom import UpsRSClient
from healthcare.healthcare.dicom.ups_rs import Workitem, ProcedureStepState, DicomCode

# Initialize client
client = UpsRSClient(
    base_url="http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs",
    aet="FRAPPE_AET"
)

# Create a workitem
workitem = Workitem(
    procedure_step_label="CT Chest with Contrast",
    patient_id="PAT001",
    patient_name="Doe^John",
    accession_number="ACC123",
    scheduled_workitem_code=DicomCode("CT001", "CT Chest", "LOCAL")
)

uid = client.create_workitem(workitem)
print(f"Created workitem: {uid}")

# Retrieve workitem
workitem = client.retrieve_workitem(uid)
print(f"State: {workitem.procedure_step_state.value}")

# Search workitems
scheduled = client.search_workitems(
    filters={"00741000": "SCHEDULED"},  # ProcedureStepState
    limit=50
)

# Clean up
client.close()
```

#### State Transitions

```python
# Start procedure (SCHEDULED → IN PROGRESS)
transaction_uid = client.start_workitem(uid)

# Update progress during procedure
workitem.custom_attributes["00741002"] = {  # ProcedureStepProgress
    "vr": "DS", 
    "Value": ["50"]
}
client.update_workitem(uid, workitem, transaction_uid)

# Complete procedure (IN PROGRESS → COMPLETED)
client.complete_workitem(uid, transaction_uid)

# Or cancel (IN PROGRESS → CANCELED)
client.cancel_workitem(uid, transaction_uid)
```

#### Request Cancellation (Non-owner)

```python
from healthcare.healthcare.dicom.ups_rs import CancellationRequest

request = CancellationRequest(
    reason="Patient requested rescheduling",
    contact_uri="mailto:radiology@hospital.com",
    contact_display_name="Radiology Department"
)

client.request_cancellation(uid, request)
```

#### Subscriptions

```python
# Subscribe to specific workitem
client.subscribe_workitem(uid, deletion_lock=True)

# Subscribe to all workitems (global)
client.subscribe_worklist()

# Subscribe with filters
client.subscribe_worklist(
    filters={"00741000": "SCHEDULED"},
    deletion_lock=True
)

# Unsubscribe
client.unsubscribe_workitem(uid)
client.unsubscribe_worklist()
```

#### WebSocket Events (Async)

```python
import asyncio

async def handle_event(event_type: str, data: dict):
    print(f"Event: {event_type}")
    print(f"Data: {data}")

async def main():
    client = UpsRSClient(
        base_url="http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs",
        aet="FRAPPE_AET"
    )
    
    # Subscribe to worklist first
    client.subscribe_worklist()
    
    # Listen for events (blocks until closed)
    await client.subscribe_websocket(
        callback=handle_event,
        reconnect=True,
        reconnect_delay=10
    )

asyncio.run(main())
```

### Using Frappe Helpers

```python
from healthcare.healthcare.dicom.ups_rs import (
    get_ups_client,
    create_ups_workitem,
    get_ups_workitem,
    search_ups_workitems,
    change_ups_state
)

# Get client from settings
client = get_ups_client()

# Or use whitelist functions directly
uid = create_ups_workitem(
    procedure_step_label="MRI Brain",
    patient_id="PAT002",
    patient_name="Smith^Jane"
)

# Search
workitems = search_ups_workitems(state="SCHEDULED", limit=100)
```

### JavaScript (Frontend)

```javascript
// Initialize (auto-called on page load)
healthcare.dicom.ups.init();

// Create workitem
healthcare.dicom.ups.createWorkitem({
    procedure_step_label: "CT Chest",
    patient_id: "PAT001",
    patient_name: "Doe^John"
}).then(uid => {
    console.log("Created:", uid);
});

// Get workitem
healthcare.dicom.ups.getWorkitem(uid).then(workitem => {
    console.log("State:", workitem.state);
});

// Search
healthcare.dicom.ups.searchWorkitems({
    state: "SCHEDULED",
    limit: 50
}).then(workitems => {
    console.log("Found:", workitems.length);
});

// State changes
healthcare.dicom.ups.startWorkitem(uid).then(transactionUid => {
    // Later...
    healthcare.dicom.ups.completeWorkitem(uid, transactionUid);
});

// Subscribe to real-time events
const unsubscribe = healthcare.dicom.ups.on("state_change", (data) => {
    console.log("Workitem state changed:", data);
    frappe.show_alert({
        message: `Procedure ${data.workitem_uid} is now ${data.state}`,
        indicator: "blue"
    });
});

// Other event types
healthcare.dicom.ups.on("progress", (data) => { /* ... */ });
healthcare.dicom.ups.on("cancel_request", (data) => { /* ... */ });
healthcare.dicom.ups.on("websocket_connected", (data) => { /* ... */ });

// Unsubscribe when done
unsubscribe();
```

## Background Worker

The UPS Event Worker listens to WebSocket events and:
1. Forwards events to Frappe realtime (browser clients)
2. Updates linked Radiology Procedure status
3. Creates notifications for cancellation requests

### Starting the Worker

```python
# Via bench command
bench execute healthcare.healthcare.dicom.ups_worker.start_worker

# Via API
frappe.call({
    method: "healthcare.healthcare.dicom.ups_worker.enqueue_worker"
});

# Programmatically
from healthcare.healthcare.dicom.ups_worker import enqueue_worker
enqueue_worker()
```

### Scheduler Integration

Add to `hooks.py` for automatic worker management:

```python
scheduler_events = {
    "cron": {
        "0 */1 * * *": [  # Every hour
            "healthcare.healthcare.dicom.ups_worker.check_worker_health"
        ]
    }
}
```

## API Reference

### UpsRSClient

| Method | Description |
|--------|-------------|
| `create_workitem(workitem, uid=None)` | Create new workitem, returns UID |
| `retrieve_workitem(uid)` | Get workitem by UID |
| `update_workitem(uid, workitem, transaction_uid=None)` | Update workitem |
| `search_workitems(filters=None, limit=None, offset=None)` | Search workitems |
| `change_state(uid, state, transaction_uid=None)` | Change workitem state |
| `start_workitem(uid)` | Start workitem (→ IN PROGRESS) |
| `complete_workitem(uid, transaction_uid)` | Complete workitem |
| `cancel_workitem(uid, transaction_uid)` | Cancel workitem |
| `request_cancellation(uid, request=None)` | Request cancellation |
| `subscribe_workitem(uid, deletion_lock=False)` | Subscribe to workitem |
| `subscribe_worklist(filters=None, deletion_lock=False)` | Subscribe to worklist |
| `unsubscribe_workitem(uid)` | Unsubscribe from workitem |
| `unsubscribe_worklist(filtered=False)` | Unsubscribe from worklist |
| `subscribe_websocket(callback, reconnect=True)` | Start WebSocket listener |
| `close_websocket()` | Close WebSocket connection |
| `close()` | Close client and release resources |

### Workitem States

| State | Description |
|-------|-------------|
| `SCHEDULED` | Initial state, workitem is scheduled |
| `IN PROGRESS` | Workitem is being performed |
| `COMPLETED` | Workitem finished successfully |
| `CANCELED` | Workitem was canceled |

### WebSocket Events

| Event | Description |
|-------|-------------|
| `StateReport` | Workitem state changed |
| `ProgressReport` | Workitem progress updated |
| `CancelRequest` | Cancellation requested |
| `Assigned` | Workitem assigned |
| `Delete` | Workitem deleted |

## DICOM Tags

Common tags used in UPS workitems:

| Tag | Name | VR |
|-----|------|-----|
| `00080018` | SOP Instance UID | UI |
| `00741000` | Procedure Step State | CS |
| `00404005` | Scheduled Procedure Step Start DateTime | DT |
| `00741204` | Procedure Step Label | LO |
| `00100020` | Patient ID | LO |
| `00100010` | Patient Name | PN |
| `00080050` | Accession Number | SH |
| `00081195` | Transaction UID | UI |
| `00741002` | Procedure Step Progress | DS |

## Integration with Radiology Procedure

The UPS worker automatically syncs state with Radiology Procedure DocType:

| UPS State | Radiology Procedure Status |
|-----------|---------------------------|
| SCHEDULED | Scheduled |
| IN PROGRESS | In Progress |
| COMPLETED | Completed |
| CANCELED | Cancelled |

Link a Radiology Procedure to UPS by setting `ups_workitem_uid` field.

## Compatible DICOM Servers

Tested with:
- **dcm4chee-arc** 5.x
- **Orthanc** with DICOMweb plugin
- **Google Cloud Healthcare API**

## Error Handling

```python
from healthcare.healthcare.dicom.ups_rs import UpsRSError

try:
    workitem = client.retrieve_workitem("invalid-uid")
except UpsRSError as e:
    print(f"Error {e.status_code}: {e.message}")
```

## Testing

Run unit tests:

```bash
bench --site development.localhost run-tests --app healthcare --module healthcare.healthcare.dicom.test_ups_rs
```

For integration tests with a real DICOM server:

```bash
DICOM_TEST_URL=http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs \
    bench --site development.localhost run-tests --app healthcare --module healthcare.healthcare.dicom.test_ups_rs
```

## References

- [DICOM PS3.18 - Web Services](https://dicom.nema.org/medical/dicom/current/output/chtml/part18/PS3.18.html)
- [dcm4che - Open Source DICOM](https://www.dcm4che.org/)
- [dcm4chee-arc Documentation](https://github.com/dcm4che/dcm4chee-arc-light/wiki)
- [IHE Radiology Technical Framework](https://www.ihe.net/resources/technical_frameworks/#radiology)

## License

GNU GPL v3 - See LICENSE file in the Healthcare app root.
