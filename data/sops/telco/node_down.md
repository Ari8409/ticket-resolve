---
sop_id: SOP-NET-002
fault_category: node_down
estimated_resolution_time: "15–120 minutes"
escalation_path: "L1 NOC → L2 Network Engineer → L3 Core Network Team → Vendor TAC"
preconditions:
  - Out-of-band (OOB) management access available (console server or 4G management SIM)
  - Maintenance window not required for remote recovery attempts
  - Spare hardware available at the site or nearest depot if hardware fault suspected
---

# Node Down — Network Element Unreachable SOP

## Overview

Procedure for recovering a network node (router, switch, or basestation controller)
that has become unreachable via the primary management plane. Covers remote recovery
via OOB management, automated failover verification, and field dispatch criteria.

## Preconditions

- Out-of-band (OOB) management access available (console server or 4G management SIM)
- Maintenance window not required for remote recovery attempts
- Spare hardware available at the site or nearest depot if hardware fault suspected

## Resolution Steps

1. Confirm the node is truly down and not a management plane issue: ping the loopback from a different network segment and check SNMP trap history in the NMS event log.
2. Access the node via OOB management (console server or 4G SIM); if OOB is also unreachable, check site power status via the building management system or contact site security.
3. If console access is available, check system logs for the last boot reason: kernel panic, power failure, watchdog reset, or software crash; record the exact error message.
4. For a software crash or watchdog reset, attempt a controlled reload via the console: `reload` on Cisco IOS / `reboot` on Linux-based NEs; wait up to 10 minutes for boot completion.
5. If the node boots but does not rejoin the network, verify interface states and routing table; re-apply any missing static routes or BGP peer configurations from the last known-good backup.
6. Check for recent software upgrades or config pushes in the change management portal; if a change correlates with the outage time, roll back to the previous image or configuration.
7. If the node does not respond to OOB access and power is confirmed present, check hardware health indicators (fan alarms, temperature, PSU status) via IPMI or equivalent remote management card.
8. If hardware fault indicators are present (CPU/memory error, PSU failure, fan failure), dispatch a field engineer with a spare unit; initiate hardware replacement procedure SOP-HW-007.
9. After recovery, verify all adjacencies (BGP, OSPF, LDP) are re-established and traffic is flowing before closing the ticket; monitor for 30 minutes to confirm stability.

## Escalation Path

L1 NOC → L2 Network Engineer → L3 Core Network Team → Vendor TAC

## Estimated Resolution Time

15–120 minutes
