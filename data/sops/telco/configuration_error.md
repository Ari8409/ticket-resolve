---
sop_id: SOP-CFG-003
fault_category: configuration_error
estimated_resolution_time: "15–60 minutes"
escalation_path: "L1 NOC → L2 Network Engineer → Change Advisory Board (CAB) if rollback affects multiple nodes"
preconditions:
  - Configuration backup from before the suspected change is available and verified
  - Change management ticket number identified for the suspected change
  - Affected services and customers identified from the service inventory
---

# Configuration Error — Misconfiguration Detection and Rollback SOP

## Overview

Procedure for identifying, isolating, and rolling back network configuration errors
that have caused service degradation or outage. Covers change correlation, targeted
rollback, and validation steps for router, switch, and firewall configuration changes.

## Preconditions

- Configuration backup from before the suspected change is available and verified
- Change management ticket number identified for the suspected change
- Affected services and customers identified from the service inventory

## Resolution Steps

1. Correlate the outage start time with recent changes in the change management portal: run a report for all changes applied within 2 hours before the first alarm; identify the most likely candidate change.
2. Pull the configuration diff for the suspected change using the NMS config backup tool: compare the running config with the pre-change backup to identify exactly what was modified.
3. Assess the rollback risk: determine whether the change affects only the local node or propagates to peers (BGP policy changes, OSPF metric adjustments, ACLs); if multi-node impact, notify the CAB before proceeding.
4. For low-risk local rollbacks (interface config, VLAN, QoS policy), apply the rollback immediately via CLI or NMS: paste the pre-change config section and verify with `show` commands.
5. For routing policy rollbacks (BGP route-maps, OSPF redistributions), apply the rollback during a short traffic shift: pre-warm the alternate path, apply the rollback, then restore traffic.
6. For firewall rule rollbacks, follow the security change process: get verbal approval from the security team lead before applying; document the rollback in the change ticket.
7. After rollback, verify all affected services are restored: check service-level alarms, run end-to-end connectivity tests for each affected customer circuit, and confirm no new alarms are generated.
8. If the rollback does not resolve the issue, the root cause may not be the configuration change — escalate to L2 for deeper investigation; do not re-apply the rolled-back change without CAB approval.
9. Document the full incident timeline, root cause, and corrective action in the change ticket and close with a lessons-learned note.

## Escalation Path

L1 NOC → L2 Network Engineer → Change Advisory Board (CAB) if rollback affects multiple nodes

## Estimated Resolution Time

15–60 minutes
