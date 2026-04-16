"""
Unit tests for CTTS description parser and TelcoTicketCreate auto-parse logic.

Covers real Ericsson/Singtel NOC alarm description formats including:
- Standard CTTS format: {NodeID}*{alarmCategory}/{alarmName}*{severityCode}*
- Legacy 3G spaced alarm categories ("Equipment Alarm" → "equipmentAlarm")
- UNKNOWN/ prefixed alarm names from RAN NMS exports
- Auto back-fill of affected_node from parsed node_id
- TelcoTicketCreate model_validator integration
"""
from __future__ import annotations

import pytest

from app.models.telco_ticket import (
    FaultType,
    Severity,
    TelcoTicketCreate,
    _parse_ctts_description,
)


# ---------------------------------------------------------------------------
# _parse_ctts_description — raw parser
# ---------------------------------------------------------------------------

class TestCTTSDescriptionParser:
    """Unit tests for the _parse_ctts_description helper."""

    def test_standard_4g_heartbeat_failure(self):
        desc = (
            "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*"
            "Heartbeat Failure\n\nHeartbeat Failure Unknown"
        )
        result = _parse_ctts_description(desc)
        assert result["node_id"] == "LTE_ENB_780321"
        assert result["alarm_category"] == "communicationsAlarm"
        assert result["alarm_name"] == "Heartbeat Failure"
        assert result["alarm_severity_code"] == "1"

    def test_standard_5g_gnb_sync_alarm(self):
        desc = (
            "5G_GNB_1039321*communicationsAlarm/SyncRefQuality*2*"
            "Sync Reference Quality Degraded"
        )
        result = _parse_ctts_description(desc)
        assert result["node_id"] == "5G_GNB_1039321"
        assert result["alarm_category"] == "communicationsAlarm"
        assert result["alarm_name"] == "SyncRefQuality"
        assert result["alarm_severity_code"] == "2"

    def test_3g_nodeb_equipment_alarm_legacy_spaced_category(self):
        """Legacy 3G CTTS exports use spaced category names."""
        desc = (
            "Rnc15_2650*Equipment Alarm/HW Fault*1*"
            "Hardware fault detected on NodeB"
        )
        result = _parse_ctts_description(desc)
        assert result["node_id"] == "Rnc15_2650"
        assert result["alarm_category"] == "equipmentAlarm"   # normalised
        assert result["alarm_name"] == "HW Fault"

    def test_communications_alarm_spaced_legacy(self):
        desc = (
            "Rnc07_1100*Communications Alarm/Link Failure*2*Link down"
        )
        result = _parse_ctts_description(desc)
        assert result["alarm_category"] == "communicationsAlarm"

    def test_processing_error_alarm_spaced_legacy(self):
        desc = (
            "LTE_ENB_780001*Processing Error Alarm/SW Error*2*SW fault"
        )
        result = _parse_ctts_description(desc)
        assert result["alarm_category"] == "processingErrorAlarm"

    def test_unknown_prefix_stripped_from_alarm_name(self):
        """Ericsson NMS sometimes prefixes alarm names with 'UNKNOWN/'."""
        desc = (
            "Rnc07_2345*equipmentAlarm/UNKNOWN/DigitalCable_CableFailure*1*"
            "Digital cable fault"
        )
        result = _parse_ctts_description(desc)
        assert result["alarm_name"] == "DigitalCable_CableFailure"
        assert "UNKNOWN" not in result["alarm_name"]

    def test_allcaps_mo_prefix_stripped(self):
        """MO-type prefixes like 'RADIO/' should be stripped."""
        desc = (
            "LTE_ENB_781000*equipmentAlarm/RADIO/AntennaSupervisor*2*"
            "Antenna fault"
        )
        result = _parse_ctts_description(desc)
        assert result["alarm_name"] == "AntennaSupervisor"

    def test_4g_ess_hw_fault(self):
        desc = (
            "LTE_ESS_735557*equipmentAlarm/HW Fault*1*HW Fault\n\nHardware failure"
        )
        result = _parse_ctts_description(desc)
        assert result["node_id"] == "LTE_ESS_735557"
        assert result["alarm_category"] == "equipmentAlarm"
        assert result["alarm_severity_code"] == "1"

    def test_non_ctts_format_returns_empty_dict(self):
        result = _parse_ctts_description("Generic free-text fault description.")
        assert result == {}

    def test_empty_string_returns_empty_dict(self):
        result = _parse_ctts_description("")
        assert result == {}

    def test_partial_format_no_severity_code_returns_empty(self):
        """If severity code segment is absent, regex should not match."""
        result = _parse_ctts_description(
            "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure"
        )
        assert result == {}

    @pytest.mark.parametrize("severity_code,expected", [
        ("1", "1"),
        ("2", "2"),
        ("3", "3"),
    ])
    def test_alarm_severity_code_values(self, severity_code, expected):
        desc = (
            f"LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*{severity_code}*text"
        )
        result = _parse_ctts_description(desc)
        assert result["alarm_severity_code"] == expected

    def test_whitespace_trimmed_from_node_id(self):
        desc = "  LTE_ENB_780321  *communicationsAlarm/Heartbeat Failure*1*text"
        result = _parse_ctts_description(desc)
        assert result["node_id"] == "LTE_ENB_780321"

    def test_quality_of_service_alarm_normalised(self):
        desc = "5G_GNB_1039321*Quality of Service Alarm/Congestion*2*Congestion alarm"
        result = _parse_ctts_description(desc)
        assert result["alarm_category"] == "qualityOfServiceAlarm"

    def test_environmental_alarm_normalised(self):
        desc = "LTE_ENB_780100*Environmental Alarm/Temperature*3*Temperature alert"
        result = _parse_ctts_description(desc)
        assert result["alarm_category"] == "environmentalAlarm"

    def test_performance_alarm_normalised(self):
        desc = "5G_ESS_1017001*Performance Alarm/Throughput*2*Throughput degraded"
        result = _parse_ctts_description(desc)
        assert result["alarm_category"] == "performanceAlarm"


