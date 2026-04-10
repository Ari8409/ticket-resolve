"""
Human review endpoint for telco ticket recommendations.

POST /telco-tickets/{ticket_id}/review
---------------------------------------
Presents the agent's recommendation to a human reviewer.  The reviewer
chooses one of three actions:

  approve   — recommended steps accepted and recorded as executed;
               ticket marked RESOLVED; resolution indexed into Chroma.

  override  — reviewer selects a different SOP; replacement steps loaded;
               ticket marked IN_PROGRESS pending re-approval.

  escalate  — ticket flagged for senior engineer; no steps executed.

GET /telco-tickets/{ticket_id}/review
--------------------------------------
Returns the current recommendation and ticket state for the reviewer
to read before submitting their decision.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.exceptions import TicketNotFoundError
from app.dependencies import get_review_handler, get_telco_repo
from app.models.review import ReviewRequest, ReviewResult
from app.models.telco_ticket import TelcoTicketStatus
from app.review.handler import ReviewHandler
from app.storage.telco_repositories import TelcoTicketRepository

router = APIRouter(prefix="/telco-tickets", tags=["human-review"])


# ---------------------------------------------------------------------------
# GET — surface recommendation for reviewer
# ---------------------------------------------------------------------------

@router.get(
    "/{ticket_id}/review",
    summary="Get ticket recommendation for human review",
    responses={
        200: {"description": "Ticket + recommendation ready for review"},
        202: {"description": "Recommendation pipeline still processing"},
        404: {"description": "Ticket not found"},
    },
)
async def get_review_context(
    ticket_id: str,
    repo: Annotated[TelcoTicketRepository, Depends(get_telco_repo)],
):
    """
    Return the ticket details and the agent's DispatchDecision so the
    reviewer can inspect before submitting their decision.

    Returns 202 if the recommendation pipeline is still running.
    """
    ticket = await repo.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} not found")

    decision = await repo.get_dispatch_decision(ticket_id)
    if decision is None:
        return {
            "ticket_id":   ticket_id,
            "status":      ticket.get("status"),
            "message":     "Recommendation pipeline is still processing. Try again shortly.",
            "ready":       False,
        }

    return {
        "ticket_id":               ticket_id,
        "ready":                   True,
        "ticket": {
            "affected_node":       ticket.get("affected_node"),
            "fault_type":          str(ticket.get("fault_type", "")),
            "severity":            str(ticket.get("severity", "")),
            "network_type":        ticket.get("network_type"),
            "alarm_name":          ticket.get("alarm_name"),
            "alarm_category":      ticket.get("alarm_category"),
            "description":         ticket.get("description", "")[:500],
            "location_details":    ticket.get("location_details"),
            "status":              ticket.get("status"),
        },
        "recommendation": {
            "dispatch_mode":            decision.get("dispatch_mode"),
            "confidence_score":         decision.get("confidence_score"),
            "natural_language_summary": decision.get("natural_language_summary", ""),
            "ranked_sops":              decision.get("ranked_sops", []),
            "recommended_steps":        decision.get("recommended_steps", []),
            "reasoning":                decision.get("reasoning", ""),
            "escalation_required":      decision.get("escalation_required", False),
            "relevant_sops":            decision.get("relevant_sops", []),
            "similar_ticket_ids":       decision.get("similar_ticket_ids", []),
            # Correlation context
            "alarm_status":             decision.get("alarm_status"),
            "maintenance_active":       decision.get("maintenance_active"),
            "remote_feasible":          decision.get("remote_feasible"),
            "remote_confidence":        decision.get("remote_confidence"),
            "short_circuited":          decision.get("short_circuited", False),
            "short_circuit_reason":     decision.get("short_circuit_reason", ""),
        },
        "available_actions": _available_actions(ticket.get("status")),
    }


# ---------------------------------------------------------------------------
# POST — submit review decision
# ---------------------------------------------------------------------------

@router.post(
    "/{ticket_id}/review",
    response_model=ReviewResult,
    status_code=status.HTTP_200_OK,
    summary="Submit human review decision",
    responses={
        200: {"description": "Review decision applied"},
        400: {"description": "Invalid request (e.g. override_sop_id missing)"},
        404: {"description": "Ticket not found"},
        409: {"description": "Ticket is not in a reviewable state"},
    },
)
async def submit_review(
    ticket_id: str,
    request: ReviewRequest,
    handler: Annotated[ReviewHandler, Depends(get_review_handler)],
    repo: Annotated[TelcoTicketRepository, Depends(get_telco_repo)],
):
    """
    Submit a human review decision for a ticket recommendation.

    **approve** — The reviewer accepts the recommended steps. The ticket is
    marked RESOLVED and the resolution is written back to the Chroma vector
    store as a training signal for the similarity matcher.

    **override** — The reviewer selects a different SOP (via `override_sop_id`).
    The system fetches that SOP's steps, updates the recommendation, and marks
    the ticket IN_PROGRESS pending re-approval.

    **escalate** — The reviewer flags the ticket for a senior engineer. The
    ticket is marked ESCALATED and the escalation note is appended to remarks.
    """
    # Guard: ticket must exist and be in a reviewable state
    ticket = await repo.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} not found")

    current_status = str(ticket.get("status", ""))
    non_reviewable = {
        TelcoTicketStatus.RESOLVED.value,
        TelcoTicketStatus.CLOSED.value,
        TelcoTicketStatus.ESCALATED.value,
    }
    if current_status in non_reviewable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ticket {ticket_id} is in status '{current_status}' "
                "and cannot be reviewed again. "
                "Only OPEN / ASSIGNED / PENDING / IN_PROGRESS / CLEARED tickets are reviewable."
            ),
        )

    try:
        result = await handler.handle(ticket_id, request)
    except TicketNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _available_actions(current_status: str | None) -> list[str]:
    """Return the review actions available given the current ticket status."""
    non_reviewable = {
        TelcoTicketStatus.RESOLVED.value,
        TelcoTicketStatus.CLOSED.value,
        TelcoTicketStatus.ESCALATED.value,
    }
    if current_status in non_reviewable:
        return []
    return ["approve", "override", "escalate"]
