"""
ReviewHandler — business logic for the three human-review actions.

  approve:   accept the agent's recommended steps, mark ticket RESOLVED,
             index the resolution back into Chroma as a training signal.

  override:  reject the recommended SOP, fetch steps from a reviewer-chosen
             SOP, store them, mark ticket IN_PROGRESS (awaiting re-approval).

  escalate:  flag for senior engineer, mark ticket ESCALATED, append note.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.core.exceptions import TicketNotFoundError
from app.models.review import ReviewAction, ReviewRequest, ReviewResult
from app.models.telco_ticket import TelcoTicketCreate, TelcoTicketStatus, TelcoTicketUpdate
from app.review.feedback import ResolutionFeedbackIndexer
from app.sop.retriever import SOPRetriever
from app.storage.telco_repositories import TelcoTicketRepository

log = logging.getLogger(__name__)


class ReviewHandler:
    """
    Orchestrates the approve / override / escalate review workflow.

    Dependencies are injected so the handler is fully testable without
    real DB sessions or Chroma connections.
    """

    def __init__(
        self,
        repo: TelcoTicketRepository,
        sop_retriever: SOPRetriever,
        feedback_indexer: ResolutionFeedbackIndexer,
    ) -> None:
        self._repo     = repo
        self._sop      = sop_retriever
        self._feedback = feedback_indexer

    async def handle(self, ticket_id: str, request: ReviewRequest) -> ReviewResult:
        """Route the request to the correct action handler."""
        if request.action == ReviewAction.APPROVE:
            return await self._approve(ticket_id, request)
        if request.action == ReviewAction.OVERRIDE:
            return await self._override(ticket_id, request)
        return await self._escalate(ticket_id, request)

    # ------------------------------------------------------------------
    # APPROVE
    # ------------------------------------------------------------------

    async def _approve(self, ticket_id: str, req: ReviewRequest) -> ReviewResult:
        """
        Accept the recommendation as-is.

        1. Load the current dispatch decision for this ticket.
        2. Record the recommended steps as executed.
        3. Mark ticket RESOLVED with reviewer identity.
        4. Index the resolution back into Chroma (training signal).
        """
        ticket_dict = await self._repo.get(ticket_id)
        if not ticket_dict:
            raise TicketNotFoundError(ticket_id)

        decision = await self._repo.get_dispatch_decision(ticket_id)
        if not decision:
            raise ValueError(f"No dispatch decision found for ticket {ticket_id}. "
                             "Run the resolution pipeline first.")

        executed_steps: list[str] = decision.get("recommended_steps", [])
        sop_applied: str | None   = (
            decision.get("relevant_sops", [None])[0]
            if decision.get("relevant_sops")
            else ticket_dict.get("sop_id")
        )

        # Update the ticket: status → RESOLVED, record reviewer
        patch = TelcoTicketUpdate(
            status=TelcoTicketStatus.RESOLVED,
            resolution_steps=executed_steps,
            resolved_person=req.reviewed_by,
            remarks=_append_remark(
                ticket_dict.get("remarks"),
                f"[{_now()}] APPROVED by {req.reviewed_by or 'reviewer'}. "
                f"SOP applied: {sop_applied or 'agent recommendation'}.",
            ),
        )
        await self._repo.update(ticket_id, patch)

        # Reconstruct TelcoTicketCreate from stored dict for the feedback indexer
        ticket = _dict_to_create(ticket_dict)
        # Enrich with resolution data from the decision
        object.__setattr__(ticket, "resolution_steps", executed_steps)

        # Write to Chroma vector store as a training signal
        indexed = False
        try:
            await self._feedback.index_resolved(
                ticket_id=ticket_id,
                ticket=ticket,
                executed_steps=executed_steps,
                sop_applied=sop_applied,
                reviewed_by=req.reviewed_by,
            )
            indexed = True
        except Exception as exc:
            log.error(
                "Failed to index resolved ticket %s into Chroma: %s",
                ticket_id, exc, exc_info=True,
            )

        log.info("Ticket %s APPROVED by %s (sop=%s)", ticket_id, req.reviewed_by, sop_applied)
        return ReviewResult(
            ticket_id=ticket_id,
            action_taken=ReviewAction.APPROVE,
            new_status=TelcoTicketStatus.RESOLVED.value,
            message=(
                f"Ticket {ticket_id} approved and marked RESOLVED. "
                f"{len(executed_steps)} step(s) recorded as executed."
                + (" Resolution indexed as training signal." if indexed else "")
            ),
            executed_steps=executed_steps,
            sop_applied=sop_applied,
            indexed_as_training_signal=indexed,
            reviewed_by=req.reviewed_by,
        )

    # ------------------------------------------------------------------
    # OVERRIDE
    # ------------------------------------------------------------------

    async def _override(self, ticket_id: str, req: ReviewRequest) -> ReviewResult:
        """
        Reject the recommended SOP and apply a reviewer-chosen one instead.

        1. Validate override_sop_id is provided.
        2. Fetch the SOP's resolution steps from the vector store.
        3. Update the dispatch decision with the new steps + SOP.
        4. Mark ticket IN_PROGRESS (steps must still be actioned; re-approval expected).
        """
        if not req.override_sop_id:
            raise ValueError("override_sop_id is required when action=override.")

        ticket_dict = await self._repo.get(ticket_id)
        if not ticket_dict:
            raise TicketNotFoundError(ticket_id)

        # Fetch steps from the chosen SOP
        override_steps = await self._sop.get_sop_steps_by_id(req.override_sop_id)
        if not override_steps:
            raise ValueError(
                f"SOP '{req.override_sop_id}' not found in the knowledge base. "
                "Check that the SOP has been indexed."
            )

        # Update ticket: steps replaced, SOP reference changed, status → IN_PROGRESS
        remark = (
            f"[{_now()}] SOP OVERRIDDEN by {req.reviewed_by or 'reviewer'}. "
            f"Replaced with {req.override_sop_id}."
        )
        if req.override_notes:
            remark += f" Note: {req.override_notes}"

        patch = TelcoTicketUpdate(
            status=TelcoTicketStatus.IN_PROGRESS,
            resolution_steps=override_steps,
            sop_id=req.override_sop_id,
            resolved_person=req.reviewed_by,
            remarks=_append_remark(ticket_dict.get("remarks"), remark),
        )
        await self._repo.update(ticket_id, patch)

        log.info(
            "Ticket %s OVERRIDDEN by %s — new SOP: %s (%d steps)",
            ticket_id, req.reviewed_by, req.override_sop_id, len(override_steps),
        )
        return ReviewResult(
            ticket_id=ticket_id,
            action_taken=ReviewAction.OVERRIDE,
            new_status=TelcoTicketStatus.IN_PROGRESS.value,
            message=(
                f"Ticket {ticket_id} SOP overridden with {req.override_sop_id}. "
                f"{len(override_steps)} replacement step(s) loaded. "
                "Ticket is now IN_PROGRESS — re-approve once steps are actioned."
            ),
            executed_steps=override_steps,
            sop_applied=req.override_sop_id,
            indexed_as_training_signal=False,
            reviewed_by=req.reviewed_by,
        )

    # ------------------------------------------------------------------
    # ESCALATE
    # ------------------------------------------------------------------

    async def _escalate(self, ticket_id: str, req: ReviewRequest) -> ReviewResult:
        """
        Flag the ticket for a senior engineer.

        1. Mark ticket ESCALATED.
        2. Append the escalation note to remarks.
        3. No steps are executed; no Chroma write (ticket is not resolved).
        """
        ticket_dict = await self._repo.get(ticket_id)
        if not ticket_dict:
            raise TicketNotFoundError(ticket_id)

        escalation_note = req.escalation_note or "Escalated by reviewer — no specific note provided."
        remark = (
            f"[{_now()}] ESCALATED by {req.reviewed_by or 'reviewer'}. "
            f"Escalated to: {req.escalate_to or 'senior engineer'}. "
            f"Reason: {escalation_note}"
        )

        patch = TelcoTicketUpdate(
            status=TelcoTicketStatus.ESCALATED,
            resolved_person=req.reviewed_by,
            remarks=_append_remark(ticket_dict.get("remarks"), remark),
        )
        await self._repo.update(ticket_id, patch)

        log.info(
            "Ticket %s ESCALATED by %s to %s",
            ticket_id, req.reviewed_by, req.escalate_to or "senior engineer",
        )
        return ReviewResult(
            ticket_id=ticket_id,
            action_taken=ReviewAction.ESCALATE,
            new_status=TelcoTicketStatus.ESCALATED.value,
            message=(
                f"Ticket {ticket_id} escalated to {req.escalate_to or 'senior engineer'}. "
                "No steps were executed. Ticket is flagged ESCALATED."
            ),
            escalated_to=req.escalate_to,
            indexed_as_training_signal=False,
            reviewed_by=req.reviewed_by,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_remark(existing: str | None, new_line: str) -> str:
    """Append a new remark line to existing remarks (newline-separated)."""
    if existing:
        return f"{existing}\n{new_line}"
    return new_line


def _dict_to_create(d: dict) -> TelcoTicketCreate:
    """
    Reconstruct a minimal TelcoTicketCreate from a repository dict.

    Only the fields required for the feedback indexer's document builder
    need to be populated; the rest default to None / empty.
    """
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
