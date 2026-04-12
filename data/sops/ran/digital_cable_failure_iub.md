---
sop_id: SOP-RAN-3G-001
fault_category: hardware_failure
alarm_name: "DigitalCable_CableFailure"
managed_object: UtranCell / IubLink
additional_text: "DigitalCable_CableFailure on Iub interface between RNC and NodeB"
alarm_severity: primary
on_site_required: true
estimated_resolution_time: "1–4 hours"
escalation_path: "L1 NOC → Transmission Team → Field Operations → Vendor"
preconditions:
  - DigitalCable_CableFailure alarm verified active on the affected RNC / UtranCell
  - Affected NodeB site name and location confirmed from node registry
  - Transmission NMS access available to query Iub bearer alarms (SDH/PDH or IP)
  - Field engineer with E1/BERT test equipment and site access credentials on standby
---

# DigitalCable_CableFailure — 3G Iub Physical Cable Failure (RNC / NodeB)

## Overview

The `DigitalCable_CableFailure` alarm is raised on the RNC when the physical
Iub bearer (E1/T1 or STM-1 optical) between the Radio Network Controller and
the NodeB at a remote site is lost or severely degraded. The affected
`UtranCell` goes out of service immediately — all 3G subscribers on that cell
are dropped.

Managed Objects: `UtranCell`, `IubLink`
Alarm type: Primary
Network: 3G WCDMA/UMTS

**This alarm always requires on-site investigation if remote checks confirm
physical cable loss.** Remote-only resolution is only possible if the fault
is caused by a misconfigured patch (rare) and the NodeB O&M interface remains
reachable.

## Preconditions

- DigitalCable_CableFailure alarm verified active on the affected RNC / UtranCell
- Affected NodeB site name and location confirmed from node registry
- Transmission NMS access available to query Iub bearer alarms (SDH/PDH or IP)
- Field engineer with E1/BERT test equipment and site access credentials on standby

## Resolution Steps

1. In OSS-RC / ENM Fault Management, confirm the alarm is ACTIVE on the RNC and note the UtranCell ID and NodeB site codename from the alarm additional text.

2. Scope the fault: navigate to RNC → affected NodeB → check ALL UtranCells on that NodeB. If the entire NodeB is unreachable (all cells in alarm), this is a full Iub or site power failure. If only one UtranCell is affected, suspect a single E1 sub-group or bearer fault.

3. Check the NodeB O&M (Operations & Maintenance) connection status: if O&M is still UP but Iub traffic bearer is DOWN, the fault is on the traffic E1/T1 circuits rather than a total site loss. If O&M is also DOWN, the site has lost all connectivity — suspect power failure, primary fiber cut, or civil damage.

4. Query the transmission NMS for the NodeB site: look for LOS (Loss of Signal), AIS (Alarm Indication Signal), or LOF (Loss of Frame) alarms on the E1/T1 circuits or STM-1 optical ports serving this NodeB. A transmission alarm on the same path confirms the root cause is in the backhaul, not the RAN equipment.

5. Check correlated alarms on RNC17 IubLink MO for the affected NodeB: any `IubLink` alarms (e.g. `IubLink_SetupFailure`, `Iub_Congestion`) confirm the Iub bearer is fully lost rather than intermittently degraded.

6. Determine the root cause branch and take appropriate action:
   - **Civil/third-party cable cut** (transmission LOS + recent roadworks): Notify the fibre provisioning team immediately for emergency splice; dispatch field engineer to the site in parallel to verify.
   - **Single E1 fault / patch panel issue** (O&M UP, one E1 lost): Attempt remote patch rerouting via the DDF management system if available; otherwise dispatch engineer to reseat E1 connector or repatch at the DDF.
   - **NodeB hardware fault** (all bearers lost, O&M down, no transmission alarm): Dispatch field engineer to inspect NodeB chassis — check power, fuses, and Iub interface board.
   - **Post-maintenance misconfiguration** (fault coincides with planned works): Coordinate with the maintenance team to confirm whether a cable was accidentally disconnected during works; request remote rollback if applicable.

7. On-site (field engineer at FERRARI / NodeB site):
   a. Inspect E1/T1 cables at the DDF (Digital Distribution Frame) — check for physical damage, disconnected connectors, or cross-connects.
   b. Run a BERT (Bit Error Rate Test) on the affected E1 pair to confirm continuity and measure BER.
   c. If optical STM-1: inspect the SFP module and fiber connectors — clean with lint-free swab; check bend radius and splice points.
   d. Reseat or replace the faulty cable/connector; re-test all E1 bearers on the Iub.

8. After repair, confirm with the RNC operator that the Iub link recovers and the affected UtranCell returns to `operationalState = ENABLED` in OSS-RC / ENM.

9. In OSS-RC / ENM Fault Management: verify `DigitalCable_CableFailure` alarm clears on the RNC / UtranCell. Check for any secondary alarms (e.g. cell outage performance counters) — these should normalise within 5 minutes of Iub recovery.

10. If the alarm does not clear after cable repair: escalate to the Transmission Team with the BERT test results and a transmission NMS alarm printout; request a full path audit of the E1 bearers from RNC to NodeB.

## Escalation Path

L1 NOC → Transmission Team → Field Operations → Vendor

## Estimated Resolution Time

1–4 hours (remote diagnosis 15 mins; on-site cable repair 1–4 hours depending on severity)
