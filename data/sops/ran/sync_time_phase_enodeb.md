---
sop_id: SOP-RAN-002
fault_category: sync_time_phase_accuracy
alarm_name: "Sync Time and Phase Accuracy Too Low"
managed_object: ENodeBFunction
additional_text: "Time and phase sync accuracy crossed the threshold for features interworking with NR"
alarm_severity: primary
on_site_required: false
estimated_resolution_time: "20–60 minutes"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Alarm verified active on ENodeBFunction MO
  - No higher-severity correlated alarms pending resolution
  - NMS access confirmed with read/write privileges on RadioEquipmentClock and NodeGroupSyncMember MOs
---

# Sync Time and Phase Accuracy Too Low — ENodeBFunction

## Overview

The `Sync Time and Phase Accuracy Too Low` alarm is raised on `ENodeBFunction`
when synchronisation accuracy is worse than the required level for features
interworking with NR (5G New Radio).

Features that may be degraded when this alarm is active:
- Basic Intelligent Connectivity
- NR Coverage-Triggered NR Session Continuity

This alarm is a primary alarm. Resolution depends on the node's role in its
node group (`RadioEquipmentClock.nodeGroupRole`).

Managed Object: `ENodeBFunction`
Alarm type: Primary

## Preconditions

- Alarm verified active on ENodeBFunction MO
- No higher-severity correlated alarms pending resolution
- NMS access confirmed with read/write privileges on RadioEquipmentClock and NodeGroupSyncMember MOs

## Resolution Steps

1. Check the role of the node in its node group by reading the value of attribute `RadioEquipmentClock.nodeGroupRole`; if the role is "Not Defined" or "Synchronization Receiver" proceed to step 2; if the role is "Not Activated" or "Synchronization Provider" proceed to step 3.
2. [Synchronization Receiver path] Check if any of the following alarms is raised on the `NodeGroupSyncMember` MO and resolve them according to the appropriate alarm Operating Instructions: "Node Group Sync Configuration Fault", "Node Group Sync Loss of All SoCC"; if the alarm remains, proceed to step 3.
3. [Synchronization Provider path] Check if any of the following alarms are raised on `RadioEquipmentClock` or `RadioEquipmentClockReference` MOs and resolve them first: Clock Reference Missing For Long Time, Sync PTP Time Availability Fault, Sync PTP Time PDV Problem, Sync PTP Time Reachability Fault, Sync PTP Time Reliability Fault, Sync Reference Deviation, Sync Reference Quality Level Too Low, TimeSyncIO Reference Failed.
4. Verify that attributes `RadioEquipmentClockReference.administrativeState` and `NodeGroupSyncMember.administrativeState` are set to UNLOCKED on the node that has the Not Activated or Synchronization Provider role; set to UNLOCKED if they are not.
5. Verify that the configuration of synchronisation is correct; for more information, see Manage Network Synchronization in the NMS administration guide.
6. Consult the next level of maintenance support.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

20–60 minutes
