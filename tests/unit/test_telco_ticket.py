"""Unit tests for TelcoTicket Pydantic models and TelcoTicketRepository."""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.telco_ticket import (
    FaultType,
    Severity,
    TelcoTicketCreate,
    TelcoTicketStatus,
    TelcoTicketUpdate,
)
from app.storage.telco_repositories import TelcoTicketRepository, TelcoTicketRow


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------

class TestTelcoTicketCreate:
    def test_valid_minimal_ticket(self):
        t = TelcoTicketCreate(
            fault_type=FaultType.SIGNAL_LOSS,
            affected_node="BS-MUM-042",
            severity=Severity.HIGH,
            description="Signal strength dropped below threshold for 3200 subscribers.",
        )
        assert t.ticket_id.startswith("TKT-")
        assert t.resolution_steps == []
        assert t.sop_id is None
        assert isinstance(t.timestamp, datetime)

    def test_auto_generates_ticket_id(self):
        t1 = TelcoTicketCreate(fault_type=FaultType.LATENCY, affected_node="N1", severity=Severity.LOW, description="Minor latency increase detected on backhaul link.")
        t2 = TelcoTicketCreate(fault_type=FaultType.LATENCY, affected_node="N1", severity=Severity.LOW, description="Minor latency increase detected on backhaul link.")
        assert t1.ticket_id != t2.ticket_id

    def test_explicit_ticket_id_preserved(self):
        t = TelcoTicketCreate(
            ticket_id="TKT-CUSTOM01",
            fault_type=FaultType.NODE_DOWN,
            affected_node="NODE-ATL-01",
            severity=Severity.CRITICAL,
            description="Core node NODE-ATL-01 is completely unreachable from NMS.",
        )
        assert t.ticket_id == "TKT-CUSTOM01"

    def test_resolution_steps_coerced_from_string(self):
        t = TelcoTicketCreate(
            fault_type=FaultType.NODE_DOWN,
            affected_node="NODE-ATL-01",
            severity=Severity.CRITICAL,
            description="Core node NODE-ATL-01 is completely unreachable from NMS.",
            resolution_steps="Ping node\nSSH into router\nRestart interface",
        )
        assert t.resolution_steps == ["Ping node", "SSH into router", "Restart interface"]

    def test_description_too_short_raises(self):
        with pytest.raises(Exception):
            TelcoTicketCreate(
                fault_type=FaultType.LATENCY,
                affected_node="N1",
                severity=Severity.LOW,
                description="Short",
            )

    def test_affected_node_required(self):
        with pytest.raises(Exception):
            TelcoTicketCreate(
                fault_type=FaultType.LATENCY,
                affected_node="",
                severity=Severity.LOW,
                description="Some valid description of the fault detected.",
            )

    def test_all_fault_types_valid(self):
        for ft in FaultType:
            t = TelcoTicketCreate(
                fault_type=ft,
                affected_node="NODE-X",
                severity=Severity.MEDIUM,
                description="Automated test ticket for fault type validation coverage.",
            )
            assert t.fault_type == ft

    def test_all_severities_valid(self):
        for sev in Severity:
            t = TelcoTicketCreate(
                fault_type=FaultType.LATENCY,
                affected_node="NODE-X",
                severity=sev,
                description="Automated test ticket for severity validation coverage.",
            )
            assert t.severity == sev

    def test_sop_id_stored(self):
        t = TelcoTicketCreate(
            fault_type=FaultType.SIGNAL_LOSS,
            affected_node="BS-DEL-011",
            severity=Severity.HIGH,
            description="Signal loss detected on sector 3 of BS-DEL-011 base station.",
            sop_id="SOP-RF-007",
        )
        assert t.sop_id == "SOP-RF-007"


