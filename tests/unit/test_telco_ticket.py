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
