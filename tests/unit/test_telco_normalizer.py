"""Unit tests for TelcoNormalizer — field alias mapping and inference."""
import pytest
from datetime import datetime, timezone

from app.ingestion.telco.normalizer import TelcoNormalizer
from app.models.telco_ticket import FaultType, Severity


@pytest.fixture
def norm():
    return TelcoNormalizer()


# ---------------------------------------------------------------------------
# Field alias lookup
# ---------------------------------------------------------------------------

class TestFieldAliasLookup:
    def test_canonical_field_names_pass_through(self, norm):
        t = norm.normalize({
            "fault_type": "signal_loss",
            "affected_node": "BS-MUM-042",
            "severity": "high",
            "description": "RSSI degradation on BS-MUM-042 affecting 3200 subscribers.",
        }, source="api")
        assert t.fault_type == FaultType.SIGNAL_LOSS
        assert t.affected_node == "BS-MUM-042"
        assert t.severity == Severity.HIGH

    def test_jira_style_aliases(self, norm):
        t = norm.normalize({
            "summary": "BGP session flapping on RTR-HYD-01",
            "hostname": "RTR-HYD-01",
            "priority": "critical",
            "details": "BGP peer 203.0.113.1 has been flapping for 15 minutes causing route churn.",
        }, source="api")
        assert t.affected_node == "RTR-HYD-01"
        assert t.severity == Severity.CRITICAL

    def test_nagios_style_aliases(self, norm):
        t = norm.normalize({
            "alarm_type": "node_down",
            "element": "NODE-ATL-01",
            "alarm_level": "high",
            "alarm_text": "PING CRITICAL - Packet loss = 100%. Node NODE-ATL-01 completely unreachable.",
        }, source="api")
        assert t.fault_type == FaultType.NODE_DOWN
        assert t.affected_node == "NODE-ATL-01"

    def test_uppercase_keys_resolved(self, norm):
        t = norm.normalize({
            "FAULT_TYPE": "latency",
            "AFFECTED_NODE": "RTR-LON-03",
            "SEVERITY": "medium",
            "DESCRIPTION": "High RTT detected on core backhaul link RTR-LON-03.",
        }, source="csv")
        assert t.fault_type == FaultType.LATENCY

    def test_sop_id_aliases(self, norm):
        for key in ("sop_id", "runbook_id", "kb_id", "procedure_id"):
            t = norm.normalize({
                "fault_type": "hardware_failure",
                "affected_node": "ENB-01",
                "severity": "high",
                "description": "Hardware failure on RAN equipment ENB-01 at tower site.",
                key: "SOP-HW-021",
            }, source="api")
            assert t.sop_id == "SOP-HW-021", f"Failed for alias: {key}"

    def test_resolution_steps_alias(self, norm):
        t = norm.normalize({
            "fault_type": "configuration_error",
            "affected_node": "RTR-01",
            "severity": "medium",
            "description": "BGP misconfiguration detected on RTR-01 edge router.",
            "remedy": "Roll back config\nVerify BGP\nRe-apply",
        }, source="api")
        assert t.resolution_steps == ["Roll back config", "Verify BGP", "Re-apply"]

    def test_ticket_id_preserved_from_alias(self, norm):
        t = norm.normalize({
            "incident_id": "INC-99001",
            "fault_type": "congestion",
            "affected_node": "AGGR-01",
            "severity": "medium",
            "description": "Aggregation switch AGGR-01 experiencing traffic congestion on uplink port.",
        }, source="api")
        assert t.ticket_id == "INC-99001"


# ---------------------------------------------------------------------------
# Fault type inference from description text
# ---------------------------------------------------------------------------

class TestFaultTypeInference:
    @pytest.mark.parametrize("text,expected", [
        ("RSSI dropped to -112 dBm. Signal loss on sector 3.", FaultType.SIGNAL_LOSS),
        ("Node NODE-ATL-01 is completely unreachable — 100% packet loss.", FaultType.NODE_DOWN),
        ("High latency detected: RTT 450ms on core backhaul link.", FaultType.LATENCY),
        ("18% packet drop rate on OLT PON downstream ports.", FaultType.PACKET_LOSS),
        ("Uplink congestion — bandwidth utilisation at 98% on aggregation switch.", FaultType.CONGESTION),
        ("Power amplifier hardware failure at cell site ENB-214.", FaultType.HARDWARE_FAILURE),
        ("BGP misconfiguration pushed during maintenance window on RTR-01.", FaultType.CONFIGURATION_ERROR),
        ("Routine check — no anomaly detected on the node.", FaultType.UNKNOWN),
    ])
    def test_infers_fault_type(self, norm, text, expected):
        t = norm.normalize({
            "affected_node": "NODE-X",
            "severity": "medium",
            "description": text,
        }, source="api")
        assert t.fault_type == expected, f"Expected {expected} for: {text[:50]}"


