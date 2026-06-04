# Procedure Type vs Procedure Step

## Overview

The Healthcare module uses two related but distinct DocTypes for managing radiology workflows:

| Aspect | Procedure Type | Procedure Step |
|--------|---------------|----------------|
| **Purpose** | Defines a medical imaging procedure (e.g., "CT Chest", "MRI Brain") | Defines a workflow step within a procedure (e.g., "Patient Check-in", "Image Acquisition") |
| **Nature** | Master data for orderable procedures | Catalog of reusable workflow building blocks |
| **Relationship** | Contains many Procedure Steps via child table | Can be assigned to many Procedure Types |
| **Key Fields** | modality, body_part, laterality, protocol_codes | phase, typical_duration, required_role |
| **System Flag** | No | Yes (`is_system`) - prevents deletion of pre-seeded steps |

## Procedure Type

A **Procedure Type** represents an orderable medical imaging examination. It defines:

- **What** imaging study to perform (modality, body part, laterality)
- **How** to code it (protocol codes, DICOM mappings)
- **Workflow** steps required to complete it

### Key Fields

| Field | Description |
|-------|-------------|
| `procedure_type_name` | Display name (e.g., "CT Chest with Contrast") |
| `modality` | Imaging modality (CT, MR, US, XR, etc.) |
| `body_part` | Anatomical region |
| `laterality` | Left, Right, Bilateral, or N/A |
| `workflow_steps` | Child table linking to Procedure Steps |

## Procedure Step

A **Procedure Step** represents a discrete workflow action within a procedure. It defines:

- **What** action to perform (step name, description)
- **When** in the workflow (phase)
- **Who** should perform it (required role)
- **How long** it typically takes

### Key Fields

| Field | Description |
|-------|-------------|
| `step_name` | Unique identifier (e.g., "Image Acquisition") |
| `description` | Detailed description of the step |
| `phase` | Workflow phase: Acquisition, Post Processing, or Reporting |
| `typical_duration` | Expected duration in minutes |
| `required_role` | Frappe Role that should perform this step |
| `is_active` | Whether step is available for assignment |
| `is_system` | System-seeded steps (cannot be deleted) |

### Phases

1. **Acquisition** - Patient-facing steps (check-in, preparation, imaging)
2. **Post Processing** - Technical steps (reconstruction, enhancement, QA)
3. **Reporting** - Clinical interpretation and documentation

## Relationship Diagram

```
Procedure Type (e.g., "CT Chest with Contrast")
  └── workflow_steps (child table: Procedure Type Step)
       ├── [1] Patient Check-in (Acquisition phase)
       ├── [2] Patient Preparation (Acquisition phase)
       ├── [3] Image Acquisition (Acquisition phase)
       ├── [4] Contrast Administration (Acquisition phase)
       ├── [5] Image Reconstruction (Post Processing phase)
       └── [6] Final Interpretation (Reporting phase)
```

## Data Model

```
┌─────────────────────┐       ┌──────────────────────┐       ┌─────────────────┐
│   Procedure Type    │       │  Procedure Type Step │       │  Procedure Step │
├─────────────────────┤       ├──────────────────────┤       ├─────────────────┤
│ name (PK)           │──┐    │ name (PK)            │    ┌──│ name (PK)       │
│ procedure_type_name │  │    │ parent → Proc Type   │────┘  │ step_name       │
│ modality            │  └───>│ parentfield          │       │ description     │
│ body_part           │       │ procedure_step ──────│───────│ phase           │
│ laterality          │       │ sequence             │       │ typical_duration│
│ workflow_steps[]    │       │ phase (fetch_from)   │       │ required_role   │
└─────────────────────┘       └──────────────────────┘       │ is_active       │
                                                             │ is_system       │
                                                             └─────────────────┘
```

## Example Usage

### Creating a Procedure Type with Workflow Steps

```python
import frappe

# Get or create procedure type
proc_type = frappe.get_doc({
    "doctype": "Procedure Type",
    "procedure_type_name": "MRI Lumbar Spine",
    "modality": "MR",
    "body_part": "Spine",
    "workflow_steps": [
        {"procedure_step": "Patient Check-in", "sequence": 1},
        {"procedure_step": "Patient Preparation", "sequence": 2},
        {"procedure_step": "Patient Positioning", "sequence": 3},
        {"procedure_step": "Image Acquisition", "sequence": 4},
        {"procedure_step": "Image Reconstruction", "sequence": 5},
        {"procedure_step": "Quality Review", "sequence": 6},
        {"procedure_step": "Final Interpretation", "sequence": 7}
    ]
})
proc_type.insert()
```

### Querying Workflow Steps for a Procedure

```python
# Get all workflow steps for a procedure type, ordered by sequence
steps = frappe.get_all(
    "Procedure Type Step",
    filters={"parent": "MRI Lumbar Spine"},
    fields=["procedure_step", "sequence", "phase"],
    order_by="sequence"
)
```

## System-Seeded Steps

The following 12 procedure steps are pre-seeded and cannot be deleted:

### Acquisition Phase
- Patient Check-in
- Patient Preparation
- Patient Positioning
- Image Acquisition
- Contrast Administration

### Post Processing Phase
- Image Reconstruction
- Image Enhancement
- 3D Rendering
- Quality Review

### Reporting Phase
- Preliminary Read
- Final Interpretation
- Report Finalization

## Best Practices

1. **Reuse existing steps** - Use system-seeded steps when possible for consistency
2. **Custom steps** - Create custom steps only for organization-specific workflows
3. **Sequence matters** - Order steps logically within each phase
4. **Inactive steps** - Deactivate rather than delete custom steps to preserve history
5. **Role assignment** - Assign appropriate roles to steps for access control
