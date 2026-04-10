"""
Background resolution pipeline — now with pre-dispatch correlation.

Execution order
---------------
1. Mark ticket PROCESSING
2. Index ticket into Chroma (so it's searchable immediately)
3. Run CorrelationEngine (alarm check + maintenance check + similarity + SOPs) — all parallel
4. Short-circuit to HOLD if alarm is cleared OR node is in maintenance
5. Otherwise: invoke ResolutionAgent (LLM) with full CorrelationContext
6. Persist DispatchDecision and mark ticket RESOLVED / FAILED
"""
from __future__ import annotations

import logging

from app.correlation.engine import CorrelationEngine
from app.correlation.models import DispatchDecision
from app.matching.engine import MatchingEngine
from app.models.telco_ticket import TelcoTicketCreate, TelcoTicketStatus
from app.recommendation.agent import ResolutionAgent
from app.storage.telco_repositories import TelcoTicketRepository

log = logging.getLogger(__name__)


async def run_telco_resolution_pipeline(
    ticket_id: str,
    ticket: TelcoTicketCreate,
    matching_engine: MatchingEngine,
    correlation_engine: CorrelationEngine,
    agent: ResolutionAgent,
    repo: TelcoTicketRepository,
) -> None:
    """
    Full pre-dispatch correlation + LLM resolution pipeline.

    Short-circuit path (no LLM call):
      alarm cleared     → DispatchDecision.HOLD
      in maintenance    → DispatchDecision.HOLD

    Normal path (LLM call):
      → DispatchDecision.REMOTE | ON_SITE | ESCALATE
    """
    try:
        await repo.update_status(ticket_id, TelcoTicketStatus.IN_PROGRESS)

        # Step 1 — index ticket into vector store so similarity search works for it too
        from app.models.ticket import TicketIn, TicketPriority
        generic = TicketIn(
            source="telco",
            title=ticket.affected_node + " — " + ticket.fault_type.value,
            description=ticket.description,
            priority=TicketPriority(ticket.severity.value),
            category=ticket.fault_type.value,
        )
        await matching_engine.index_ticket(ticket_id, generic)

        # Step 2 — run all pre-dispatch checks concurrently
        ctx = await correlation_engine.correlate(ticket)

        # Step 3 — short-circuit if alarm cleared or in maintenance
        if ctx.should_short_circuit:
            log.info(
                "Short-circuit HOLD for ticket %s — reason: %s",
                ticket_id, ctx.short_circuit_reason,
            )
            decision = DispatchDecision.hold_from_context(ticket_id, ctx)
            await repo.save_dispatch_decision(ticket_id, decision)
            await repo.update_status(ticket_id, TelcoTicketStatus.RESOLVED)
            return

        # Step 4 — run the LLM agent with full correlation context
        decision = await agent.resolve(ticket, ticket_id=ticket_id, correlation_ctx=ctx)
        await repo.save_dispatch_decision(ticket_id, decision)
        await repo.update_status(ticket_id, TelcoTicketStatus.RESOLVED)

        log.info(
            "Pipeline complete — ticket=%s dispatch=%s confidence=%.2f escalation=%s short_circuit=%s",
            ticket_id,
            decision.dispatch_mode.value,
            decision.confidence_score,
            decision.escalation_required,
            decision.short_circuited,
        )

    except Exception as exc:
        log.error("Telco pipeline failed for ticket %s: %s", ticket_id, exc, exc_info=True)
        await repo.update_status(ticket_id, TelcoTicketStatus.FAILED)


# Preserve the original generic pipeline for non-telco tickets
async def run_resolution_pipeline(
    ticket_id: str,
    ticket,
    matching_engine: MatchingEngine,
    sop_retriever,
    agent,
    repo,
) -> None:
    from app.models.ticket import TicketStatus
    try:
        await repo.update_status(ticket_id, TicketStatus.PROCESSING)
        await matching_engine.index_ticket(ticket_id, ticket)
        result = await agent.resolve(ticket, ticket_id=ticket_id)
        await repo.save_recommendation(ticket_id, result)
        await repo.update_status(ticket_id, TicketStatus.RESOLVED)
        log.info(
            "Generic pipeline complete for ticket %s — confidence %.2f",
            ticket_id, result.confidence_score,
        )
    except Exception as exc:
        log.error("Generic pipeline failed for ticket %s: %s", ticket_id, exc, exc_info=True)
        from app.models.ticket import TicketStatus
        await repo.update_status(ticket_id, TicketStatus.FAILED)
