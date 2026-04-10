---
sop_id: SOP-HW-007
fault_category: hardware_failure
estimated_resolution_time: "2 hours (remote diagnosis); 8 hours if physical replacement required"
escalation_path: "L1 NOC → L2 Field Operations → Vendor RMA Team → Regional Spares Manager"
preconditions:
  - Spare hardware unit confirmed available at nearest depot or site
  - Field engineer with appropriate tools and access credentials dispatched or on standby
  - Change freeze check completed — no active freeze period for this network segment
---

# Hardware Failure — Physical Component Replacement SOP

## Overview

Procedure for diagnosing and replacing failed physical hardware components including
line cards, power supply units, fans, optical transceivers, and complete chassis.
Covers remote diagnosis, RMA initiation, and field replacement steps.

## Preconditions

- Spare hardware unit confirmed available at nearest depot or site
- Field engineer with appropriate tools and access credentials dispatched or on standby
- Change freeze check completed — no active freeze period for this network segment

## Resolution Steps

1. Identify the failing component from NMS alarms: check hardware inventory alarms for PSU, fan, line card, or transceiver faults and note the exact slot/port identifier.
2. Attempt remote recovery where applicable: for transceiver faults, check DOM (Digital Optical Monitoring) values via CLI and attempt a remote interface shutdown/no-shutdown cycle.
3. For PSU or fan failures, verify redundancy status: if the failed unit is redundant and the standby is active, the node can continue operating — raise an RMA but defer replacement to the next maintenance window.
4. If the failure is on a non-redundant component (single PSU, primary fabric), immediately declare a P1 incident and prepare for emergency replacement.
5. Initiate the vendor RMA process: log into the vendor portal, raise an RMA ticket with the serial number and fault description, and confirm the SLA (standard 4-hour, NBD, or critical 2-hour based on service tier).
6. While awaiting the spare, implement traffic mitigation: re-route affected LSPs or adjust OSPF/BGP costs to steer traffic away from the affected node where possible.
7. On field engineer arrival, follow the vendor's hot-swap procedure for the specific component; do not power down the chassis unless the component is non-hot-swappable.
8. After replacement, verify the component is recognised by the system (check hardware inventory), confirm all alarms clear, and validate traffic is restored across all affected services.
9. Update the asset management system with the new serial number and the returned faulty unit's tracking information.

## Escalation Path

L1 NOC → L2 Field Operations → Vendor RMA Team → Regional Spares Manager

## Estimated Resolution Time

2 hours (remote diagnosis); 8 hours if physical replacement required
