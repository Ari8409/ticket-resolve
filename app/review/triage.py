"""
HumanTriageHandler — business logic for the PENDING_REVIEW human-in-the-loop queue.

Triggered when the automated pipeline cannot produce a confident resolution:
  • No SOP matched in the vector store
  • No sufficiently similar historical ticket found
  • Agent confidence < AUTO_RESOLVE_THRESHOLD
  • Fault type classified as UNKNOWN

The handler exposes three operations:
  list_pending   — returns all PENDING_REVIEW tickets with triage context
  assign         — route a ticket to a specific NOC engineer or group
  manual_resolve — engineer submits the steps they performed; ticket → RESOLVED
                   and the resolution is indexed into Chroma as training signal
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.core.exceptions import TicketNotFoundError
from app.models.human_triage import (
    AssignRequest,
    AssignResult,
    ManualResolveRequest,
    ManualResolveResult,
    TriageSummary,
    UnresolvableReason,
)
from app.models.telco_ticket import TelcoTicketCreate, TelcoTicketStatus, TelcoTicketUpdate
from app.review.feedback import ResolutionFeedbackIndexer
from app.storage.telco_repositories import TelcoTicketRepository

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pipeline flags a ticket as PENDING_REVIEW when ALL of the following hold:
#   confidence_score  < this threshold
#   sop_candidates    < MIN_SOP_CANDIDATES
#   similar_tickets   < MIN_SIMILAR_TICKETS
AUTO_RESOLVE_THRESHOLD = 0.50
MIN_SOP_CANDIDATES     = 1
MIN_SIMILAR_TICKETS    = 1


def is_unresolvable(
    confidence_score: float,
    sop_candidates_found: int,
    similar_tickets_found: int,
    fault_type: str,
) -> tuple[bool, list[UnresolvableReason]]:
    """
    Evaluate whether the pipeline result warrants human-in-the-loop review.

    Returns (should_flag, reasons).  If should_flag is True, the caller
    must set the ticket status to PENDING_REVIEW and persist the reasons.

    A ticket is flagged when ANY of the individual criteria are met:
      - No SOP was retrieved            → NO_SOP_MATCH
      - No similar past tickets found   → NO_HISTORICAL_PRECEDENT
      - Low agent confidence            → LOW_CONFIDENCE
      - Fault type is UNKNOWN           → UNKNOWN_FAULT_TYPE

    Requiring only one criterion (rather than all three) ensures we never
    silently auto-resolve tickets in genuinely novel situations.
    """
    reasons: list[UnresolvableReason] = []

    if sop_candidates_found < MIN_SOP_CANDIDATES:
        reasons.append(UnresolvableReason.NO_SOP_MATCH)

    if similar_tickets_found < MIN_SIMILAR_TICKETS:
        reasons.append(UnresolvableReason.NO_HISTORICAL_PRECEDENT)

    if confidence_score < AUTO_RESOLVE_THRESHOLD:
        reasons.append(UnresolvableReason.LOW_CONFIDENCE)

    if fault_type in ("unknown", ""):
        reasons.append(UnresolvableReason.UNKNOWN_FAULT_TYPE)

    return bool(reasons), reasons


class HumanTriageHandler:
    """
    Orchestrates the PENDING_REVIEW human-in-the-loop workflow.

    Dependencies are injected for testability.
    """

    def __init__(
        self,
        repo: TelcoTicketRepository,
        feedback_indexer: ResolutionFeedbackIndexer,
    ) -> None:
        self._repo     = repo
        self._feedback = feedback_indexer

    # ------------------------------------------------------------------
    # LIST
    # ------------------------------------------------------------------

    async def list_pending(self, limit: int = 100) -> list[TriageSummary]:
        """
        Return all PENDING_REVIEW tickets ordered by oldest-first
        (highest urgency — been waiting longest).
        """
        rows = await self._repo.list_pending_review(limit=limit)
        summaries = []
        for r in rows:
            reasons_raw = r.get("pending_review_reasons") or []
            # Tolerate legacy DB values that don't match the current enum
            # (e.g. "no_similar_ticket" stored by the bulk-import script vs
            # the canonical "no_historical_precedent" enum value).
            reasons = []
            for x in reasons_raw:
                if not x:
                    continue
                try:
                    reasons.append(UnresolvableReason(x))
                except ValueError:
                    reasons.append(x)  # pass raw string through
            summaries.append(
                TriageSummary(
                    ticket_id=r["ticket_id"],
                    affected_node=r["affected_node"],
                    fault_type=str(r["fault_type"].value if hasattr(r["fault_type"], "value") else r["fault_type"]),
                    severity=str(r["severity"].value if hasattr(r["severity"], "value") else r["severity"]),
                    network_type=r.get("network_type"),
                    alarm_name=r.get("alarm_name"),
                    alarm_category=r.get("alarm_category"),
                    location_details=r.get("location_details"),
                    description=r["description"],
                    reasons=reasons,
                    confidence_score=0.0,   # stored in dispatch_decision; not denormalised here
                    sop_candidates_found=0,
                    similar_tickets_found=0,
                    flagged_at=r.get("updated_at") or r["created_at"],
                    assigned_to=r.get("assigned_to"),
                    assigned_at=r.get("assigned_at"),
                )
            )
        return summaries

    # ------------------------------------------------------------------
    # ASSIGN
    # ------------------------------------------------------------------

    async def assign(self, ticket_id: str, request: AssignRequest) -> AssignResult:
        """
        Route a PENDING_REVIEW ticket to a specific NOC engineer or group.

        The ticket status stays PENDING_REVIEW; only the assigned_to and
        assigned_at fields are updated.  The assignee then performs the
        investigation and calls manual_resolve() to close the loop.
        """
        ticket_dict = await self._repo.get(ticket_id)
        if not ticket_dict:
            raise TicketNotFoundError(ticket_id)

        if ticket_dict["status"] != TelcoTicketStatus.PENDING_REVIEW:
            raise ValueError(
                f"Ticket {ticket_id} is not in PENDING_REVIEW status "
                f"(current: {ticket_dict['status'].value}). "
                "Only PENDING_REVIEW tickets can be assigned."
            )

        updated = await self._repo.assign_ticket(ticket_id, request.assign_to)
        assigned_at = updated["assigned_at"] or datetime.utcnow()

        if request.notes:
            remark = (
                f"[{_now()}] Assigned to {request.assign_to}. "
                f"Note: {request.notes}"
            )
            patch = TelcoTicketUpdate(
                remarks=_append_remark(ticket_dict.get("remarks"), remark)
            )
            await self._repo.update(ticket_id, patch)

        log.info("Ticket %s assigned to %s", ticket_id, request.assign_to)
        return AssignResult(
            ticket_id=ticket_id,
            assigned_to=request.assign_to,
            assigned_at=assigned_at,
            message=(
                f"Ticket {ticket_id} assigned to {request.assign_to}. "
                "Status remains PENDING_REVIEW until manually resolved."
            ),
        )

    # ------------------------------------------------------------------
    # MANUAL RESOLVE
    # ------------------------------------------------------------------

    async def manual_resolve(
        self, ticket_id: str, request: ManualResolveRequest
    ) -> ManualResolveResult:
        """
        NOC engineer submits the steps they performed to resolve the ticket.

        1. Update ticket: steps, resolution fields, status → RESOLVED.
        2. Index the resolution into Chroma as a training signal so future
           similar tickets can be matched to this resolution pattern.
        3. Return ManualResolveResult.
        """
        ticket_dict = await self._repo.get(ticket_id)
        if not ticket_dict:
            raise TicketNotFoundError(ticket_id)

        status = ticket_dict["status"]
        if status not in (TelcoTicketStatus.PENDING_REVIEW, TelcoTicketStatus.IN_PROGRESS):
            raise ValueError(
                f"Ticket {ticket_id} cannot be manually resolved from status "
                f"'{status.value}'. Only PENDING_REVIEW or IN_PROGRESS tickets "
                "can be manually resolved."
            )

        now_str = _now()
        remark = (
            f"[{now_str}] Manually resolved by {request.resolved_by}. "
            + (f"SOP reference: {request.sop_reference}. " if request.sop_reference else "")
            + (f"Root cause: {request.primary_cause}. " if request.primary_cause else "")
            + (f"Notes: {request.notes}" if request.notes else "")
        ).strip()

        patch = TelcoTicketUpdate(
            status=TelcoTicketStatus.RESOLVED,
            resolution_steps=request.resolution_steps,
            sop_id=request.sop_reference,
            resolved_person=request.resolved_by,
            primary_cause=request.primary_cause,
            resolution_code=request.resolution_code,
            remarks=_append_remark(ticket_dict.get("remarks"), remark),
        )
        await self._repo.update(ticket_id, patch)

        # Index back to Chroma as a training signal
        ticket = _dict_to_create(ticket_dict)
        if request.primary_cause:
            object.__setattr__(ticket, "primary_cause", request.primary_cause)
        if request.resolution_code:
            object.__setattr__(ticket, "resolution_code", request.resolution_code)

        indexed = False
        try:
            await self._feedback.index_resolved(
                ticket_id=ticket_id,
                ticket=ticket,
                executed_steps=request.resolution_steps,
                sop_applied=request.sop_reference,
                reviewed_by=request.resolved_by,
            )
            indexed = True
            log.info(
                "Manually resolved ticket %s indexed as training signal (sop=%s)",
                ticket_id, request.sop_reference,
            )
        except Exception as exc:
            log.error(
                "Failed to index manually resolved ticket %s: %s",
                ticket_id, exc, exc_info=True,
            )

        return ManualResolveResult(
            ticket_id=ticket_id,
            new_status=TelcoTicketStatus.RESOLVED.value,
            message=(
                f"Ticket {ticket_id} manually resolved by {request.resolved_by}. "
                f"{len(request.resolution_steps)} step(s) recorded."
                + (" Resolution indexed as training signal." if indexed else "")
            ),
            executed_steps=request.resolution_steps,
            sop_reference=request.sop_reference,
            resolved_by=request.resolved_by,
            resolved_at=datetime.utcnow(),
            indexed_as_training_signal=indexed,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_remark(existing: str | None, new_line: str) -> str:
    return f"{existing}\n{new_line}" if existing else new_line


def _dict_to_create(d: dict) -> TelcoTicketCreate:
    from app.models.telco_ticket import FaultType, Severity
    return TelcoTicketCreate(
        ticket_id=d["ticket_id"],
        affected_node=d["affected_node"],
        severity=d["severity"] if isinstance(d["severity"], Severity) else Severity(d["severity"]),
        fault_type=d["fault_type"] if isinstance(d["fault_type"], FaultType) else FaultType(d["fault_type"]),
        description=d["description"],
        timestamp=d.get("timestamp"),
        title=d.get("title"),
        alarm_name=d.get("alarm_name"),
        alarm_category=d.get("alarm_category"),
        network_type=d.get("network_type"),
        object_class=d.get("object_class"),
        location_details=d.get("location_details"),
        primary_cause=d.get("primary_cause"),
        remarks=d.get("remarks"),
        resolution=d.get("resolution"),
        resolution_code=d.get("resolution_code"),
        sop_id=d.get("sop_id"),
    )
