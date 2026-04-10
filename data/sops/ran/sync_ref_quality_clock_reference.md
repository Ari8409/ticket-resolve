---
sop_id: SOP-RAN-001
fault_category: sync_reference_quality
alarm_name: "Sync Reference Quality Level Too Low"
managed_object: RadioEquipmentClockReference
additional_text: "Remedy action independent of additional text"
alarm_severity: primary
on_site_required: false
estimated_resolution_time: "15–30 minutes"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Alarm is verified active and not a transient event
  - No higher-severity correlated alarms pending resolution (resolve those first)
  - NMS access confirmed with read/write privileges on RadioEquipmentClock MOs
---

# Sync Reference Quality Level Too Low — RadioEquipmentClockReference

## Overview

The alarm is raised when the quality level of a synchronisation reference
(`RadioEquipmentClockReference`) is lower than the minimum acceptable quality
level configured on the node (`RadioEquipmentClock.minQualityLevel`).

If no standby synchronisation reference is available, the fault can stop or
disturb network synchronisation for all cells served by this node.

Managed Object: `RadioEquipmentClockReference`
Alarm type: Primary

## Preconditions

- Alarm is verified active and not a transient event
- No higher-severity correlated alarms pending resolution (resolve those first)
- NMS access confirmed with read/write privileges on RadioEquipmentClock MOs

## Resolution Steps

1. Check for correlated alarms and resolve alarms with higher severity first; for detailed instructions on identifying correlated alarms and determining their resolution order, see Check for Correlated Alarms in the NMS Fault Management guide.
2. Verify that attribute `RadioEquipmentClock.minQualityLevel` is set according to the synchronisation plan; if it is not, reconfigure the value according to the plan and wait at least 2 minutes for the alarm to clear.
3. Verify that attribute `RadioEquipmentClockReference.useQLFrom` is set according to the synchronisation plan; if it is not, reconfigure the value and wait at least 2 minutes — if the attribute is set to ADMIN_QL proceed to step 3a, if set to RECEIVED_QL proceed to step 4.
4. [ADMIN_QL path] Verify that attribute `RadioEquipmentClockReference.adminQualityLevel` is set according to the synchronisation plan; reconfigure if needed and wait at least 2 minutes; if the alarm remains, consult the next level of maintenance support and send the present configuration.
5. [RECEIVED_QL path] The fault is in the network synchronisation connection outside the node or in the synchronisation source itself; consult the next level of maintenance support and send the present configuration including values of `RadioEquipmentClock.minQualityLevel`, `RadioEquipmentClockReference.useQLFrom`, `RadioEquipmentClockReference.adminQualityLevel`, and `RadioEquipmentClockReference.receivedQualityLevel`.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

15–30 minutes
