"""
Human-in-the-loop (HITL) triage models.

Used when the automated pipeline cannot produce a high-confidence resolution
because one or more of the following gaps exist:
  • No SOP exists for the detected alarm class
  • No sufficiently similar historical ticket found in the vector store
  • Agent confidence score falls below the auto-resolve threshold
  • Fault type could not be classified (UNKNOWN)

Lifecycle:
  PENDING_REVIEW   — ticket flagged by pipeline; appears in /pending-review queue
  assigned_to set  — NOC engineer claimed the ticket
  ManualResolveRequest submitted  → ticket moves to RESOLVED (or ESCALATED)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UnresolvableReason(str, Enum):
    """
    Why the automated pipeline could not produce a resolution.
    Multiple reasons may apply to a single ticket.
    """
    NO_SOP_MATCH            = "no_sop_match"
    NO_HISTORICAL_PRECEDENT = "no_historical_precedent"
    LOW_CONFIDENCE          = "low_confidence"
    UNKNOWN_FAULT_TYPE      = "unknown_fault_type"


class TriageSummary(BaseModel):
    """
    Lightweight record returned by GET /pending-review.
    Contains just enough information for the NOC dashboard to prioritise.
    """
    ticket_id:    str
    affected_node: str
    fault_type:   str
    severity:     str
    network_type: Optional[str]
    alarm_name:   Optional[str]
    alarm_category: Optional[str]
    location_details: Optional[str]
    description:  str
    reasons:      list[str]  # UnresolvableReason values or legacy DB strings
    confidence_score: float = Field(
        description="Agent confidence at time of flagging (0.0 = no SOP/history)."
    )
    sop_candidates_found:  int = Field(
        default=0, description="Number of SOPs the retriever found (may be 0)."
    )
    similar_tickets_found: int = Field(
        default=0, description="Number of historical matches returned (may be 0)."
    )
    flagged_at:   datetime
    assigned_to:  Optional[str] = None
    assigned_at:  Optional[datetime] = None


class AssignRequest(BaseModel):
    """
    POST /telco-tickets/{ticket_id}/assign

    Routes a PENDING_REVIEW ticket to a specific engineer or NOC group.
    The ticket remains PENDING_REVIEW until manually resolved or escalated.
    """
    assign_to: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Engineer login (e.g. 'ahmad.zulkifli') or group name (e.g. 'ATO-BSM-East').",
        examples=["ahmad.zulkifli", "ATO-BSM-East"],
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Optional routing notes visible to the assignee.",
    )


class AssignResult(BaseModel):
    """Response from POST /telco-tickets/{ticket_id}/assign."""
    ticket_id:  str
    assigned_to: str
    assigned_at: datetime
    message:    str


class ManualResolveRequest(BaseModel):
    """
    POST /telco-tickets/{ticket_id}/manual-resolve

    The assigned NOC engineer provides the resolution steps they performed.
    The ticket is marked RESOLVED and the resolution is indexed into Chroma
    as a training signal so future similar tickets can be auto-resolved.
    """
    resolved_by: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Engineer login performing the manual resolution.",
    )
    resolution_steps: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of steps taken to resolve the fault.",
    )
    sop_reference: Optional[str] = Field(
        default=None,
        max_length=64,
        description=(
            "SOP ID applied (if an existing SOP covered this fault). "
            "Leave None if resolved ad-hoc — the resolution will seed a future SOP."
        ),
    )
    primary_cause: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Root cause identified during investigation.",
    )
    resolution_code: Optional[str] = Field(
        default=None,
        max_length=256,
        description="CTTS-style resolution code (e.g. 'Hardware Replacement', 'Restart').",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Additional context for future reference / SOP authoring.",
    )


class ManualResolveResult(BaseModel):
    """Response from POST /telco-tickets/{ticket_id}/manual-resolve."""
    ticket_id:               str
    new_status:              str
    message:                 str
    executed_steps:          list[str]
    sop_reference:           Optional[str]
    resolved_by:             str
    resolved_at:             datetime
    indexed_as_training_signal: bool
