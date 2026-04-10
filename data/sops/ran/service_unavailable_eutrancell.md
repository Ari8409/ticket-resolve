---
sop_id: SOP-RAN-004
fault_category: service_unavailable
alarm_name: "Service Unavailable"
managed_object: EUtranCellFDD
additional_text: "This is a secondary alarm, use alarm correlation information in Additional Information to find primary alarm"
alarm_severity: secondary
on_site_required: false
secondary_alarm_pointer: ""
estimated_resolution_time: "Depends on primary alarm resolution time"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Alarm verified active on EUtranCellFDD or EUtranCellTDD MO
  - Alarm correlation information read from Additional Information field of the alarm
  - The correlated primary alarm has been identified before starting this procedure
---

# Service Unavailable — EUtranCellFDD / EUtranCellTDD

## Overview

The `Service Unavailable` alarm is raised when a cell is disabled because of
faults in underlying resources. On `EUtranCellFDD` and `EUtranCellTDD` MOs,
this is **always a secondary alarm** caused by a correlated primary alarm or
by fallback from time and phase synchronisation.

**This alarm MUST NOT be treated as a standalone fault.** The correct procedure
is to identify the correlated primary alarm from the alarm's Additional
Information field and resolve it first.

A special sub-case exists where no correlated primary alarm is present — this
occurs when fallback from time and phase synchronisation is activated AND a GPS
HW defect happens simultaneously. In this case follow the GPS fallback procedure
(steps 4–7 below).

Managed Object: `EUtranCellFDD`, `EUtranCellTDD`
Alarm type: Secondary (find and resolve primary first)

## Preconditions

- Alarm verified active on EUtranCellFDD or EUtranCellTDD MO
- Alarm correlation information read from Additional Information field of the alarm
- The correlated primary alarm has been identified before starting this procedure

## Resolution Steps

1. Check for any correlated alarms as described in Manage Faults; if a correlated primary alarm is identified, proceed to step 2; if no correlated alarm is present, the cause is GPS/sync fallback — proceed to step 4.
2. Clear the correlated primary alarm by following the procedure in the corresponding alarm OPI (Operating Procedure Instruction).
3. Verify the Service Unavailable alarm has cleared after the primary alarm was resolved; if the alarm remains, consult the next level of maintenance support.
4. [GPS fallback sub-case] Check the configuration to ensure that all attributes and parameters associated with the `TimeAndPhase` MO for activation of fallback from time and phase synchronisation are set correctly; pay close attention to `ENodeBFunction.timePhaseMaxDeviationTdd` and `ENodeBFunction.timePhaseMaxDeviationTdd(1-7)` attributes that define the alarm thresholds.
5. Troubleshoot for a marginally defective Synchronisation Reference input (the GPS system); check for correct installation (line of sight), cabling and configuration (`GpsCompensationDelay` parameter) or replace the GPS Receiver unit.
6. Check if the `ENodeBFunction.timePhaseMaxDeviationTdd` or `ENodeBFunction.timePhaseMaxDeviationTdd(1-7)` attribute is set correctly.
7. Consult the next level of maintenance support.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

Depends on primary alarm resolution time
