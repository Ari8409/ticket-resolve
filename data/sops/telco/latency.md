---
sop_id: SOP-NET-004
fault_category: latency
estimated_resolution_time: "30–120 minutes"
escalation_path: "L1 NOC → L2 Network Engineer → L3 Capacity Planning Team → Vendor TAC"
preconditions:
  - IPFIX/NetFlow or equivalent traffic telemetry is available for the affected segment
  - Baseline latency measurements are recorded in the performance management system
  - Access to QoS policy configurations on all nodes in the affected path
---

# High Latency and Packet Loss — Congestion and Delay SOP

## Overview

Procedure for diagnosing and remediating elevated latency, packet loss, or network
congestion on IP/MPLS backhaul and access segments. Covers queue analysis, traffic
re-engineering, and capacity escalation triggers.

## Preconditions

- IPFIX/NetFlow or equivalent traffic telemetry is available for the affected segment
- Baseline latency measurements are recorded in the performance management system
- Access to QoS policy configurations on all nodes in the affected path

## Resolution Steps

1. Confirm the symptom scope: run an MTR or traceroute from multiple vantage points to identify which hop(s) introduce the latency; check if packet loss is present (>0.1% sustained is significant).
2. Check interface utilisation on all hops in the affected path using SNMP or streaming telemetry: identify any interface at >80% utilisation as a congestion candidate.
3. For congested interfaces, inspect the output queue drops using `show interfaces` or equivalent: if drops are present in the primary class, QoS prioritisation may be misclassified.
4. Review traffic composition using NetFlow/IPFIX data: identify the top 10 flows by byte count; check whether any single source/destination pair is consuming >30% of link capacity.
5. If a single application or customer is causing congestion, apply a temporary rate-limit policy on the offending traffic class; notify the customer's account manager immediately.
6. For chronic congestion (>70% utilisation sustained over 4 hours), initiate a capacity upgrade request via the capacity planning portal; in the interim, consider adding a parallel link or re-routing traffic via an alternate path.
7. If latency is high but interface utilisation is normal, check for buffer bloat: verify DSCP markings are correct and the appropriate DSCP class is mapped to the low-latency queue; re-classify if necessary.
8. For MPLS paths, check LSP TE tunnel utilisation and RSVP bandwidth reservation: if an TE tunnel is over-booked, trigger an online re-optimisation via the PCE or RSVP bandwidth adjustment.
9. After mitigation, monitor latency and packet loss for 30 minutes to confirm sustained improvement before updating the ticket; capture a new NetFlow baseline.

## Escalation Path

L1 NOC → L2 Network Engineer → L3 Capacity Planning Team → Vendor TAC

## Estimated Resolution Time

30–120 minutes
