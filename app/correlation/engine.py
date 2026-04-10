"""
CorrelationEngine — orchestrates all pre-dispatch checks in parallel
and assembles a CorrelationContext before the LLM agent runs.

Flow
----
                    ticket received
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   AlarmChecker   MaintenanceChecker  MatchingEngine
   (node active?) (in maint window?) (similar tickets)
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                   SOPRetriever (top-k SOPs)
                          │
                          ▼
               RemoteFeasibility assessment
                          │
                          ▼
                  CorrelationContext
                          │
              should_short_circuit?
              ┌─── YES ───┴─── NO ───┐
              ▼                      ▼
       DispatchDecision.HOLD    ResolutionAgent
       (no LLM call needed)         │
                                     ▼
                            DispatchDecision
                         (REMOTE / ON_SITE / ESCALATE)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.alarms.checker import AlarmChecker
from app.correlation.models import (
    CorrelationContext,
    DispatchDecision,
    assess_remote_feasibility,
)
from app.maintenance.checker import MaintenanceChecker
from app.matching.engine import MatchingEngine
from app.models.telco_ticket import TelcoTicketCreate
from app.sop.retriever import SOPRetriever

log = logging.getLogger(__name__)


class CorrelationEngine:
    """
    Assembles a CorrelationContext for a telco ticket by running all
    pre-dispatch checks concurrently.

    Usage::

        ctx = await engine.correlate(ticket)
        if ctx.should_short_circuit:
            return DispatchDecision.hold_from_context(ticket.ticket_id, ctx)
        # else: pass ctx to ResolutionAgent
    """

    def __init__(
        self,
        alarm_checker: AlarmChecker,
        maintenance_checker: MaintenanceChecker,
        matching_engine: MatchingEngine,
        sop_retriever: SOPRetriever,
        similar_top_k: int = 5,
        sop_top_k: int = 3,
    ) -> None:
        self._alarm       = alarm_checker
        self._maintenance = maintenance_checker
        self._matching    = matching_engine
        self._sop         = sop_retriever
        self._similar_k   = similar_top_k
        self._sop_k       = sop_top_k

    async def correlate(self, ticket: TelcoTicketCreate) -> CorrelationContext:
        """
        Run all checks in parallel and return a fully-assembled context.

        The alarm and maintenance checks are the fast path (SQL lookups).
        Vector searches run concurrently.  Total latency ≈ max(slowest check).
        """
        query = f"{ticket.fault_type} {ticket.affected_node} {ticket.description}"

        # Run everything concurrently
        (
            alarm_result,
            maint_result,
            similar_tickets,
            sop_matches,
        ) = await asyncio.gather(
            self._alarm.check(ticket.affected_node, alarm_type=ticket.fault_type.value),
            self._maintenance.check(ticket.affected_node, at=ticket.timestamp.replace(tzinfo=None)),
            self._matching.find_similar(query, top_k=self._similar_k),
            self._sop.retrieve(query, top_k=self._sop_k),
            return_exceptions=True,
        )

        # Gracefully handle any individual check failure
        if isinstance(alarm_result, Exception):
            log.error("AlarmChecker failed: %s", alarm_result, exc_info=True)
            from app.alarms.models import AlarmCheckResult
            alarm_result = AlarmCheckResult.not_found(ticket.affected_node)

        if isinstance(maint_result, Exception):
            log.error("MaintenanceChecker failed: %s", maint_result, exc_info=True)
            from app.maintenance.models import MaintenanceCheckResult
            maint_result = MaintenanceCheckResult.none_found(ticket.affected_node)

        if isinstance(similar_tickets, Exception):
            log.error("MatchingEngine failed: %s", similar_tickets, exc_info=True)
            similar_tickets = []

        if isinstance(sop_matches, Exception):
            log.error("SOPRetriever failed: %s", sop_matches, exc_info=True)
            sop_matches = []

        # Assess remote feasibility from the evidence gathered
        remote_feasibility = assess_remote_feasibility(
            fault_type=ticket.fault_type.value,
            similar_tickets=similar_tickets,
            sop_matches=sop_matches,
        )

        ctx = CorrelationContext(
            ticket_id=ticket.ticket_id,
            affected_node=ticket.affected_node,
            fault_type=ticket.fault_type.value,
            alarm_check=alarm_result,
            maintenance_check=maint_result,
            similar_tickets=similar_tickets,
            sop_matches=sop_matches,
            remote_feasibility=remote_feasibility,
        )

        log.info(
            "Correlation complete — node=%s fault=%s alarm=%s maint=%s remote_feasible=%s short_circuit=%s",
            ctx.affected_node,
            ctx.fault_type,
            alarm_result.status.value if alarm_result.alarm_found else "not_found",
            "yes" if maint_result.in_maintenance else "no",
            remote_feasibility.feasible,
            ctx.should_short_circuit,
        )
        return ctx
