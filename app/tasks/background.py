"""
Background resolution pipeline — pre-dispatch correlation + classifier-aware agent.

Execution order
---------------
1. Mark ticket IN_PROGRESS
2. Index ticket into Chroma using the telco-aware document builder
   (preserves alarm_name, network_type, resolution fields)
3. Run FaultClassifier + CorrelationEngine concurrently
   - Classifier: Anthropic Claude tool-call → fault_type + confidence + affected_layer
   - Correlation: alarm check + maintenance check + similar tickets + SOP candidates
4. Short-circuit to HOLD if alarm cleared OR node is in maintenance (skip LLM)
5. Otherwise: run ResolutionAgent with both classifier result and correlation context
   → ranked SOPs + natural language summary + dispatch decision
6. Persist DispatchDecision; mark ticket RESOLVED or FAILED on error
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.classifier.classifier import FaultClassifier
from app.classifier.models import ClassificationResult
from app.correlation.engine import CorrelationEngine
from app.correlation.models import DispatchDecision
from app.matching.engine import MatchingEngine
from app.models.telco_ticket import TelcoTicketCreate, TelcoTicketStatus
from app.recommendation.agent import ResolutionAgent
from app.review.triage import is_unresolvable
from app.storage.telco_repositories import TelcoTicketRepository

log = logging.getLogger(__name__)


async def run_telco_resolution_pipeline(
    ticket_id: str,
    ticket: TelcoTicketCreate,
    matching_engine: MatchingEngine,
    correlation_engine: CorrelationEngine,
    agent: ResolutionAgent,
    repo: TelcoTicketRepository,
    fault_classifier: Optional[FaultClassifier] = None,
) -> None:
    """
    Full pre-dispatch correlation + LLM resolution pipeline for telco tickets.

    Short-circuit path (no LLM agent call):
      alarm CLEARED       → DispatchDecision.HOLD
      node IN MAINTENANCE → DispatchDecision.HOLD

    Normal path (LLM agent call):
      → DispatchDecision.REMOTE | ON_SITE | ESCALATE
      Classifier output (fault_type + confidence) is injected into the agent
      prompt so the ranked SOP selection is anchored to the classifier's verdict.
    """
    try:
        await repo.update_status(ticket_id, TelcoTicketStatus.IN_PROGRESS)

        # ----------------------------------------------------------------
        # Step 1 — index ticket into Chroma using the telco document builder.
        #
        # index_telco_ticket() preserves alarm_name, alarm_category,
        # network_type, primary_cause, and resolution fields in the
        # embedded document — the generic index_ticket() loses all of these.
        # ----------------------------------------------------------------
        await matching_engine.index_telco_ticket(ticket_id, ticket, resolved=False)

        # ----------------------------------------------------------------
        # Step 2 — run classifier + correlation concurrently.
        #
        # Both are independent at this point:
        #   - FaultClassifier hits Anthropic API + does its own Chroma queries
        #   - CorrelationEngine runs alarm check, maintenance check, similarity
        #     search, and SOP retrieval — all four in parallel internally
        # ----------------------------------------------------------------
        classifier_result: Optional[ClassificationResult] = None

        if fault_classifier is not None:
            classifier_task = asyncio.create_task(
                _run_classifier(fault_classifier, ticket)
            )
            ctx = await correlation_engine.correlate(ticket)
            classifier_result = await classifier_task
        else:
            log.warning(
                "FaultClassifier not provided for ticket %s — "
                "agent will infer fault type from description only.",
                ticket_id,
            )
            ctx = await correlation_engine.correlate(ticket)

        # ----------------------------------------------------------------
        # Step 3 — short-circuit: alarm cleared or node in maintenance.
        # No LLM call needed; confidence is 1.0 by definition.
        # ----------------------------------------------------------------
        if ctx.should_short_circuit:
            log.info(
                "Short-circuit HOLD for ticket %s — reason: %s",
                ticket_id, ctx.short_circuit_reason,
            )
            decision = DispatchDecision.hold_from_context(ticket_id, ctx)
            await repo.save_dispatch_decision(ticket_id, decision)
            await repo.update_status(ticket_id, TelcoTicketStatus.RESOLVED)
            return

        # ----------------------------------------------------------------
        # Step 4 — run the LLM agent with full context.
        #
        # Both classifier_result and correlation_ctx are passed so:
        #   • The prompt shows the classifier's fault_type + confidence
        #     alongside the pre-ranked candidate SOPs and similar tickets
        #   • The agent can anchor its ranked_sops output to the classifier
        #     verdict instead of re-deriving the fault type from scratch
        # ----------------------------------------------------------------
        decision = await agent.resolve(
            ticket,
            ticket_id=ticket_id,
            correlation_ctx=ctx,
            classifier_result=classifier_result,
        )
        await repo.save_dispatch_decision(ticket_id, decision)

        # ----------------------------------------------------------------
        # Step 5 — human-in-the-loop gate.
        #
        # Check whether the pipeline result is confident enough to
        # auto-resolve or whether it should be routed to the NOC queue.
        #
        # Flagging criteria (ANY one is sufficient):
        #   • sop_candidates  == 0          → NO_SOP_MATCH
        #   • similar_tickets == 0          → NO_HISTORICAL_PRECEDENT
        #   • confidence_score < 0.50       → LOW_CONFIDENCE
        #   • fault_type == "unknown"       → UNKNOWN_FAULT_TYPE
        # ----------------------------------------------------------------
        sop_candidates_found  = len(ctx.sop_matches)
        similar_tickets_found = len(ctx.similar_tickets)
        fault_type_str = (
            ticket.fault_type.value
            if hasattr(ticket.fault_type, "value")
            else str(ticket.fault_type)
        )

        should_flag, reasons = is_unresolvable(
            confidence_score=decision.confidence_score,
            sop_candidates_found=sop_candidates_found,
            similar_tickets_found=similar_tickets_found,
            fault_type=fault_type_str,
        )

        if should_flag:
            reason_values = [r.value for r in reasons]
            await repo.flag_pending_review(ticket_id, reason_values)
            log.warning(
                "Ticket %s flagged PENDING_REVIEW — reasons=%s "
                "confidence=%.2f sop_candidates=%d similar_tickets=%d fault_type=%s",
                ticket_id,
                reason_values,
                decision.confidence_score,
                sop_candidates_found,
                similar_tickets_found,
                fault_type_str,
            )
        else:
            await repo.update_status(ticket_id, TelcoTicketStatus.RESOLVED)

        log.info(
            "Pipeline complete — ticket=%s dispatch=%s confidence=%.2f "
            "escalation=%s ranked_sops=%d short_circuit=%s pending_review=%s",
            ticket_id,
            decision.dispatch_mode.value,
            decision.confidence_score,
            decision.escalation_required,
            len(decision.ranked_sops),
            decision.short_circuited,
            should_flag,
        )

    except Exception as exc:
        log.error("Telco pipeline failed for ticket %s: %s", ticket_id, exc, exc_info=True)
        await repo.update_status(ticket_id, TelcoTicketStatus.FAILED)


async def _run_classifier(
    classifier: FaultClassifier,
    ticket: TelcoTicketCreate,
) -> Optional[ClassificationResult]:
    """Run the fault classifier, returning None on failure (pipeline continues)."""
    try:
        return await classifier.classify(ticket.description)
    except Exception as exc:
        log.warning(
            "FaultClassifier failed for node %s — continuing without classifier output: %s",
            ticket.affected_node, exc,
        )
        return None


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
