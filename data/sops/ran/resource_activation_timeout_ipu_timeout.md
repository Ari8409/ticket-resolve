---
sop_id: SOP-RAN-008
fault_category: resource_activation_timeout
alarm_name: "Resource Activation Timeout"
managed_object: EUtranCellFDD
additional_text: "Internal timeout during Inter Processing Unit Control Interface setup"
alarm_severity: primary
on_site_required: false
estimated_resolution_time: "15–30 minutes"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Resource Activation Timeout alarm verified active
  - Additional Text confirms "Internal timeout during Inter Processing Unit Control Interface setup"
  - No higher-severity correlated alarms pending resolution
  - NMS access confirmed with ability to lock/unlock cell MOs and restart hardware units
---

# Resource Activation Timeout — IPU Control Interface Timeout (EUtranCellFDD / EUtranCellTDD)

## Overview

The `Resource Activation Timeout` alarm with additional text
"Internal timeout during Inter Processing Unit Control Interface setup"
is caused by a missing signal from the requested resource during the
unlock cell process.

This specific variant indicates an internal control plane communication
timeout between processing units during cell activation.

Managed Object: `EUtranCellFDD`, `EUtranCellTDD`
Alarm type: Primary

## Preconditions

- Resource Activation Timeout alarm verified active
- Additional Text confirms "Internal timeout during Inter Processing Unit Control Interface setup"
- No higher-severity correlated alarms pending resolution
- NMS access confirmed with ability to lock/unlock cell MOs and restart hardware units

## Resolution Steps

1. Lock the cell using the EUtranCellFDD or the EUtranCellTDD MO (set administrativeState to LOCKED).
2. Unlock the cell (set administrativeState to UNLOCKED) and wait 2 minutes.
3. If the alarm remains: check that the Baseband unit and the radio unit are both enabled and unlocked; if the Baseband unit is locked, unlock it (see Unlock Board or Manage Hardware Equipment); if the radio unit is locked, unlock it (see Unlock Board or Manage Hardware Equipment).
4. Lock the cell again using EUtranCellFDD or EUtranCellTDD MO.
5. Unlock the cell again and wait 2 minutes.
6. If the alarm remains: restart the node; for more information, see Restart Node or Emergency Recover Node on Site depending on the library in use.
7. If the alarm remains: consult the next level of maintenance support.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

15–30 minutes
