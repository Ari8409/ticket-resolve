---
sop_id: SOP-RAN-010
fault_category: resource_activation_timeout
alarm_name: "Resource Activation Timeout"
managed_object: NRSectorCarrier
additional_text: "Unable to allocate radio resources"
alarm_severity: primary
on_site_required: false
estimated_resolution_time: "15–30 minutes"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Resource Activation Timeout alarm verified active
  - Additional Text confirms "Unable to allocate radio resources"
  - No higher-severity correlated alarms pending resolution
  - NMS access confirmed; SectorEquipmentFunction MO identified for the affected carrier
---

# Resource Activation Timeout — Unable to Allocate Radio Resources (Cell MOs / NRSectorCarrier / Trx)

## Overview

The `Resource Activation Timeout` alarm with additional text
"Unable to allocate radio resources" is raised when no radio resources can
be allocated to the `SectorEquipmentFunction` MO referenced by the
affected cell or carrier MO.

Common co-occurring alarms that indicate the root cause:
- SFP Not Present
- Link Failure
- No Connection

Managed Object: `EUtranCellFDD`, `EUtranCellTDD`, `NbIotCell`, `NRSectorCarrier`, `Trx`, `ExtTrx`
Alarm type: Primary

## Preconditions

- Resource Activation Timeout alarm verified active
- Additional Text confirms "Unable to allocate radio resources"
- No higher-severity correlated alarms pending resolution
- NMS access confirmed; SectorEquipmentFunction MO identified for the affected carrier

## Resolution Steps

1. Check for correlated alarms and resolve alarms with higher severity first; for detailed instructions on identifying correlated alarms and determining their resolution order, see Check for Correlated Alarms in the NMS Fault Management guide.
2. Check if any of the following alarms are raised on the node: SFP Not Present, Link Failure, No Connection; if any are raised, proceed to step 3; if none are raised, proceed to step 5.
3. Check if the MO on which the alarm is raised is relevant to the `SectorEquipmentFunction` MO that is referenced by the MO on which the Resource Activation Timeout alarm is raised; if the specific MO is relevant to SectorEquipmentFunction, proceed to step 4; if the MO is not relevant, proceed to step 5.
4. Follow the remedy actions of the raised SFP / Link Failure / No Connection alarm according to its corresponding alarm OPI.
5. If the alarm remains after addressing correlated alarms, or if no correlated alarms were found: consult the next level of maintenance support.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

15–30 minutes