class TestCTTSDescriptionParser:
    """
    Tests for the _parse_ctts_description helper and its integration with
    the TelcoTicketCreate model_validator.

    Covers two non-standard variants observed in 3G/legacy CTTS exports:
    1. Spaced alarm categories  — "Equipment Alarm" → "equipmentAlarm"
    2. Sub-category prefixes    — "UNKNOWN/DigitalCable_CableFailure" → "DigitalCable_CableFailure"
    """

    _3G_DESCRIPTION = (
        "Rnc17_5652*Equipment Alarm/UNKNOWN/DigitalCable_CableFailure*1*DigitalCable_CableFailure\n\n"
        "FERRARI Site DigitalCable_CableFailure UtranCell: 5652"
    )
    _STANDARD_DESCRIPTION = (
        "LTE_ENB_780321*equipmentAlarm/HW Fault*1*HW Fault\n\n"
        "HW Fault Unknown"
    )

    def test_standard_description_parses_alarm_category(self):
        t = TelcoTicketCreate(
            fault_type=FaultType.HARDWARE_FAILURE,
            affected_node="LTE_ENB_780321",
            severity=Severity.CRITICAL,
            description=self._STANDARD_DESCRIPTION,
        )
        assert t.alarm_category == "equipmentAlarm"

    def test_standard_description_parses_alarm_name(self):
        t = TelcoTicketCreate(
            fault_type=FaultType.HARDWARE_FAILURE,
            affected_node="LTE_ENB_780321",
            severity=Severity.CRITICAL,
            description=self._STANDARD_DESCRIPTION,
        )
        assert t.alarm_name == "HW Fault"

    def test_spaced_alarm_category_normalised_to_camelcase(self):
        """'Equipment Alarm' (with space) must become 'equipmentAlarm'."""
        t = TelcoTicketCreate(
            fault_type=FaultType.HARDWARE_FAILURE,
            affected_node="RNC_Rnc17_5652",
            severity=Severity.CRITICAL,
            description=self._3G_DESCRIPTION,
        )
        assert t.alarm_category == "equipmentAlarm"

    def test_unknown_prefix_stripped_from_alarm_name(self):
        """'UNKNOWN/DigitalCable_CableFailure' must become 'DigitalCable_CableFailure'."""
        t = TelcoTicketCreate(
            fault_type=FaultType.HARDWARE_FAILURE,
            affected_node="RNC_Rnc17_5652",
            severity=Severity.CRITICAL,
            description=self._3G_DESCRIPTION,
        )
        assert t.alarm_name == "DigitalCable_CableFailure"

    def test_node_id_parsed_from_3g_description(self):
        t = TelcoTicketCreate(
            fault_type=FaultType.HARDWARE_FAILURE,
            affected_node="RNC_Rnc17_5652",
            severity=Severity.CRITICAL,
            description=self._3G_DESCRIPTION,
        )
        assert t.node_id == "Rnc17_5652"

    def test_severity_code_1_parsed(self):
        t = TelcoTicketCreate(
            fault_type=FaultType.HARDWARE_FAILURE,
            affected_node="RNC_Rnc17_5652",
            severity=Severity.CRITICAL,
            description=self._3G_DESCRIPTION,
        )
        assert t.alarm_severity_code == "1"

    def test_communications_alarm_normalised(self):
        desc = (
            "LTE_ENB_781561*Communications Alarm/Heartbeat Failure*1*Heartbeat Failure\n\n"
            "Heartbeat Failure Unknown"
        )
        t = TelcoTicketCreate(
            fault_type=FaultType.NODE_DOWN,
            affected_node="LTE_ENB_781561",
            severity=Severity.CRITICAL,
            description=desc,
        )
        assert t.alarm_category == "communicationsAlarm"

    def test_processing_error_alarm_normalised(self):
        desc = (
            "NR_GNB_1041002*Processing Error Alarm/SW Error*2*SW Error\n\n"
            "SW Error detected on baseband unit"
        )
        t = TelcoTicketCreate(
            fault_type=FaultType.SW_ERROR,
            affected_node="NR_GNB_1041002",
            severity=Severity.MAJOR,
            description=desc,
        )
        assert t.alarm_category == "processingErrorAlarm"

    def test_unrecognised_spaced_category_preserved_as_is(self):
        """Categories not in the normalisation map are passed through verbatim."""
        desc = (
            "NODE_X*Custom Alarm/SomeFault*2*SomeFault\n\n"
            "Some fault description with enough detail."
        )
        t = TelcoTicketCreate(
            fault_type=FaultType.UNKNOWN,
            affected_node="NODE_X",
            severity=Severity.MAJOR,
            description=desc,
        )
        assert t.alarm_category == "Custom Alarm"

    def test_alarm_name_without_prefix_unchanged(self):
        """Standard alarm names (no ALL-CAPS prefix) must not be modified."""
        t = TelcoTicketCreate(
            fault_type=FaultType.HARDWARE_FAILURE,
            affected_node="LTE_ENB_780321",
            severity=Severity.CRITICAL,
            description=self._STANDARD_DESCRIPTION,
        )
        # "HW Fault" has a lowercase second word — regex must not strip it
        assert t.alarm_name == "HW Fault"

    def test_non_ctts_description_produces_no_parsed_fields(self):
        """Free-text descriptions without CTTS format return None for parsed fields."""
        t = TelcoTicketCreate(
            fault_type=FaultType.UNKNOWN,
            affected_node="NODE_X",
            severity=Severity.MAJOR,
            description="Node is experiencing intermittent connectivity issues on the uplink.",
        )
        assert t.alarm_category is None
        assert t.alarm_name is None
        assert t.node_id is None