# ---------------------------------------------------------------------------
# TelcoTicketCreate — model_validator auto-parse integration
# ---------------------------------------------------------------------------

class TestTelcoTicketCreateAutoParseDescription:

    def _make(self, description: str, **kwargs) -> TelcoTicketCreate:
        return TelcoTicketCreate(
            affected_node=kwargs.pop("affected_node", "LTE_ENB_780321"),
            severity=kwargs.pop("severity", "major"),
            description=description,
            **kwargs,
        )

    def test_auto_parses_alarm_fields_when_absent(self):
        t = self._make(
            "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*Heartbeat Failure"
        )
        assert t.node_id == "LTE_ENB_780321"
        assert t.alarm_category == "communicationsAlarm"
        assert t.alarm_name == "Heartbeat Failure"
        assert t.alarm_severity_code == "1"

    def test_explicit_alarm_fields_not_overwritten(self):
        t = TelcoTicketCreate(
            affected_node="LTE_ENB_780321",
            severity="major",
            description=(
                "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*text"
            ),
            node_id="EXPLICIT_NODE",
            alarm_name="ExplicitAlarm",
        )
        # Explicit values must not be overwritten by auto-parse
        assert t.node_id == "EXPLICIT_NODE"
        assert t.alarm_name == "ExplicitAlarm"

    def test_affected_node_backfilled_from_node_id(self):
        """If affected_node is 'UNKNOWN', it should be filled from parsed node_id."""
        t = TelcoTicketCreate(
            affected_node="UNKNOWN",
            severity="major",
            description=(
                "LTE_ENB_781561*communicationsAlarm/Heartbeat Failure*1*text"
            ),
        )
        assert t.affected_node == "LTE_ENB_781561"

    def test_5g_gnb_description_fully_parsed(self):
        t = self._make(
            "5G_GNB_1039321*communicationsAlarm/SyncRefQuality*2*Sync quality degraded",
            affected_node="5G_GNB_1039321",
        )
        assert t.alarm_category == "communicationsAlarm"
        assert t.alarm_name == "SyncRefQuality"

    def test_legacy_3g_spaced_category_normalised_in_model(self):
        t = self._make(
            "Rnc15_2650*Equipment Alarm/HW Fault*1*Hardware fault",
            affected_node="Rnc15_2650",
        )
        assert t.alarm_category == "equipmentAlarm"

    def test_non_ctts_description_leaves_alarm_fields_none(self):
        t = self._make("Free-text alarm, no structured format")
        assert t.node_id is None
        assert t.alarm_category is None
        assert t.alarm_name is None

    def test_resolution_steps_coerced_from_multiline_string(self):
        t = self._make(
            "LTE_ENB_780321*equipmentAlarm/HW Fault*1*HW Fault",
            resolution_steps="Check power\nReseat module\nVerify recovery",
        )
        assert t.resolution_steps == ["Check power", "Reseat module", "Verify recovery"]

    def test_resolution_steps_empty_lines_stripped(self):
        t = self._make(
            "LTE_ENB_780321*equipmentAlarm/HW Fault*1*HW Fault",
            resolution_steps="Step 1\n\nStep 2\n\n",
        )
        assert t.resolution_steps == ["Step 1", "Step 2"]

    def test_object_class_a1_for_critical_alarm(self):
        """A1 indicates CTTS critical alarm class."""
        t = TelcoTicketCreate(
            affected_node="LTE_ENB_780321",
            severity="critical",
            description="LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*text",
            object_class="A1",
        )
        assert t.object_class == "A1"
        assert t.severity == Severity.CRITICAL

    def test_ctts_ticket_number_optional(self):
        t = self._make(
            "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*text"
        )
        assert t.ctts_ticket_number is None

    def test_network_type_3g_preserved(self):
        t = TelcoTicketCreate(
            affected_node="Rnc15_2650",
            severity="major",
            description="Rnc15_2650*Equipment Alarm/HW Fault*1*Hardware fault",
            network_type="3G",
        )
        assert t.network_type == "3G"

    @pytest.mark.parametrize("network_type", ["3G", "4G", "5G", "Huawei_CE"])
    def test_all_network_types_accepted(self, network_type):
        t = TelcoTicketCreate(
            affected_node="NODE-001",
            severity="major",
            description="Generic alarm description for NODE-001.",
            network_type=network_type,
        )
        assert t.network_type == network_type
