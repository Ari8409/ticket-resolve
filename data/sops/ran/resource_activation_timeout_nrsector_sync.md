---
sop_id: SOP-RAN-011
fault_category: resource_activation_timeout
alarm_name: "Resource Activation Timeout"
managed_object: NRSectorCarrier
additional_text: "Timeout while waiting for response from radio that is unable to synchronize"
alarm_severity: primary
on_site_required: false
estimated_resolution_time: "15–45 minutes"
escalation_path: "Consult the next level of maintenance support"
preconditions:
  - Resource Activation Timeout alarm verified active on NRSectorCarrier
  - Additional Text confirms "Timeout while waiting for response from radio that is unable to synchronize"
  - No higher-severity correlated alarms pending resolution
  - NMS access confirmed with ability to lock/unlock NRSectorCarrier and restart radio/baseband
---

# Resource Activation Timeout — Radio Unable to Synchronize (NRSectorCarrier)

## Overview

The `Resource Activation Timeout` alarm is raised on `NRSectorCarrier` when the
requested radio resources are not available within a certain time frame because
the radio cannot synchronize. The `NRSectorCarrier` is disabled as a result.

This variant specifically involves a synchronisation failure on the
`FieldReplaceableUnit` associated with the sector carrier.

Managed Object: `NRSectorCarrier`
Alarm type: Primary

## Preconditions

- Resource Activation Timeout alarm verified active on NRSectorCarrier
- Additional Text confirms "Timeout while waiting for response from radio that is unable to synchronize"
- No higher-severity correlated alarms pending resolution
- NMS access confirmed with ability to lock/unlock NRSectorCarrier and restart radio/baseband

## Resolution Steps

1. Check for correlated alarms and resolve alarms with higher severity first; for detailed instructions on identifying correlated alarms and determining their resolution order, see Check for Correlated Alarms in the NMS Fault Management guide.
2. Identify the presence of the Synchronization Lost alarm on the corresponding FieldReplaceableUnit MO; if the Synchronization Lost alarm is present, clear it according to the procedure in the corresponding alarm OPI.
3. If the Synchronization Lost alarm is not present, or if the alarm remains after clearing it: set the `NRSectorCarrier.administrativeState` attribute to LOCKED.
4. Set the `NRSectorCarrier.administrativeState` attribute to UNLOCKED and wait 2 minutes.
5. If the alarm remains: restart the radio unit; for more information, see Manage Hardware Equipment or Restart Board depending on the library in use.
6. If the alarm remains: restart the Baseband Radio Node; for more information, see Restart Node or Emergency Recover Node on Site depending on the library in use.
7. If the alarm remains: consult the next level of maintenance support.

## Escalation Path

Consult the next level of maintenance support

## Estimated Resolution Time

15–45 minutes
