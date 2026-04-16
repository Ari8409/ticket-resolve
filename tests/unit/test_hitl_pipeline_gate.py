"""
Unit tests for the human-in-the-loop gate inside run_telco_resolution_pipeline().

Specifically tests the post-agent decision branching:
  • tickets that pass all criteria → RESOLVED
  • tickets that fail any criterion → PENDING_REVIEW (flag_pending_review called)
  • short-circuit HOLD path is not affected by the HITL gate
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.telco_ticket import FaultType, Severity, TelcoTicketCreate, TelcoTicketStatus
from app.tasks.background import run_telco_resolution_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ticket(fault_type=FaultType.LATENCY) -> TelcoTicketCreate:
    return TelcoTicketCreate(
        ticket_id="TKT-HITL-001",
        affected_node="NODE-HITL-01",
        severity=Severity.HIGH,
        fault_type=fault_type,
        description="Minor latency spike detected on backhaul link to NODE-HITL-01.",
    )


def _make_correlation_ctx(
    sop_matches: int = 2,
    similar_tickets: int = 3,
    short_circuit: bool = False,
) -> MagicMock:
    ctx = MagicMock()
    ctx.should_short_circuit = short_circuit
    ctx.short_circuit_reason = "Test short-circuit" if short_circuit else ""
    ctx.sop_matches      = [MagicMock()] * sop_matches
    ctx.similar_tickets  = [MagicMock()] * similar_tickets
    ctx.alarm_check      = MagicMock()
    ctx.maintenance_check = MagicMock()
    return ctx


def _make_decision(confidence: float = 0.85) -> MagicMock:
    decision = MagicMock()
    decision.confidence_score     = confidence
    decision.dispatch_mode        = MagicMock(value="remote")
    decision.escalation_required  = False
    decision.ranked_sops          = []
    decision.short_circuited      = False
    return decision


async def _run_pipeline(
    ticket=None,
    correlation_ctx=None,
    decision=None,
    repo=None,
):
    """Convenience wrapper — sets up all dependencies with sensible defaults."""
    if ticket          is None: ticket          = _make_ticket()
    if correlation_ctx is None: correlation_ctx = _make_correlation_ctx()
    if decision        is None: decision        = _make_decision()
    if repo            is None: repo            = MagicMock()

    repo.update_status           = AsyncMock()
    repo.save_dispatch_decision  = AsyncMock()
    repo.flag_pending_review     = AsyncMock()

    matching_engine = MagicMock()
    matching_engine.index_telco_ticket = AsyncMock()

    correlation_engine = MagicMock()
    correlation_engine.correlate = AsyncMock(return_value=correlation_ctx)

    agent = MagicMock()
    agent.resolve = AsyncMock(return_value=decision)

    await run_telco_resolution_pipeline(
        ticket_id="TKT-HITL-001",
        ticket=ticket,
        matching_engine=matching_engine,
        correlation_engine=correlation_engine,
        agent=agent,
        repo=repo,
        fault_classifier=None,
    )
    return repo


# ---------------------------------------------------------------------------
# Tests — normal (non-short-circuit) path
# ---------------------------------------------------------------------------

class TestHITLGate:

    @pytest.mark.asyncio
    async def test_confident_ticket_auto_resolves(self):
        """High confidence + SOP + history → RESOLVED, no flag."""
        ctx = _make_correlation_ctx(sop_matches=2, similar_tickets=3)
        decision = _make_decision(confidence=0.90)

        repo = await _run_pipeline(correlation_ctx=ctx, decision=decision)

        repo.update_status.assert_called_with("TKT-HITL-001", TelcoTicketStatus.RESOLVED)
        repo.flag_pending_review.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sop_flags_pending_review(self):
        """Zero SOP candidates → PENDING_REVIEW regardless of confidence."""
        ctx = _make_correlation_ctx(sop_matches=0, similar_tickets=3)
        decision = _make_decision(confidence=0.90)  # confidence is fine

        repo = await _run_pipeline(correlation_ctx=ctx, decision=decision)

        repo.flag_pending_review.assert_called_once()
        call_args = repo.flag_pending_review.call_args[0]
        assert "no_sop_match" in call_args[1]
        # RESOLVED must NOT be called on the repo when flagging
        resolved_calls = [
            c for c in repo.update_status.call_args_list
            if c[0][1] == TelcoTicketStatus.RESOLVED
        ]
        assert len(resolved_calls) == 0

    @pytest.mark.asyncio
    async def test_no_similar_tickets_flags_pending_review(self):
        """Zero similar tickets → PENDING_REVIEW."""
        ctx = _make_correlation_ctx(sop_matches=2, similar_tickets=0)
        decision = _make_decision(confidence=0.90)

        repo = await _run_pipeline(correlation_ctx=ctx, decision=decision)

        repo.flag_pending_review.assert_called_once()
        reasons = repo.flag_pending_review.call_args[0][1]
        assert "no_historical_precedent" in reasons

    @pytest.mark.asyncio
    async def test_low_confidence_flags_pending_review(self):
        """Confidence below threshold → PENDING_REVIEW."""
        ctx = _make_correlation_ctx(sop_matches=2, similar_tickets=3)
        decision = _make_decision(confidence=0.40)  # below 0.50

        repo = await _run_pipeline(correlation_ctx=ctx, decision=decision)

        repo.flag_pending_review.assert_called_once()
        reasons = repo.flag_pending_review.call_args[0][1]
        assert "low_confidence" in reasons

    @pytest.mark.asyncio
    async def test_unknown_fault_type_flags_pending_review(self):
        """Fault type UNKNOWN → PENDING_REVIEW even with high confidence."""
        ticket = _make_ticket(fault_type=FaultType.UNKNOWN)
        ctx = _make_correlation_ctx(sop_matches=2, similar_tickets=3)
        decision = _make_decision(confidence=0.85)

        repo = await _run_pipeline(ticket=ticket, correlation_ctx=ctx, decision=decision)

        repo.flag_pending_review.assert_called_once()
        reasons = repo.flag_pending_review.call_args[0][1]
        assert "unknown_fault_type" in reasons

    @pytest.mark.asyncio
    async def test_multiple_reasons_all_included(self):
        """All four criteria failing → all four reasons in flag call."""
        ticket = _make_ticket(fault_type=FaultType.UNKNOWN)
        ctx = _make_correlation_ctx(sop_matches=0, similar_tickets=0)
        decision = _make_decision(confidence=0.20)

        repo = await _run_pipeline(ticket=ticket, correlation_ctx=ctx, decision=decision)

        reasons = repo.flag_pending_review.call_args[0][1]
        assert set(reasons) == {
            "no_sop_match",
            "no_historical_precedent",
            "low_confidence",
            "unknown_fault_type",
        }

    @pytest.mark.asyncio
    async def test_short_circuit_hold_bypasses_hitl_gate(self):
        """Short-circuit HOLD path marks RESOLVED without going through HITL gate."""
        ctx = _make_correlation_ctx(
            sop_matches=0, similar_tickets=0, short_circuit=True
        )

        with patch(
            "app.tasks.background.DispatchDecision.hold_from_context",
            return_value=_make_decision(confidence=1.0),
        ):
            repo = await _run_pipeline(correlation_ctx=ctx)

        # For the short-circuit path, RESOLVED is set directly (no HITL check)
        repo.flag_pending_review.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_decision_always_saved_before_hitl_check(self):
        """save_dispatch_decision must be called regardless of HITL outcome."""
        ctx = _make_correlation_ctx(sop_matches=0, similar_tickets=0)
        decision = _make_decision(confidence=0.10)

        repo = await _run_pipeline(correlation_ctx=ctx, decision=decision)

        repo.save_dispatch_decision.assert_called_once_with("TKT-HITL-001", decision)

    @pytest.mark.asyncio
    async def test_pipeline_failure_sets_failed_status(self):
        """Any exception in the pipeline → FAILED status, no flag."""
        repo = MagicMock()
        repo.update_status = AsyncMock()
        repo.save_dispatch_decision = AsyncMock()
        repo.flag_pending_review = AsyncMock()

        matching_engine = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock(side_effect=RuntimeError("Chroma down"))

        correlation_engine = MagicMock()
        agent = MagicMock()

        await run_telco_resolution_pipeline(
            ticket_id="TKT-HITL-001",
            ticket=_make_ticket(),
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=repo,
        )

        repo.update_status.assert_called_with("TKT-HITL-001", TelcoTicketStatus.FAILED)
        repo.flag_pending_review.assert_not_called()
