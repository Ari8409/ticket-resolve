"""
Human-review domain models.

A recommendation produced by ResolutionAgent is presented to a NOC engineer
(the "reviewer") via POST /telco-tickets/{ticket_id}/review.

The reviewer chooses one of three actions:

  approve   — accept the recommended steps as-is; they are recorded as
               executed and the ticket is marked RESOLVED.  The resolved
               ticket is then indexed into the vector store as a training
               signal for the similarity matcher.

  override  — reject the recommended SOP in favour of a different one.
               The reviewer supplies an override_sop_id; the system fetches
               that SOP's resolution steps, stores them on the dispatch
               decision, and marks the ticket IN_PROGRESS (awaiting
               re-approval once the steps are actioned).

  escalate  — flag the ticket for a senior engineer.  The ticket is marked
               ESCALATED and the escalation note is appended to remarks.
               No steps are executed; the ticket leaves the normal queue.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReviewAction(str, Enum):
    APPROVE  = "approve"
    OVERRIDE = "override"
    ESCALATE = "escalate"


class ReviewRequest(BaseModel):
    """Payload for POST /telco-tickets/{ticket_id}/review."""

    action: ReviewAction = Field(
        ...,
        description="Reviewer decision: approve, override, or escalate.",
    )
    # --- approve ---
    reviewed_by: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Identity of the reviewer (login / name). Stored in resolved_person.",
    )
    # --- override ---
    override_sop_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description=(
            "Required when action=override. SOP ID to substitute for the "
            "agent's recommendation (e.g. 'SOP-RAN-011')."
        ),
    )
    override_notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional explanation of why this SOP was chosen over the recommendation.",
    )
    # --- escalate ---
    escalation_note: Optional[str] = Field(
        default=None,
        max_length=2000,
        description=(
            "Required when action=escalate. Reason for escalation; "
            "appended to the ticket's remarks field."
        ),
    )
    escalate_to: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Name or team of the senior engineer this is escalated to.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "action": "approve",
                    "reviewed_by": "john.smith",
                },
                {
                    "action": "override",
                    "override_sop_id": "SOP-RAN-009",
                    "override_notes": "TX power issue confirmed — using TX-power-specific SOP.",
                    "reviewed_by": "jane.doe",
                },
                {
                    "action": "escalate",
                    "escalation_note": "Multiple correlated RAN alarms. Requires Ericsson TAC involvement.",
                    "escalate_to": "ericsson_tac_team",
                    "reviewed_by": "john.smith",
                },
            ]
        }
    }


class ReviewResult(BaseModel):
    """Response returned by POST /telco-tickets/{ticket_id}/review."""

    ticket_id:                  str
    action_taken:               ReviewAction
    new_status:                 str
    message:                    str
    executed_steps:             list[str]             = Field(default_factory=list)
    sop_applied:                Optional[str]         = None   # SOP ID that was used
    escalated_to:               Optional[str]         = None
    indexed_as_training_signal: bool                  = False
    reviewed_by:                Optional[str]         = None
    reviewed_at:                datetime              = Field(default_factory=datetime.utcnow)
