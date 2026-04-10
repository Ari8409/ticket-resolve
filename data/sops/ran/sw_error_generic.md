---
sop_id: SOP-RAN-006
fault_category: sw_error
alarm_name: "SW Error"
managed_object: ""
additional_text: "Contact next level of support and provide log files required by Data Collection Guideline"
alarm_severity: primary
on_site_required: false
estimated_resolution_time: "30–60 minutes (log collection); resolution time depends on software fix"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - SW Error alarm is verified active (primary alarm)
  - NMS access confirmed with MoShell or equivalent CLI access to the node
  - Affected Managed Object identified from alarm details (AntennaNearUnit, FieldReplaceableUnit, NRSectorCarrier, EUtranCellFDD, EUtranCellTDD, NbIotCell, SectorCarrier, NRCellDU, or Trx)
---

# SW Error — Generic (All Managed Objects)

## Overview

`SW Error` is a primary alarm raised when a software fault is detected on any
of the following Managed Objects:

- `AntennaNearUnit`
- `FieldReplaceableUnit`
- `NRSectorCarrier`
- `EUtranCellFDD`
- `EUtranCellTDD`
- `NbIotCell`
- `SectorCarrier`
- `NRCellDU`
- `Trx`

The remedy for all MOs is identical: collect the SW error alarm log and
escalate to the next level of support with the log files. No on-site
activities are required.

Managed Object: Multiple (see above)
Alarm type: Primary

## Preconditions

- SW Error alarm is verified active (primary alarm)
- NMS access confirmed with MoShell or equivalent CLI access to the node
- Affected Managed Object identified from alarm details

## Resolution Steps

1. Retrieve the `SwErrorAlarmLog` using the `lg7` MoShell command on the affected node; for more information on the SwErrorAlarmLog and the lg7 command, see Manage Software in the NMS administration guide.
2. Contact the next level of support and provide the log files required by the Data Collection Guideline; for more information on required log files and the collection procedure, see Manage Software and the Data Collection Guideline documentation.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

30–60 minutes (log collection); resolution time depends on software fix
