---
sop_id: SOP-RF-001
fault_category: signal_loss
estimated_resolution_time: "30–90 minutes"
escalation_path: "L1 NOC → L2 RF Engineer → Vendor TAC (Ericsson SLA-001)"
preconditions:
  - NMS access confirmed and alarm verified active (not cleared)
  - Site access authorisation obtained if physical inspection required
  - Spectrum analyser available for remote diagnostics
---

# Signal Loss — RF Link Degradation SOP

## Overview

Procedure for diagnosing and restoring signal loss on RF links. Covers both remote
remediation and field dispatch decisions for Ericsson MINI-LINK and Nokia Wavence
microwave backhaul equipment.

## Preconditions

- NMS access confirmed and alarm verified active (not cleared)
- Site access authorisation obtained if physical inspection required
- Spectrum analyser available for remote diagnostics

## Resolution Steps

1. Log into NMS and confirm alarm: verify RSSI, RSL, and TSL values are below thresholds; cross-check against baseline recorded at commissioning.
2. Check remote inventory for recent configuration changes in the last 24 hours using the change management portal; roll back any frequency or power changes applied after the last clean measurement.
3. Run an end-to-end path availability test from NMS: if RSL has dropped more than 10 dB from baseline, check for obstructions using the site's LOS survey data.
4. Validate antenna alignment remotely by comparing current azimuth/elevation telemetry against the as-built record; if deviation exceeds 0.5°, schedule field re-alignment.
5. Check Tx power at the far-end node; if Tx is below nominal, attempt a remote power cycle of the ODU via NMS.
6. If RSL remains degraded after power cycle, check for atmospheric ducting or heavy precipitation using weather data for the link path; if weather-induced, log and monitor — no further action until conditions clear.
7. If no weather cause and RSL remains low, dispatch a field engineer with a spectrum analyser to check for interference sources and verify physical antenna condition.
8. After restoration, verify RSL is within ±3 dB of baseline for at least 15 minutes before closing the alarm.

## Escalation Path

L1 NOC → L2 RF Engineer → Vendor TAC (Ericsson SLA-001)

## Estimated Resolution Time

30–90 minutes
