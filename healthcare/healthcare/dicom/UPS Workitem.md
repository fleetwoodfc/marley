# UPS Workitem vs Procedure Step

In DICOM terminology, these terms are closely related but represent different aspects of radiology workflow management.

## Procedure Step

A **Procedure Step** is a single unit of work in a radiology workflow - one imaging acquisition or processing task. Think of it as "the work to be done."

**Examples:**
- Acquire CT images of the chest
- Process MRI reconstruction
- Generate 3D rendering
- Perform image analysis

## UPS Workitem

A **UPS Workitem** is the **container/envelope** that carries a Procedure Step through the workflow system. It wraps the procedure step with workflow management capabilities:

| Aspect | What it Adds |
|--------|--------------|
| **State Machine** | SCHEDULED → IN PROGRESS → COMPLETED/CANCELED |
| **Ownership** | Who claimed the work (via Transaction UID) |
| **Subscriptions** | Who gets notified of changes |
| **Input/Output** | References to DICOM objects needed/produced |
| **Scheduling** | When the work should happen |

## Analogy: Shipping Package

Think of the relationship like a shipping package:

```
┌─────────────────────────────────────┐
│  UPS WORKITEM (the package)         │
│  ┌─────────────────────────────┐    │
│  │  PROCEDURE STEP (contents)  │    │
│  │  - What to do               │    │
│  │  - On which patient         │    │
│  │  - With what parameters     │    │
│  └─────────────────────────────┘    │
│                                     │
│  + Tracking number (UID)            │
│  + Status (In Transit/Delivered)    │
│  + Who's handling it                │
│  + Delivery notifications           │
└─────────────────────────────────────┘
```

## Code Example

```python
from healthcare.healthcare.dicom.ups_rs import Workitem, ProcedureStepState, DicomCode
from datetime import datetime

# The Workitem is the object you interact with
workitem = Workitem(
    uid="1.2.3.4.5",                           # Workitem tracking
    procedure_step_state=ProcedureStepState.SCHEDULED,  # Workitem state
    procedure_step_label="CT Chest",           # Procedure Step info
    scheduled_workitem_code=DicomCode(         # What procedure
        "CT001", "CT Chest with Contrast", "LOCAL"
    ),
    patient_id="PAT001",                       # Who
    scheduled_start_datetime=datetime.now(),   # When
    input_information=[...],                   # Input DICOM refs
)
```

## Key Differences

| Aspect | Procedure Step | UPS Workitem |
|--------|----------------|--------------|
| **What** | The clinical task | The workflow wrapper |
| **State** | No | Yes (SCHEDULED, IN PROGRESS, etc.) |
| **Ownership** | No | Yes (Transaction UID) |
| **Events** | No | Yes (WebSocket notifications) |
| **API** | N/A | UPS-RS REST/WebSocket |

## State Lifecycle

```
                    ┌──────────────┐
                    │  SCHEDULED   │
                    └──────┬───────┘
                           │
                           │ claim (start_workitem)
                           │ + Transaction UID generated
                           ▼
                    ┌──────────────┐
        ┌──────────▶│ IN PROGRESS  │◀──────────┐
        │           └──────┬───────┘           │
        │                  │                   │
        │    update        │                   │ request_cancellation
        │    progress      │                   │ (by non-owner)
        │                  │                   │
        └──────────────────┤                   │
                           │                   │
              ┌────────────┴────────────┐      │
              │                         │      │
              ▼                         ▼      │
       ┌──────────────┐          ┌──────────────┐
       │  COMPLETED   │          │   CANCELED   │
       └──────────────┘          └──────────────┘
```

## Ownership Model

When a performer claims a workitem (transitions to IN PROGRESS), they receive a **Transaction UID**. This UID is required for:

- Updating the workitem
- Completing the workitem
- Canceling the workitem

This prevents multiple performers from working on the same task simultaneously.

```python
# Claim ownership
transaction_uid = client.start_workitem(uid)

# Must use transaction_uid for subsequent operations
client.update_workitem(uid, updated_workitem, transaction_uid)
client.complete_workitem(uid, transaction_uid)
```

## Why UPS?

The **Unified Procedure Step (UPS)** service was created to provide a **standardized way to manage and track** procedure steps across different DICOM systems. It replaced older, modality-specific worklist services:

| Old Service | Limitation |
|-------------|------------|
| Modality Worklist (MWL) | Query-only, no state management |
| Modality Performed Procedure Step (MPPS) | Modality-initiated, no scheduling |
| General Purpose Worklist (GPWL) | Complex, limited adoption |

UPS combines the best of these into a single, modern service with:
- RESTful API (UPS-RS)
- WebSocket event notifications
- Unified state management
- Cross-modality support

## Related Documents

- [UPS-RS.md](UPS-RS.md) - API documentation and usage examples
- [DICOM PS3.4 Annex CC](https://dicom.nema.org/medical/dicom/current/output/chtml/part04/chapter_CC.html) - UPS Service specification
- [DICOM PS3.18](https://dicom.nema.org/medical/dicom/current/output/chtml/part18/chapter_11.html) - UPS-RS Web Services
