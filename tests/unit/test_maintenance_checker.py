"""
Unit tests for MaintenanceChecker.

The MaintenanceStore is mocked so no database is required.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.maintenance.checker import MaintenanceChecker
from app.maintenance.models import (
    MaintenanceCheckResult,
    MaintenanceType,
    PlannedMaintenance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 10, 12, 0, 0)  # fixed reference time


def _make_window(
    node: str = "NODE-ATL-01",
    start_offset_h: int = -1,
    end_offset_h: int = 2,
    maint_type: MaintenanceType = MaintenanceType.PLANNED,
    external_ref: str | None = "CR-12345",
) -> PlannedMaintenance:
    return PlannedMaintenance(
        maintenance_id="MW-001",
        title="Routine fibre splicing",
        maintenance_type=maint_type,
        affected_nodes=[node],
        start_time=_NOW + timedelta(hours=start_offset_h),
        end_time=_NOW + timedelta(hours=end_offset_h),
        description="Scheduled maintenance",
        contact="noc-team@example.com",
        external_ref=external_ref,
    )


def _make_store(window: PlannedMaintenance | None) -> MagicMock:
    store = MagicMock()
    store.get_for_node = AsyncMock(return_value=window)
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMaintenanceChecker:
    @pytest.mark.asyncio
    async def test_no_maintenance_window(self):
        checker = MaintenanceChecker(store=_make_store(None))
        result = await checker.check("NODE-ATL-01", at=_NOW)

        assert result.in_maintenance is False
        assert result.dispatch_blocked is False
        assert result.window is None
        assert "No active" in result.summary

    @pytest.mark.asyncio
    async def test_active_maintenance_blocks_dispatch(self):
        window = _make_window()
        checker = MaintenanceChecker(store=_make_store(window))
        result = await checker.check("NODE-ATL-01", at=_NOW)

        assert result.in_maintenance is True
        assert result.dispatch_blocked is True
        assert result.window == window
        assert "CR-12345" in result.summary

    @pytest.mark.asyncio
    async def test_result_carries_window_metadata(self):
        window = _make_window(node="BS-MUM-042", external_ref="RFC-99")
        checker = MaintenanceChecker(store=_make_store(window))
        result = await checker.check("BS-MUM-042", at=_NOW)

        assert result.node == "BS-MUM-042"
        assert result.window.external_ref == "RFC-99"
        assert result.window.maintenance_type == MaintenanceType.PLANNED

    @pytest.mark.asyncio
    async def test_emergency_maintenance_also_blocks(self):
        window = _make_window(maint_type=MaintenanceType.EMERGENCY)
        checker = MaintenanceChecker(store=_make_store(window))
        result = await checker.check("NODE-ATL-01", at=_NOW)

        assert result.dispatch_blocked is True

    @pytest.mark.asyncio
    async def test_store_called_with_node_and_time(self):
        store = _make_store(None)
        checker = MaintenanceChecker(store=store)
        await checker.check("NODE-XYZ", at=_NOW)

        store.get_for_node.assert_awaited_once_with("NODE-XYZ", at=_NOW)

    @pytest.mark.asyncio
    async def test_defaults_to_utcnow_when_no_timestamp(self):
        store = _make_store(None)
        checker = MaintenanceChecker(store=store)
        await checker.check("NODE-XYZ")  # no `at` argument

        # Should still be called once with *some* datetime
        store.get_for_node.assert_awaited_once()
        call_args = store.get_for_node.call_args
        at_arg = call_args.kwargs.get("at") or call_args.args[1]
        assert isinstance(at_arg, datetime)

    @pytest.mark.asyncio
    async def test_none_found_result_structure(self):
        checker = MaintenanceChecker(store=_make_store(None))
        result = await checker.check("X-NODE")

        assert isinstance(result, MaintenanceCheckResult)
        assert result.node == "X-NODE"
        assert result.window is None

    @pytest.mark.asyncio
    async def test_found_result_structure(self):
        window = _make_window()
        checker = MaintenanceChecker(store=_make_store(window))
        result = await checker.check("NODE-ATL-01", at=_NOW)

        assert isinstance(result, MaintenanceCheckResult)
        assert result.node == "NODE-ATL-01"
        assert result.in_maintenance is True
        assert result.window is not None