# ---------------------------------------------------------------------------
# Severity inference and mapping
# ---------------------------------------------------------------------------

class TestSeverityMapping:
    @pytest.mark.parametrize("raw_sev,expected", [
        ("critical",      Severity.CRITICAL),
        ("CRITICAL",      Severity.CRITICAL),
        ("p0",            Severity.CRITICAL),
        ("sev1",          Severity.CRITICAL),
        ("disaster",      Severity.CRITICAL),
        ("high",          Severity.HIGH),
        ("major",         Severity.HIGH),
        ("p1",            Severity.HIGH),
        ("medium",        Severity.MEDIUM),
        ("warning",       Severity.MEDIUM),
        ("average",       Severity.MEDIUM),
        ("low",           Severity.LOW),
        ("informational", Severity.LOW),
        ("p3",            Severity.LOW),
    ])
    def test_maps_severity_labels(self, norm, raw_sev, expected):
        t = norm.normalize({
            "fault_type": "latency",
            "affected_node": "NODE-X",
            "severity": raw_sev,
            "description": "High RTT detected on core backhaul link — baseline exceeded.",
        }, source="api")
        assert t.severity == expected, f"Failed for severity label: {raw_sev}"

    def test_infers_critical_from_outage_text(self, norm):
        t = norm.normalize({
            "fault_type": "node_down",
            "affected_node": "NODE-X",
            "description": "Full outage detected on core router. 50000 subscribers impacted.",
        }, source="api")
        assert t.severity == Severity.CRITICAL

    def test_defaults_to_medium_when_unknown_label(self, norm):
        t = norm.normalize({
            "fault_type": "latency",
            "affected_node": "NODE-X",
            "severity": "banana",
            "description": "Intermittent latency spikes observed on backhaul link.",
        }, source="api")
        assert t.severity == Severity.MEDIUM


# ---------------------------------------------------------------------------
# Node extraction from description
# ---------------------------------------------------------------------------

class TestNodeExtraction:
    def test_extracts_node_pattern_from_description(self, norm):
        t = norm.normalize({
            "fault_type": "node_down",
            "severity": "critical",
            "description": "Alert: NODE-ATL-01 is not responding to ICMP. Last seen 09:10 UTC.",
        }, source="api")
        assert "NODE-ATL-01" in t.affected_node

    def test_extracts_bs_pattern(self, norm):
        t = norm.normalize({
            "fault_type": "signal_loss",
            "severity": "high",
            "description": "Base station BS-MUM-042 RSSI dropped below -110 dBm threshold.",
        }, source="api")
        assert "BS-MUM-042" in t.affected_node

    def test_falls_back_to_source_label_when_no_pattern(self, norm):
        t = norm.normalize({
            "fault_type": "congestion",
            "severity": "medium",
            "description": "Traffic congestion detected on the aggregation layer.",
        }, source="csv")
        assert t.affected_node == "UNKNOWN-CSV"


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

class TestTimestampParsing:
    def test_iso_utc_z_format(self, norm):
        t = norm.normalize({
            "fault_type": "latency",
            "affected_node": "N1",
            "severity": "low",
            "description": "Minor latency increase on backhaul link N1.",
            "timestamp": "2024-06-01T09:10:00Z",
        }, source="api")
        assert t.timestamp.year == 2024
        assert t.timestamp.month == 6
        assert t.timestamp.day == 1

    def test_epoch_integer_timestamp(self, norm):
        t = norm.normalize({
            "fault_type": "latency",
            "affected_node": "N1",
            "severity": "low",
            "description": "Minor latency increase on backhaul link N1.",
            "timestamp": 1717229400,  # 2024-06-01T09:10:00Z
        }, source="api")
        assert t.timestamp.year == 2024

    def test_missing_timestamp_defaults_to_now(self, norm):
        t = norm.normalize({
            "fault_type": "latency",
            "affected_node": "N1",
            "severity": "low",
            "description": "Minor latency increase on backhaul link N1.",
        }, source="api")
        assert t.timestamp is not None
        assert (datetime.now(tz=timezone.utc) - t.timestamp).total_seconds() < 5
