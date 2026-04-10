"""
Unit tests for AlarmChecker.

The AlarmStore is mocked so no database is required.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.alarms.checker import AlarmChecker
from app.alarms.models import AlarmCheckResult, AlarmRecord, AlarmStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_alarm(
    alarm_id: str = "ALM-001",
    node: str = "NODE-ATL-01",
    alarm_type: str = "node_down",
    status: AlarmStatus = AlarmStatus.ACTIVE,
    cleared_at: datetime | None = None,
) -> AlarmRecord:
    return AlarmRecord(
        alarm_id=alarm_id,
        affected_node=node,
        alarm_type=alarm_type,
        severity="high",
        raised_at=datetime(2026, 4, 10, 8, 0, 0),
        cleared_at=cleared_at,
        status=status,
    )


def _make_store(alarm: AlarmRecord | None) -> MagicMock:
    store = MagicMock()
    store.get_latest_for_node = AsyncMock(return_value=alarm)
    store.get_active_for_node = AsyncMock(return_value=[alarm] if alarm else [])
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAlarmChecker:
    @pytest.mark.asyncio
    async def test_no_alarm_found(self):
        checker = AlarmChecker(store=_make_store(None))
        result = await checker.check("NODE-ATL-01")

        assert result.alarm_found is False
        assert result.dispatch_blocked is False
        assert "No alarm" in result.summary

    @pytest.mark.asyncio
    async def test_active_alarm_does_not_block(self):
        alarm = _make_alarm(status=AlarmStatus.ACTIVE)
        checker = AlarmChecker(store=_make_store(alarm))
        result = await checker.check("NODE-ATL-01", alarm_type="node_down")

        assert result.alarm_found is True
        assert result.status == AlarmStatus.ACTIVE
        assert result.dispatch_blocked is False
        assert result.alarm_id == "ALM-001"

    @pytest.mark.asyncio
    async def test_cleared_alarm_blocks_dispatch(self):
        cleared_time = datetime(2026, 4, 10, 9, 30, 0)
        alarm = _make_alarm(
            status=AlarmStatus.CLEARED,
            cleared_at=cleared_time,
        )
        checker = AlarmChecker(store=_make_store(alarm))
        result = await checker.check("NODE-ATL-01")

        assert result.alarm_found is True
        assert result.status == AlarmStatus.CLEARED
        assert result.dispatch_blocked is True
        assert result.cleared_at == cleared_time
        assert "CLEARED" in result.summary

    @pytest.mark.asyncio
    async def test_acknowledged_alarm_treated_as_active(self):
        alarm = _make_alarm(status=AlarmStatus.ACKNOWLEDGED)
        checker = AlarmChecker(store=_make_store(alarm))
        result = await checker.check("NODE-ATL-01")

        # ACKNOWLEDGED is not CLEARED → should NOT block dispatch
        assert result.dispatch_blocked is False
        assert result.status == AlarmStatus.ACTIVE   # checker maps to active

    @pytest.mark.asyncio
    async def test_store_called_with_correct_args(self):
        store = _make_store(None)
        checker = AlarmChecker(store=store)
        await checker.check("BS-MUM-042", alarm_type="signal_loss")

        store.get_latest_for_node.assert_awaited_once_with("BS-MUM-042", "signal_loss")

    @pytest.mark.asyncio
    async def test_check_any_active_true(self):
        alarm = _make_alarm(status=AlarmStatus.ACTIVE)
        store = _make_store(alarm)
        checker = AlarmChecker(store=store)
        assert await checker.check_any_active("NODE-ATL-01") is True

    @pytest.mark.asyncio
    async def test_check_any_active_false(self):
        store = _make_store(None)
        checker = AlarmChecker(store=store)
        assert await checker.check_any_active("NODE-ATL-01") is False

    @pytest.mark.asyncio
    async def test_not_found_result_structure(self):
        checker = AlarmChecker(store=_make_store(None))
        result = await checker.check("UNKNOWN-NODE")

        assert isinstance(result, AlarmCheckResult)
        assert result.node == "UNKNOWN-NODE"
        assert result.status is None
        assert result.alarm_id is None

    @pytest.mark.asyncio
    async def test_active_result_carries_alarm_metadata(self):
        alarm = _make_alarm(
            alarm_id="ALM-XYZ",
            alarm_type="latency",
            status=AlarmStatus.ACTIVE,
        )
        checker = AlarmChecker(store=_make_store(alarm))
        result = await checker.check("NODE-ATL-01", alarm_type="latency")

        assert result.alarm_id == "ALM-XYZ"
        assert result.alarm_type == "latency"
        assert result.severity == "high"
