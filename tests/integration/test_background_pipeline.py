"""
Integration tests for run_telco_resolution_pipeline().

Covers:
  • Normal path  — classifier + correlation → LLM agent → RESOLVED
  • Short-circuit — alarm CLEARED  → HOLD, no LLM call
  • Short-circuit — IN MAINTENANCE  → HOLD, no LLM call
  • Classifier failure — pipeline degrades gracefully (classifier=None path)
  • Pipeline failure  — agent raises → ticket marked FAILED
  • No classifier     — correlation-only, agent still called with None

All external I/O (DB, Chroma, Anthropic, OpenAI) is mocked.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from app.correlation.models import CorrelationContext, DispatchDecision, DispatchMode
from app.models.telco_ticket import FaultType, Severity, TelcoTicketCreate, TelcoTicketStatus
from app.tasks.background import run_telco_resolution_pipeline


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ticket():
    return TelcoTicketCreate(
        affected_node="LTE_ENB_780321",
        severity=Severity.MAJOR,
        fault_type=FaultType.HARDWARE_FAILURE,
        description=(
            "LTE_ENB_780321*equipmentAlarm/HW Fault*1*Hardware failure\n\n"
            "Hardware failure detected on LTE node. Possible RF module issue."
        ),
        network_type="4G",
        alarm_name="HW Fault",
        alarm_category="equipmentAlarm",
        primary_cause="Hardware Fault",
        resolution_code="Hardware Replacement",
    )


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.update_status    = AsyncMock()
    repo.save_dispatch_decision = AsyncMock()
    return repo


@pytest.fixture
def normal_correlation_ctx():
    """A context that does NOT trigger short-circuit (no alarm cleared, no maintenance)."""
    ctx = MagicMock(spec=CorrelationContext)
    ctx.should_short_circuit = False
    ctx.short_circuit_reason  = None
    ctx.alarm_status          = "active"
    ctx.maintenance_active    = False
    ctx.similar_tickets       = []
    ctx.sop_matches           = []
    return ctx


@pytest.fixture
def cleared_alarm_ctx():
    """A context that triggers short-circuit because the alarm was cleared."""
    ctx = MagicMock(spec=CorrelationContext)
    ctx.should_short_circuit  = True
    ctx.short_circuit_reason  = "Alarm cleared — no dispatch required."
    ctx.alarm_status          = "cleared"
    ctx.maintenance_active    = False
    ctx.similar_tickets       = []
    ctx.sop_matches           = []
    return ctx


@pytest.fixture
def maintenance_ctx():
    """A context that triggers short-circuit because node is in maintenance."""
    ctx = MagicMock(spec=CorrelationContext)
    ctx.should_short_circuit  = True
    ctx.short_circuit_reason  = "Node in planned maintenance window."
    ctx.alarm_status          = "active"
    ctx.maintenance_active    = True
    ctx.similar_tickets       = []
    ctx.sop_matches           = []
    return ctx


def _make_dispatch_decision(ticket_id: str) -> DispatchDecision:
    return DispatchDecision(
        ticket_id=ticket_id,
        dispatch_mode=DispatchMode.ON_SITE,
        confidence_score=0.91,
        recommended_steps=["Check HW logs", "Replace module"],
        reasoning="Known HW fault pattern.",
        escalation_required=False,
        relevant_sops=["SOP-HW-001"],
        similar_ticket_ids=[],
        natural_language_summary="Hardware fault — on-site required.",
        ranked_sops=[],
        short_circuited=False,
    )


def _make_hold_decision(ticket_id: str) -> DispatchDecision:
    return DispatchDecision(
        ticket_id=ticket_id,
        dispatch_mode=DispatchMode.HOLD,
        confidence_score=1.0,
        recommended_steps=[],
        reasoning="Alarm cleared.",
        escalation_required=False,
        relevant_sops=[],
        similar_ticket_ids=[],
        natural_language_summary="Alarm cleared — no dispatch required.",
        ranked_sops=[],
        short_circuited=True,
        short_circuit_reason="Alarm cleared.",
    )


# ---------------------------------------------------------------------------
# Normal path
# ---------------------------------------------------------------------------

class TestNormalPath:
    @pytest.mark.asyncio
    async def test_pipeline_marks_in_progress_then_resolved(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        ticket_id = "TKT-NORM001"
        decision  = _make_dispatch_decision(ticket_id)

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock(return_value=decision)

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
        )

        status_calls = [c.args[1] for c in mock_repo.update_status.call_args_list]
        assert TelcoTicketStatus.IN_PROGRESS in status_calls
        assert TelcoTicketStatus.RESOLVED    in status_calls

    @pytest.mark.asyncio
    async def test_pipeline_calls_agent_resolve(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        ticket_id = "TKT-NORM002"
        decision  = _make_dispatch_decision(ticket_id)

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock(return_value=decision)

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
        )

        agent.resolve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pipeline_saves_dispatch_decision(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        ticket_id = "TKT-NORM003"
        decision  = _make_dispatch_decision(ticket_id)

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock(return_value=decision)

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
        )

        mock_repo.save_dispatch_decision.assert_awaited_once_with(ticket_id, decision)

    @pytest.mark.asyncio
    async def test_pipeline_indexes_ticket_to_chroma(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        ticket_id = "TKT-NORM004"
        decision  = _make_dispatch_decision(ticket_id)

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock(return_value=decision)

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
        )

        matching_engine.index_telco_ticket.assert_awaited_once_with(
            ticket_id, ticket, resolved=False
        )

    @pytest.mark.asyncio
    async def test_pipeline_passes_classifier_result_to_agent(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        """When a FaultClassifier is provided its result reaches agent.resolve()."""
        from app.classifier.models import ClassificationResult

        ticket_id    = "TKT-NORM005"
        decision     = _make_dispatch_decision(ticket_id)
        clf_result   = ClassificationResult(
            fault_type="hardware_failure",
            confidence_score=0.94,
            affected_layer="physical",
            reasoning="HW fault signature",
            model="claude-sonnet-4-6",
            latency_ms=120,
        )

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        fault_classifier   = MagicMock()
        fault_classifier.classify = AsyncMock(return_value=clf_result)

        agent              = MagicMock()
        agent.resolve      = AsyncMock(return_value=decision)

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
            fault_classifier=fault_classifier,
        )

        _, kwargs = agent.resolve.call_args
        assert kwargs.get("classifier_result") == clf_result

    @pytest.mark.asyncio
    async def test_pipeline_without_classifier_still_calls_agent(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        """fault_classifier=None → classifier_result is None, agent still runs."""
        ticket_id = "TKT-NORM006"
        decision  = _make_dispatch_decision(ticket_id)

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock(return_value=decision)

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
            fault_classifier=None,
        )

        agent.resolve.assert_awaited_once()
        _, kwargs = agent.resolve.call_args
        assert kwargs.get("classifier_result") is None


# ---------------------------------------------------------------------------
# Short-circuit paths
# ---------------------------------------------------------------------------

class TestShortCircuit:
    @pytest.mark.asyncio
    async def test_cleared_alarm_short_circuits_to_hold(
        self, ticket, mock_repo, cleared_alarm_ctx
    ):
        """Cleared alarm → DispatchDecision HOLD, no LLM agent call."""
        ticket_id = "TKT-SC001"

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=cleared_alarm_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock()

        with patch.object(
            DispatchDecision, "hold_from_context",
            return_value=_make_hold_decision(ticket_id),
        ) as mock_hold:
            await run_telco_resolution_pipeline(
                ticket_id=ticket_id,
                ticket=ticket,
                matching_engine=matching_engine,
                correlation_engine=correlation_engine,
                agent=agent,
                repo=mock_repo,
            )
            mock_hold.assert_called_once_with(ticket_id, cleared_alarm_ctx)

        # Agent must NOT have been called
        agent.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_maintenance_short_circuits_to_hold(
        self, ticket, mock_repo, maintenance_ctx
    ):
        """Node in maintenance → HOLD, no LLM agent call."""
        ticket_id = "TKT-SC002"

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=maintenance_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock()

        with patch.object(
            DispatchDecision, "hold_from_context",
            return_value=_make_hold_decision(ticket_id),
        ):
            await run_telco_resolution_pipeline(
                ticket_id=ticket_id,
                ticket=ticket,
                matching_engine=matching_engine,
                correlation_engine=correlation_engine,
                agent=agent,
                repo=mock_repo,
            )

        agent.resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_short_circuit_saves_hold_decision_and_resolves(
        self, ticket, mock_repo, cleared_alarm_ctx
    ):
        ticket_id    = "TKT-SC003"
        hold_decision = _make_hold_decision(ticket_id)

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=cleared_alarm_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock()

        with patch.object(
            DispatchDecision, "hold_from_context",
            return_value=hold_decision,
        ):
            await run_telco_resolution_pipeline(
                ticket_id=ticket_id,
                ticket=ticket,
                matching_engine=matching_engine,
                correlation_engine=correlation_engine,
                agent=agent,
                repo=mock_repo,
            )

        mock_repo.save_dispatch_decision.assert_awaited_once_with(ticket_id, hold_decision)
        status_calls = [c.args[1] for c in mock_repo.update_status.call_args_list]
        assert TelcoTicketStatus.RESOLVED in status_calls


# ---------------------------------------------------------------------------
# Failure / degraded paths
# ---------------------------------------------------------------------------

class TestFailurePaths:
    @pytest.mark.asyncio
    async def test_agent_error_marks_ticket_failed(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        ticket_id = "TKT-FAIL001"

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        failing_agent      = MagicMock()
        failing_agent.resolve = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=failing_agent,
            repo=mock_repo,
        )

        status_calls = [c.args[1] for c in mock_repo.update_status.call_args_list]
        assert TelcoTicketStatus.FAILED in status_calls

    @pytest.mark.asyncio
    async def test_agent_error_does_not_save_dispatch_decision(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        ticket_id = "TKT-FAIL002"

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        failing_agent      = MagicMock()
        failing_agent.resolve = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=failing_agent,
            repo=mock_repo,
        )

        mock_repo.save_dispatch_decision.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_classifier_failure_does_not_abort_pipeline(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        """Classifier exception → classifier_result=None, pipeline still resolves."""
        ticket_id = "TKT-FAIL003"
        decision  = _make_dispatch_decision(ticket_id)

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock()

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        fault_classifier   = MagicMock()
        fault_classifier.classify = AsyncMock(side_effect=ConnectionError("Anthropic API down"))

        agent              = MagicMock()
        agent.resolve      = AsyncMock(return_value=decision)

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
            fault_classifier=fault_classifier,
        )

        # Agent is still called despite classifier failure
        agent.resolve.assert_awaited_once()
        _, kwargs = agent.resolve.call_args
        assert kwargs.get("classifier_result") is None

        # Ticket ends up RESOLVED, not FAILED
        status_calls = [c.args[1] for c in mock_repo.update_status.call_args_list]
        assert TelcoTicketStatus.RESOLVED in status_calls
        assert TelcoTicketStatus.FAILED   not in status_calls

    @pytest.mark.asyncio
    async def test_chroma_indexing_error_marks_ticket_failed(
        self, ticket, mock_repo, normal_correlation_ctx
    ):
        """If Chroma indexing fails, the pipeline catches it and marks FAILED."""
        ticket_id = "TKT-FAIL004"

        matching_engine    = MagicMock()
        matching_engine.index_telco_ticket = AsyncMock(side_effect=IOError("Chroma unavailable"))

        correlation_engine = MagicMock()
        correlation_engine.correlate = AsyncMock(return_value=normal_correlation_ctx)

        agent              = MagicMock()
        agent.resolve      = AsyncMock()

        await run_telco_resolution_pipeline(
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            correlation_engine=correlation_engine,
            agent=agent,
            repo=mock_repo,
        )

        status_calls = [c.args[1] for c in mock_repo.update_status.call_args_list]
        assert TelcoTicketStatus.FAILED in status_calls
        # Agent must NOT have been called since indexing failed first
        agent.resolve.assert_not_awaited()
