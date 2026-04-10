"""
Unit tests for CorrelationEngine.

All sub-components (AlarmChecker, MaintenanceChecker, MatchingEngine,
SOPRetriever) are mocked so this remains a pure unit test.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.alarms.models import AlarmCheckResult, AlarmStatus
from app.correlation.engine import CorrelationEngine
from app.correlation.models import CorrelationContext, DispatchMode
from app.maintenance.models import MaintenanceCheckResult
from app.models.telco_ticket import FaultType, Severity, TelcoTicketCreate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ticket(
    fault_type: FaultType = FaultType.LATENCY,
    severity: Severity = Severity.HIGH,
    node: str = "NODE-ATL-01",
) -> TelcoTicketCreate:
    return TelcoTicketCreate(
        fault_type=fault_type,
        affected_node=node,
        severity=severity,
        description="High latency detected on backbone link between ATL and ORD.",
    )


def _alarm_active(node: str = "NODE-ATL-01") -> AlarmCheckResult:
    return AlarmCheckResult(
        node=node,
        alarm_found=True,
        status=AlarmStatus.ACTIVE,
        alarm_id="ALM-001",
        alarm_type="latency",
        severity="high",
        raised_at=datetime(2026, 4, 10, 8, 0),
        dispatch_blocked=False,
        summary="Alarm active.",
    )


def _alarm_cleared(node: str = "NODE-ATL-01") -> AlarmCheckResult:
    return AlarmCheckResult(
        node=node,
        alarm_found=True,
        status=AlarmStatus.CLEARED,
        alarm_id="ALM-001",
        alarm_type="latency",
        severity="high",
        raised_at=datetime(2026, 4, 10, 8, 0),
        cleared_at=datetime(2026, 4, 10, 9, 0),
        dispatch_blocked=True,
        summary="Alarm cleared.",
    )


def _no_alarm(node: str = "NODE-ATL-01") -> AlarmCheckResult:
    return AlarmCheckResult.not_found(node)


def _no_maintenance(node: str = "NODE-ATL-01") -> MaintenanceCheckResult:
    return MaintenanceCheckResult.none_found(node)


def _in_maintenance(node: str = "NODE-ATL-01") -> MaintenanceCheckResult:
    from app.maintenance.models import MaintenanceType, PlannedMaintenance
    window = PlannedMaintenance(
        maintenance_id="MW-001",
        title="Emergency router swap",
        maintenance_type=MaintenanceType.EMERGENCY,
        affected_nodes=[node],
        start_time=datetime(2026, 4, 10, 7, 0),
        end_time=datetime(2026, 4, 10, 15, 0),
    )
    return MaintenanceCheckResult.found(node, window)


def _make_engine(
    alarm_result: AlarmCheckResult,
    maint_result: MaintenanceCheckResult,
    similar_tickets: list | None = None,
    sop_matches: list | None = None,
) -> CorrelationEngine:
    alarm_checker = MagicMock()
    alarm_checker.check = AsyncMock(return_value=alarm_result)

    maint_checker = MagicMock()
    maint_checker.check = AsyncMock(return_value=maint_result)

    matching = MagicMock()
    matching.find_similar = AsyncMock(return_value=similar_tickets or [])

    sop = MagicMock()
    sop.retrieve = AsyncMock(return_value=sop_matches or [])

    return CorrelationEngine(
        alarm_checker=alarm_checker,
        maintenance_checker=maint_checker,
        matching_engine=matching,
        sop_retriever=sop,
        similar_top_k=3,
        sop_top_k=2,
    )


# ---------------------------------------------------------------------------
# Tests — normal (non-short-circuit) path
# ---------------------------------------------------------------------------

class TestCorrelationEngineNormalPath:
    @pytest.mark.asyncio
    async def test_returns_correlation_context(self):
        engine = _make_engine(_alarm_active(), _no_maintenance())
        ctx = await engine.correlate(_make_ticket())

        assert isinstance(ctx, CorrelationContext)

    @pytest.mark.asyncio
    async def test_active_alarm_no_maintenance_no_short_circuit(self):
        engine = _make_engine(_alarm_active(), _no_maintenance())
        ctx = await engine.correlate(_make_ticket())

        assert ctx.should_short_circuit is False

    @pytest.mark.asyncio
    async def test_no_alarm_no_maintenance_no_short_circuit(self):
        engine = _make_engine(_no_alarm(), _no_maintenance())
        ctx = await engine.correlate(_make_ticket())

        assert ctx.should_short_circuit is False

    @pytest.mark.asyncio
    async def test_context_carries_ticket_metadata(self):
        ticket = _make_ticket(node="BS-MUM-042", fault_type=FaultType.NODE_DOWN)
        engine = _make_engine(_alarm_active("BS-MUM-042"), _no_maintenance("BS-MUM-042"))
        ctx = await engine.correlate(ticket)

        assert ctx.affected_node == "BS-MUM-042"
        assert ctx.fault_type == FaultType.NODE_DOWN.value

    @pytest.mark.asyncio
    async def test_remote_feasibility_assessed(self):
        engine = _make_engine(_alarm_active(), _no_maintenance())
        ctx = await engine.correlate(_make_ticket(fault_type=FaultType.LATENCY))

        # LATENCY is in USUALLY_REMOTE_FAULTS → feasible should be True
        assert ctx.remote_feasibility is not None
        assert ctx.remote_feasibility.feasible is True

    @pytest.mark.asyncio
    async def test_hardware_failure_not_remote_feasible(self):
        engine = _make_engine(_alarm_active(), _no_maintenance())
        ctx = await engine.correlate(_make_ticket(fault_type=FaultType.HARDWARE_FAILURE))

        assert ctx.remote_feasibility.feasible is False


# ---------------------------------------------------------------------------
# Tests — short-circuit path
# ---------------------------------------------------------------------------

class TestCorrelationEngineShortCircuit:
    @pytest.mark.asyncio
    async def test_cleared_alarm_triggers_short_circuit(self):
        engine = _make_engine(_alarm_cleared(), _no_maintenance())
        ctx = await engine.correlate(_make_ticket())

        assert ctx.should_short_circuit is True
        assert "cleared" in ctx.short_circuit_reason.lower()

    @pytest.mark.asyncio
    async def test_in_maintenance_triggers_short_circuit(self):
        engine = _make_engine(_alarm_active(), _in_maintenance())
        ctx = await engine.correlate(_make_ticket())

        assert ctx.should_short_circuit is True
        assert "maintenance" in ctx.short_circuit_reason.lower()

    @pytest.mark.asyncio
    async def test_both_cleared_and_maintenance_triggers_short_circuit(self):
        engine = _make_engine(_alarm_cleared(), _in_maintenance())
        ctx = await engine.correlate(_make_ticket())

        assert ctx.should_short_circuit is True


# ---------------------------------------------------------------------------
# Tests — resilience: individual check failures are non-fatal
# ---------------------------------------------------------------------------

class TestCorrelationEngineResilience:
    @pytest.mark.asyncio
    async def test_alarm_checker_exception_falls_back_to_not_found(self):
        alarm_checker = MagicMock()
        alarm_checker.check = AsyncMock(side_effect=RuntimeError("NMS timeout"))

        maint_checker = MagicMock()
        maint_checker.check = AsyncMock(return_value=_no_maintenance())

        matching = MagicMock()
        matching.find_similar = AsyncMock(return_value=[])
        sop = MagicMock()
        sop.retrieve = AsyncMock(return_value=[])

        engine = CorrelationEngine(
            alarm_checker=alarm_checker,
            maintenance_checker=maint_checker,
            matching_engine=matching,
            sop_retriever=sop,
        )
        # Should not raise — falls back to AlarmCheckResult.not_found
        ctx = await engine.correlate(_make_ticket())
        assert ctx.alarm_check.alarm_found is False

    @pytest.mark.asyncio
    async def test_maintenance_checker_exception_falls_back_to_none_found(self):
        alarm_checker = MagicMock()
        alarm_checker.check = AsyncMock(return_value=_no_alarm())

        maint_checker = MagicMock()
        maint_checker.check = AsyncMock(side_effect=ConnectionError("DB unavailable"))

        matching = MagicMock()
        matching.find_similar = AsyncMock(return_value=[])
        sop = MagicMock()
        sop.retrieve = AsyncMock(return_value=[])

        engine = CorrelationEngine(
            alarm_checker=alarm_checker,
            maintenance_checker=maint_checker,
            matching_engine=matching,
            sop_retriever=sop,
        )
        ctx = await engine.correlate(_make_ticket())
        assert ctx.maintenance_check.in_maintenance is False

    @pytest.mark.asyncio
    async def test_matching_exception_yields_empty_similar_tickets(self):
        alarm_checker = MagicMock()
        alarm_checker.check = AsyncMock(return_value=_no_alarm())
        maint_checker = MagicMock()
        maint_checker.check = AsyncMock(return_value=_no_maintenance())

        matching = MagicMock()
        matching.find_similar = AsyncMock(side_effect=Exception("Chroma unavailable"))
        sop = MagicMock()
        sop.retrieve = AsyncMock(return_value=[])

        engine = CorrelationEngine(
            alarm_checker=alarm_checker,
            maintenance_checker=maint_checker,
            matching_engine=matching,
            sop_retriever=sop,
        )
        ctx = await engine.correlate(_make_ticket())
        assert ctx.similar_tickets == []