class TestTelcoTicketUpdate:
    def test_partial_update_status_only(self):
        patch = TelcoTicketUpdate(status=TelcoTicketStatus.IN_PROGRESS)
        assert patch.status == TelcoTicketStatus.IN_PROGRESS
        assert patch.resolution_steps is None
        assert patch.sop_id is None

    def test_partial_update_steps_only(self):
        patch = TelcoTicketUpdate(resolution_steps=["Step 1", "Step 2"])
        assert patch.resolution_steps == ["Step 1", "Step 2"]
        assert patch.status is None

    def test_extra_fields_forbidden(self):
        with pytest.raises(Exception):
            TelcoTicketUpdate(fault_type="latency")  # type: ignore


# ---------------------------------------------------------------------------
# Repository (mocked session)
# ---------------------------------------------------------------------------

def _make_row(ticket_id="TKT-ABCD1234") -> TelcoTicketRow:
    return TelcoTicketRow(
        ticket_id=ticket_id,
        timestamp=datetime(2024, 6, 1, 12, 0, 0),
        fault_type=FaultType.NODE_DOWN.value,
        affected_node="NODE-ATL-01",
        severity=Severity.CRITICAL.value,
        status=TelcoTicketStatus.OPEN.value,
        description="Core router NODE-ATL-01 is unreachable. Full sector outage.",
        resolution_steps=json.dumps(["Ping node", "Restart BGP session"]),
        sop_id="SOP-NET-003",
        created_at=datetime(2024, 6, 1, 12, 0, 0),
        updated_at=datetime(2024, 6, 1, 12, 0, 0),
    )


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session):
    return TelcoTicketRepository(mock_session)


@pytest.mark.asyncio
async def test_create_calls_session_add(repo, mock_session):
    ticket = TelcoTicketCreate(
        fault_type=FaultType.NODE_DOWN,
        affected_node="NODE-ATL-01",
        severity=Severity.CRITICAL,
        description="Core router NODE-ATL-01 is unreachable. Full sector outage detected.",
        sop_id="SOP-NET-003",
    )
    # simulate refresh populating ticket_id
    mock_session.refresh = AsyncMock(side_effect=lambda r: None)

    result_id = await repo.create(ticket)
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    assert result_id == ticket.ticket_id


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(repo, mock_session):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await repo.get("TKT-MISSING")
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_dict_with_correct_types(repo, mock_session):
    row = _make_row()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await repo.get("TKT-ABCD1234")

    assert result is not None
    assert result["ticket_id"] == "TKT-ABCD1234"
    assert result["fault_type"] == FaultType.NODE_DOWN
    assert result["severity"] == Severity.CRITICAL
    assert result["status"] == TelcoTicketStatus.OPEN
    assert result["resolution_steps"] == ["Ping node", "Restart BGP session"]
    assert result["sop_id"] == "SOP-NET-003"


@pytest.mark.asyncio
async def test_update_returns_none_when_ticket_missing(repo, mock_session):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await repo.update("TKT-MISSING", TelcoTicketUpdate(status=TelcoTicketStatus.RESOLVED))
    assert result is None


@pytest.mark.asyncio
async def test_update_patches_status_and_steps(repo, mock_session):
    row = _make_row()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.refresh = AsyncMock(side_effect=lambda r: None)

    patch = TelcoTicketUpdate(
        status=TelcoTicketStatus.RESOLVED,
        resolution_steps=["Restarted BGP session", "Verified routing table"],
    )
    result = await repo.update("TKT-ABCD1234", patch)

    assert row.status == TelcoTicketStatus.RESOLVED.value
    assert json.loads(row.resolution_steps) == ["Restarted BGP session", "Verified routing table"]
    assert result is not None
