"""
Human-in-the-loop triage endpoints.

These endpoints surface the PENDING_REVIEW queue to NOC engineers when the
automated pipeline cannot produce a confident resolution — i.e. no SOP was
matched, no sufficiently similar historical ticket was found, agent confidence
was below the auto-resolve threshold, or the fault type is UNKNOWN.

Endpoints
---------
GET  /telco-tickets/pending-review
    List all tickets currently in PENDING_REVIEW status, ordered oldest-first.
    Returns lightweight TriageSummary records for the NOC dashboard.

POST /telco-tickets/{ticket_id}/assign
    Route a PENDING_REVIEW ticket to a specific NOC engineer or group.
    The ticket stays PENDING_REVIEW; the assignee then calls /manual-resolve.

POST /telco-tickets/{ticket_id}/manual-resolve
    NOC engineer submits the resolution steps they performed.
    The ticket moves to RESOLVED and the resolution is indexed into Chroma
    as a training signal for future similar tickets.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.exceptions import TicketNotFoundError
from app.dependencies import get_audit_repo, get_triage_handler
from app.models.human_triage import (
    AssignRequest,
    AssignResult,
    ManualResolveRequest,
    ManualResolveResult,
    TriageSummary,
)
from app.review.triage import HumanTriageHandler
from app.storage.audit_store import AuditLogRepository

router = APIRouter(prefix="/telco-tickets", tags=["human-triage"])


# ---------------------------------------------------------------------------
# AUDIT LOG — immutable lifecycle trail per ticket
# ---------------------------------------------------------------------------

@router.get(
    "/{ticket_id}/audit-log",
    response_model=list[dict],
    summary="Return the immutable audit trail for a ticket",
    responses={
        200: {"description": "Chronological list of lifecycle events"},
    },
)
async def get_audit_log(
    ticket_id: str,
    audit_repo: Annotated[AuditLogRepository, Depends(get_audit_repo)],
):
    """
    Return all audit log entries for *ticket_id*, ordered chronologically.

    Each entry contains: id, ticket_id, event_type, from_status, to_status,
    changed_by, reason, created_at.

    Satisfies EU AI Act Art.12 traceability requirement — every automated or
    manual status transition is permanently recorded here.
    """
    rows = await audit_repo.get_trail(ticket_id)
    return [
        {
            "id":          r.id,
            "ticket_id":   r.ticket_id,
            "event_type":  r.event_type,
            "from_status": r.from_status,
            "to_status":   r.to_status,
            "changed_by":  r.changed_by,
            "reason":      r.reason,
            "created_at":  r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# LIST — pending-review queue
# ---------------------------------------------------------------------------

@router.get(
    "/pending-review",
    response_model=list[TriageSummary],
    summary="List tickets pending human triage",
    responses={
        200: {"description": "Ordered list of PENDING_REVIEW tickets (oldest first)"},
    },
)
async def list_pending_review(
    handler: Annotated[HumanTriageHandler, Depends(get_triage_handler)],
    limit: int = Query(default=100, ge=1, le=500, description="Maximum tickets to return"),
):
    """
    Return all tickets in PENDING_REVIEW status, ordered by oldest-first
    (highest urgency — those that have been waiting the longest appear first).

    The pipeline flags a ticket as PENDING_REVIEW when ANY of the following
    conditions are met:
    - No SOP was matched (NO_SOP_MATCH)
    - No similar historical ticket was found (NO_HISTORICAL_PRECEDENT)
    - Agent confidence score < 0.50 (LOW_CONFIDENCE)
    - Fault type could not be classified (UNKNOWN_FAULT_TYPE)

    Each summary includes the `reasons` list so engineers can prioritise
    tickets that require the most investigation.
    """
    return await handler.list_pending(limit=limit)


# ---------------------------------------------------------------------------
# ASSIGN — route ticket to engineer or group
# ---------------------------------------------------------------------------

@router.post(
    "/{ticket_id}/assign",
    response_model=AssignResult,
    status_code=status.HTTP_200_OK,
    summary="Assign a PENDING_REVIEW ticket to an engineer or group",
    responses={
        200: {"description": "Ticket successfully assigned"},
        404: {"description": "Ticket not found"},
        409: {"description": "Ticket is not in PENDING_REVIEW status"},
    },
)
async def assign_ticket(
    ticket_id: str,
    request: AssignRequest,
    handler: Annotated[HumanTriageHandler, Depends(get_triage_handler)],
):
    """
    Route a PENDING_REVIEW ticket to a specific NOC engineer or group.

    The ticket **remains in PENDING_REVIEW status** — it is not resolved by
    this call. The assigned engineer is expected to investigate the fault and
    call the `/manual-resolve` endpoint once they have performed the fix.

    Typical values for `assign_to`:
    - Engineer login: `"ahmad.zulkifli"`, `"siti.rahimah"`
    - NOC group name: `"ATO-BSM-East"`, `"RF-Operations-KL"`

    Optional `notes` are appended to the ticket's remarks log and are visible
    to the assignee when they open the ticket.
    """
    try:
        return await handler.assign(ticket_id, request)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# MANUAL RESOLVE — engineer submits resolution steps
# ---------------------------------------------------------------------------

@router.post(
    "/{ticket_id}/manual-resolve",
    response_model=ManualResolveResult,
    status_code=status.HTTP_200_OK,
    summary="Manually resolve a PENDING_REVIEW or IN_PROGRESS ticket",
    responses={
        200: {"description": "Ticket resolved; resolution indexed as training signal"},
        404: {"description": "Ticket not found"},
        409: {"description": "Ticket is not in a manually-resolvable status"},
        422: {"description": "Validation error — resolution_steps must not be empty"},
    },
)
async def manual_resolve(
    ticket_id: str,
    request: ManualResolveRequest,
    handler: Annotated[HumanTriageHandler, Depends(get_triage_handler)],
):
    """
    Submit the resolution steps performed by the NOC engineer.

    On success:
    1. The ticket status changes to **RESOLVED**.
    2. The `resolution_steps`, `primary_cause`, `resolution_code`, and
       `sop_reference` are persisted to the ticket record.
    3. The resolution is **indexed into Chroma** as a training signal so that
       future tickets with similar alarm descriptions can be auto-resolved
       without requiring human review.

    Only tickets in **PENDING_REVIEW** or **IN_PROGRESS** status can be
    manually resolved. Tickets already in RESOLVED, CLOSED, or ESCALATED
    status are rejected with HTTP 409.

    If an `sop_reference` is provided, it is stored as the `sop_id` on the
    ticket, enabling correlation with SOP coverage metrics. If left blank,
    the resolution will seed a candidate for a new SOP.
    """
    try:
        return await handler.manual_resolve(ticket_id, request)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
