"""
Unit tests for the human-in-the-loop triage module.

Coverage:
  is_unresolvable()       — flagging logic for all four criteria
  HumanTriageHandler
    list_pending()        — repo delegation + TriageSummary construction
    assign()              — status guard, repo update, notes remark
    manual_resolve()      — status update, Chroma indexing, graceful failure
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.human_triage import (
    AssignRequest,
    ManualResolveRequest,
    UnresolvableReason,
)
from app.models.telco_ticket import TelcoTicketStatus
from app.review.triage import (
    AUTO_RESOLVE_THRESHOLD,
    HumanTriageHandler,
    MIN_SOP_CANDIDATES,
    MIN_SIMILAR_TICKETS,
    is_unresolvable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ticket_dict(
    ticket_id: str = "TKT-001",
    status: TelcoTicketStatus = TelcoTicketStatus.PENDING_REVIEW,
    **overrides,
) -> dict:
    base = {
        "ticket_id":    ticket_id,
        "affected_node": "NODE-X",
        "fault_type":   MagicMock(value="hardware_failure"),
        "severity":     MagicMock(value="critical"),
        "network_type": "4G",
        "alarm_name":   "HW Fault",
        "alarm_category": "equipmentAlarm",
        "location_details": "Site A",
        "description":  "Critical hardware fault on NODE-X causing cell outage.",
        "status":       status,
        "pending_review_reasons": ["no_sop_match", "low_confidence"],
        "created_at":   datetime(2024, 6, 1, 10, 0, 0),
        "updated_at":   datetime(2024, 6, 1, 10, 5, 0),
        "assigned_to":  None,
        "assigned_at":  None,
        "remarks":      None,
    }
    base.update(overrides)
    return base


def _make_handler() -> tuple[HumanTriageHandler, MagicMock, MagicMock]:
    """Return (handler, mock_repo, mock_feedback_indexer)."""
    repo      = MagicMock()
    feedback  = MagicMock()
    handler   = HumanTriageHandler(repo=repo, feedback_indexer=feedback)
    return handler, repo, feedback


# ---------------------------------------------------------------------------
# is_unresolvable — unit tests
# ---------------------------------------------------------------------------

class TestIsUnresolvable:

    def test_all_good_returns_false(self):
        flagged, reasons = is_unresolvable(
            confidence_score=0.80,
            sop_candidates_found=2,
            similar_tickets_found=3,
            fault_type="latency",
        )
        assert flagged is False
        assert reasons == []

    def test_no_sop_match_alone_flags(self):
        flagged, reasons = is_unresolvable(
            confidence_score=0.80,
            sop_candidates_found=0,
            similar_tickets_found=3,
            fault_type="latency",
        )
        assert flagged is True
        assert UnresolvableReason.NO_SOP_MATCH in reasons

    def test_no_historical_precedent_alone_flags(self):
        flagged, reasons = is_unresolvable(
            confidence_score=0.80,
            sop_candidates_found=2,
            similar_tickets_found=0,
            fault_type="latency",
        )
        assert flagged is True
        assert UnresolvableReason.NO_HISTORICAL_PRECEDENT in reasons

    def test_low_confidence_alone_flags(self):
        flagged, reasons = is_unresolvable(
            confidence_score=AUTO_RESOLVE_THRESHOLD - 0.01,
            sop_candidates_found=2,
            similar_tickets_found=3,
            fault_type="latency",
        )
        assert flagged is True
        assert UnresolvableReason.LOW_CONFIDENCE in reasons

    def test_confidence_exactly_at_threshold_not_flagged(self):
        """Boundary: confidence == 0.50 should NOT trigger LOW_CONFIDENCE (strict <)."""
        flagged, reasons = is_unresolvable(
            confidence_score=AUTO_RESOLVE_THRESHOLD,
            sop_candidates_found=2,
            similar_tickets_found=3,
            fault_type="latency",
        )
        assert UnresolvableReason.LOW_CONFIDENCE not in reasons

    def test_unknown_fault_type_flags(self):
        flagged, reasons = is_unresolvable(
            confidence_score=0.80,
            sop_candidates_found=2,
            similar_tickets_found=3,
            fault_type="unknown",
        )
        assert flagged is True
        assert UnresolvableReason.UNKNOWN_FAULT_TYPE in reasons

    def test_empty_fault_type_flags(self):
        flagged, reasons = is_unresolvable(
            confidence_score=0.80,
            sop_candidates_found=2,
            similar_tickets_found=3,
            fault_type="",
        )
        assert flagged is True
        assert UnresolvableReason.UNKNOWN_FAULT_TYPE in reasons

    def test_all_criteria_met_returns_all_reasons(self):
        flagged, reasons = is_unresolvable(
            confidence_score=0.10,
            sop_candidates_found=0,
            similar_tickets_found=0,
            fault_type="unknown",
        )
        assert flagged is True
        assert len(reasons) == 4
        assert UnresolvableReason.NO_SOP_MATCH            in reasons
        assert UnresolvableReason.NO_HISTORICAL_PRECEDENT in reasons
        assert UnresolvableReason.LOW_CONFIDENCE          in reasons
        assert UnresolvableReason.UNKNOWN_FAULT_TYPE      in reasons

    def test_min_sop_candidates_boundary(self):
        """Exactly MIN_SOP_CANDIDATES SOPs found → should NOT flag."""
        flagged, reasons = is_unresolvable(
            confidence_score=0.80,
            sop_candidates_found=MIN_SOP_CANDIDATES,
            similar_tickets_found=3,
            fault_type="latency",
        )
        assert UnresolvableReason.NO_SOP_MATCH not in reasons

    def test_min_similar_tickets_boundary(self):
        """Exactly MIN_SIMILAR_TICKETS found → should NOT flag."""
        flagged, reasons = is_unresolvable(
            confidence_score=0.80,
            sop_candidates_found=2,
            similar_tickets_found=MIN_SIMILAR_TICKETS,
            fault_type="latency",
        )
        assert UnresolvableReason.NO_HISTORICAL_PRECEDENT not in reasons


# ---------------------------------------------------------------------------
# HumanTriageHandler.list_pending
# ---------------------------------------------------------------------------

class TestListPending:

    @pytest.mark.asyncio
    async def test_returns_triage_summaries(self):
        handler, repo, _ = _make_handler()
        rows = [_make_ticket_dict("TKT-001"), _make_ticket_dict("TKT-002")]
        repo.list_pending_review = AsyncMock(return_value=rows)

        result = await handler.list_pending(limit=50)

        repo.list_pending_review.assert_called_once_with(limit=50)
        assert len(result) == 2
        assert result[0].ticket_id == "TKT-001"
        assert result[1].ticket_id == "TKT-002"

    @pytest.mark.asyncio
    async def test_reasons_deserialized_from_raw(self):
        handler, repo, _ = _make_handler()
        row = _make_ticket_dict("TKT-001", pending_review_reasons=["no_sop_match", "low_confidence"])
        repo.list_pending_review = AsyncMock(return_value=[row])

        result = await handler.list_pending()

        summary = result[0]
        assert UnresolvableReason.NO_SOP_MATCH   in summary.reasons
        assert UnresolvableReason.LOW_CONFIDENCE  in summary.reasons

    @pytest.mark.asyncio
    async def test_empty_queue_returns_empty_list(self):
        handler, repo, _ = _make_handler()
        repo.list_pending_review = AsyncMock(return_value=[])

        result = await handler.list_pending()
        assert result == []

    @pytest.mark.asyncio
    async def test_none_reasons_produces_empty_list(self):
        """Ticket with no pending_review_reasons field → empty reasons list."""
        handler, repo, _ = _make_handler()
        row = _make_ticket_dict("TKT-001", pending_review_reasons=None)
        repo.list_pending_review = AsyncMock(return_value=[row])

        result = await handler.list_pending()
        assert result[0].reasons == []

    @pytest.mark.asyncio
    async def test_uses_updated_at_as_flagged_at(self):
        handler, repo, _ = _make_handler()
        updated = datetime(2024, 7, 1, 9, 0, 0)
        row = _make_ticket_dict("TKT-001", updated_at=updated)
        repo.list_pending_review = AsyncMock(return_value=[row])

        result = await handler.list_pending()
        assert result[0].flagged_at == updated

    @pytest.mark.asyncio
    async def test_falls_back_to_created_at_when_no_updated_at(self):
        handler, repo, _ = _make_handler()
        created = datetime(2024, 6, 1, 8, 0, 0)
        row = _make_ticket_dict("TKT-001", updated_at=None, created_at=created)
        repo.list_pending_review = AsyncMock(return_value=[row])

        result = await handler.list_pending()
        assert result[0].flagged_at == created


# ---------------------------------------------------------------------------
# HumanTriageHandler.assign
# ---------------------------------------------------------------------------

class TestAssign:

    @pytest.mark.asyncio
    async def test_assign_updates_repo(self):
        handler, repo, _ = _make_handler()
        ticket = _make_ticket_dict()
        repo.get = AsyncMock(return_value=ticket)
        assigned_at = datetime(2024, 6, 1, 11, 0, 0)
        repo.assign_ticket = AsyncMock(return_value={"assigned_at": assigned_at})
        repo.update = AsyncMock(return_value=ticket)

        request = AssignRequest(assign_to="noc.engineer01")
        result = await handler.assign("TKT-001", request)

        repo.assign_ticket.assert_called_once_with("TKT-001", "noc.engineer01")
        assert result.assigned_to == "noc.engineer01"
        assert result.assigned_at == assigned_at

    @pytest.mark.asyncio
    async def test_assign_appends_notes_remark(self):
        handler, repo, _ = _make_handler()
        ticket = _make_ticket_dict(remarks="Previous remark.")
        repo.get = AsyncMock(return_value=ticket)
        repo.assign_ticket = AsyncMock(return_value={"assigned_at": datetime.utcnow()})
        repo.update = AsyncMock(return_value=ticket)

        request = AssignRequest(assign_to="noc.engineer01", notes="Check link flap on Iub.")
        await handler.assign("TKT-001", request)

        # update() should have been called to append the notes remark
        repo.update.assert_called_once()
        patch_arg = repo.update.call_args[0][1]
        assert "Check link flap on Iub." in patch_arg.remarks

    @pytest.mark.asyncio
    async def test_assign_no_notes_skips_update(self):
        handler, repo, _ = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.assign_ticket = AsyncMock(return_value={"assigned_at": datetime.utcnow()})
        repo.update = AsyncMock()

        request = AssignRequest(assign_to="noc.engineer01", notes=None)
        await handler.assign("TKT-001", request)

        repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_assign_raises_when_ticket_missing(self):
        from app.core.exceptions import TicketNotFoundError

        handler, repo, _ = _make_handler()
        repo.get = AsyncMock(return_value=None)

        with pytest.raises(TicketNotFoundError):
            await handler.assign("TKT-MISSING", AssignRequest(assign_to="eng"))

    @pytest.mark.asyncio
    async def test_assign_raises_when_not_pending_review(self):
        handler, repo, _ = _make_handler()
        ticket = _make_ticket_dict(status=TelcoTicketStatus.RESOLVED)
        repo.get = AsyncMock(return_value=ticket)

        with pytest.raises(ValueError, match="PENDING_REVIEW"):
            await handler.assign("TKT-001", AssignRequest(assign_to="eng"))

    @pytest.mark.asyncio
    async def test_assign_result_message_contains_ticket_id(self):
        handler, repo, _ = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.assign_ticket = AsyncMock(return_value={"assigned_at": datetime.utcnow()})

        result = await handler.assign("TKT-001", AssignRequest(assign_to="team.alpha"))
        assert "TKT-001" in result.message
        assert "team.alpha" in result.message


# ---------------------------------------------------------------------------
# HumanTriageHandler.manual_resolve
# ---------------------------------------------------------------------------

class TestManualResolve:

    def _default_request(self) -> ManualResolveRequest:
        return ManualResolveRequest(
            resolved_by="noc.engineer01",
            resolution_steps=["Checked cable", "Re-seated E1 connector", "Verified Iub recovery"],
            sop_reference="SOP-RAN-004",
            primary_cause="Physical cable fault",
            resolution_code="Hardware Replacement",
            notes="E1 cable found unplugged at DDF panel.",
        )

    @pytest.mark.asyncio
    async def test_manual_resolve_marks_ticket_resolved(self):
        handler, repo, feedback = _make_handler()
        ticket = _make_ticket_dict()
        repo.get = AsyncMock(return_value=ticket)
        repo.update = AsyncMock(return_value=ticket)
        feedback.index_resolved = AsyncMock()

        result = await handler.manual_resolve("TKT-001", self._default_request())

        repo.update.assert_called_once()
        patch_arg = repo.update.call_args[0][1]
        assert patch_arg.status == TelcoTicketStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_manual_resolve_stores_steps(self):
        handler, repo, feedback = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.update = AsyncMock(return_value=_make_ticket_dict())
        feedback.index_resolved = AsyncMock()

        request = self._default_request()
        result = await handler.manual_resolve("TKT-001", request)

        assert result.executed_steps == request.resolution_steps
        assert result.sop_reference  == request.sop_reference
        assert result.resolved_by    == request.resolved_by

    @pytest.mark.asyncio
    async def test_manual_resolve_indexes_training_signal(self):
        handler, repo, feedback = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.update = AsyncMock(return_value=_make_ticket_dict())
        feedback.index_resolved = AsyncMock()

        await handler.manual_resolve("TKT-001", self._default_request())

        feedback.index_resolved.assert_called_once()
        kwargs = feedback.index_resolved.call_args[1]
        assert kwargs["ticket_id"]   == "TKT-001"
        assert kwargs["reviewed_by"] == "noc.engineer01"

    @pytest.mark.asyncio
    async def test_manual_resolve_graceful_on_indexing_failure(self):
        """Chroma failure must NOT roll back the ticket status update."""
        handler, repo, feedback = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.update = AsyncMock(return_value=_make_ticket_dict())
        feedback.index_resolved = AsyncMock(side_effect=RuntimeError("Chroma unavailable"))

        result = await handler.manual_resolve("TKT-001", self._default_request())

        # Ticket is still resolved even though Chroma failed
        assert result.new_status == TelcoTicketStatus.RESOLVED.value
        assert result.indexed_as_training_signal is False

    @pytest.mark.asyncio
    async def test_manual_resolve_raises_when_ticket_missing(self):
        from app.core.exceptions import TicketNotFoundError

        handler, repo, _ = _make_handler()
        repo.get = AsyncMock(return_value=None)

        with pytest.raises(TicketNotFoundError):
            await handler.manual_resolve("TKT-MISSING", self._default_request())

    @pytest.mark.asyncio
    async def test_manual_resolve_raises_for_wrong_status(self):
        handler, repo, _ = _make_handler()
        ticket = _make_ticket_dict(status=TelcoTicketStatus.RESOLVED)
        repo.get = AsyncMock(return_value=ticket)

        with pytest.raises(ValueError, match="cannot be manually resolved"):
            await handler.manual_resolve("TKT-001", self._default_request())

    @pytest.mark.asyncio
    async def test_manual_resolve_accepts_in_progress_status(self):
        handler, repo, feedback = _make_handler()
        ticket = _make_ticket_dict(status=TelcoTicketStatus.IN_PROGRESS)
        repo.get = AsyncMock(return_value=ticket)
        repo.update = AsyncMock(return_value=ticket)
        feedback.index_resolved = AsyncMock()

        # Should not raise — IN_PROGRESS is an allowed status
        result = await handler.manual_resolve("TKT-001", self._default_request())
        assert result.new_status == TelcoTicketStatus.RESOLVED.value

    @pytest.mark.asyncio
    async def test_manual_resolve_result_indicates_indexed(self):
        handler, repo, feedback = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.update = AsyncMock(return_value=_make_ticket_dict())
        feedback.index_resolved = AsyncMock()

        result = await handler.manual_resolve("TKT-001", self._default_request())
        assert result.indexed_as_training_signal is True

    @pytest.mark.asyncio
    async def test_manual_resolve_remark_includes_resolved_by(self):
        handler, repo, feedback = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.update = AsyncMock(return_value=_make_ticket_dict())
        feedback.index_resolved = AsyncMock()

        await handler.manual_resolve("TKT-001", self._default_request())

        patch_arg = repo.update.call_args[0][1]
        assert "noc.engineer01" in patch_arg.remarks

    @pytest.mark.asyncio
    async def test_manual_resolve_no_sop_reference(self):
        """Resolution without SOP reference still works (ad-hoc fix)."""
        handler, repo, feedback = _make_handler()
        repo.get = AsyncMock(return_value=_make_ticket_dict())
        repo.update = AsyncMock(return_value=_make_ticket_dict())
        feedback.index_resolved = AsyncMock()

        request = ManualResolveRequest(
            resolved_by="noc.engineer02",
            resolution_steps=["Rebooted NodeB", "Confirmed recovery"],
        )
        result = await handler.manual_resolve("TKT-001", request)
        assert result.sop_reference is None
