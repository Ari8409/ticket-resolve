---
sop_id: SOP-RAN-009
fault_category: resource_activation_timeout
alarm_name: "Resource Activation Timeout"
managed_object: NRSectorCarrier
additional_text: "Radio unit is unable to provide requested nominal power on TX antennas"
alarm_severity: primary
on_site_required: false
estimated_resolution_time: "15–30 minutes"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Resource Activation Timeout alarm verified active
  - Additional Text confirms "Radio unit is unable to provide requested nominal power on TX antennas"
  - No higher-severity correlated alarms pending resolution
  - NMS access confirmed with ability to lock/unlock cell MOs and restart radio hardware
---

# Resource Activation Timeout — TX Power Shortage (Cell MOs / NRSectorCarrier)

## Overview

The `Resource Activation Timeout` alarm with additional text
"Radio unit is unable to provide requested nominal power on TX antennas"
is caused by a lack of TX power on the radio unit. The radio unit cannot
provide the requested nominal power level needed for cell activation.

Managed Object: `EUtranCellFDD`, `EUtranCellTDD`, `NbIotCell`, `NRSectorCarrier`
Alarm type: Primary

## Preconditions

- Resource Activation Timeout alarm verified active
- Additional Text confirms "Radio unit is unable to provide requested nominal power on TX antennas"
- No higher-severity correlated alarms pending resolution
- NMS access confirmed with ability to lock/unlock cell MOs and restart radio hardware

## Resolution Steps

1. Check for correlated alarms and resolve alarms with higher severity first; for detailed instructions on identifying correlated alarms and determining their resolution order, see Check for Correlated Alarms in the NMS Fault Management guide.
2. Lock the cell (set administrativeState to LOCKED on the cell MO).
3. Unlock the cell (set administrativeState to UNLOCKED) and wait 2 minutes.
4. If the alarm remains: restart the radio unit; for more information, see Manage Hardware Equipment for Baseband Radio Nodes.
5. If the alarm remains: consult the next level of maintenance support.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

15–30 minutes
