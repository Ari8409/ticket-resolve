---
sop_id: SOP-RAN-005
fault_category: service_unavailable
alarm_name: "Service Unavailable"
managed_object: NRCellDU
additional_text: "This is a secondary alarm, use alarm correlation information in Additional Information to find primary alarm"
alarm_severity: secondary
on_site_required: false
secondary_alarm_pointer: ""
estimated_resolution_time: "Depends on primary alarm resolution time"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Alarm verified active on NRCellDU or NbIotCell MO
  - Alarm correlation information read from Additional Information field of the alarm
  - The correlated primary alarm has been identified before starting this procedure
---

# Service Unavailable — NRCellDU / NbIotCell

## Overview

The `Service Unavailable` alarm is raised when an NR cell or NB-IoT cell is
disabled because of faults in underlying resources. On `NRCellDU` and
`NbIotCell` MOs, this is **always a secondary alarm** caused by a correlated
primary alarm.

**This alarm MUST NOT be treated as a standalone fault.** The correct procedure
is to identify the correlated primary alarm from the alarm's Additional
Information field and resolve it first.

Managed Object: `NRCellDU`, `NbIotCell`
Alarm type: Secondary (find and resolve primary first)

## Preconditions

- Alarm verified active on NRCellDU or NbIotCell MO
- Alarm correlation information read from Additional Information field of the alarm
- The correlated primary alarm has been identified before starting this procedure

## Resolution Steps

1. Identify the correlated primary alarm as described in Manage Faults; use the alarm's Additional Information field to locate the specific primary alarm and its raising MO.
2. Clear the correlated primary alarm by following the procedure in the corresponding alarm OPI (Operating Procedure Instruction) for that primary alarm.
3. Verify the Service Unavailable alarm has cleared; if the alarm remains after the primary is resolved, consult the next level of maintenance support.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

Depends on primary alarm resolution time
