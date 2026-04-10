"""
Correlation domain models.

CorrelationContext  — snapshot of all pre-dispatch check results assembled
                      before the LLM agent runs.  Passed into the agent as
                      structured context and exposed via agent tools.

DispatchMode        — the final truck-dispatch recommendation.

DispatchDecision    — full output of the correlation + agent pipeline,
                      replacing the generic RecommendationResult for the
                      telco pre-dispatch use-case.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.alarms.models import AlarmCheckResult
from app.maintenance.models import MaintenanceCheckResult
from app.models.recommendation import SimilarTicket, SOPMatch


# ---------------------------------------------------------------------------
# Dispatch recommendation enum
# ---------------------------------------------------------------------------

class DispatchMode(str, Enum):
    REMOTE   = "remote"    # fault can be resolved without truck roll
    ON_SITE  = "on_site"   # physical intervention required
    HOLD     = "hold"      # alarm cleared OR active maintenance — no action
    ESCALATE = "escalate"  # severity or complexity requires senior NOC / vendor


# ---------------------------------------------------------------------------
# Remote resolution feasibility
# ---------------------------------------------------------------------------

class RemoteFeasibility(BaseModel):
    """Evidence for whether remote resolution is likely to succeed."""
    feasible:            bool
    confidence:          float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)  # from SOP + similar tickets
    blocking_factors:    list[str] = Field(default_factory=list)  # reasons it must be on-site


# Fault types that are almost always on-site regardless of SOPs
ALWAYS_ONSITE_FAULTS = {"hardware_failure"}
# Fault types that are usually resolvable remotely
USUALLY_REMOTE_FAULTS = {"latency", "configuration_error", "congestion"}


def assess_remote_feasibility(
    fault_type: str,
    similar_tickets: list[SimilarTicket],
    sop_matches: list[SOPMatch],
) -> RemoteFeasibility:
    """
    Rule-based + evidence-based assessment of remote resolution possibility.
    The agent can call this and include it in its reasoning.
    """
    blocking: list[str] = []
    supporting: list[str] = []
    score = 0.5  # neutral baseline

    # Rule 1: fault type priors
    if fault_type in ALWAYS_ONSITE_FAULTS:
        blocking.append(f"Fault type '{fault_type}' almost always requires physical access.")
        score -= 0.3
    elif fault_type in USUALLY_REMOTE_FAULTS:
        supporting.append(f"Fault type '{fault_type}' is typically resolvable remotely.")
        score += 0.2

    # Rule 2: historical ticket evidence
    remote_resolutions = [
        t for t in similar_tickets
        if t.resolution_summary and any(
            kw in t.resolution_summary.lower()
            for kw in ("remotely", "ssh", "cli", "nms", "restarted", "config", "rolled back")
        )
    ]
    onsite_resolutions = [
        t for t in similar_tickets
        if t.resolution_summary and any(
            kw in t.resolution_summary.lower()
            for kw in ("dispatch", "field", "on-site", "replaced", "engineer visited", "truck")
        )
    ]
    if remote_resolutions:
        supporting.append(
            f"{len(remote_resolutions)} similar past ticket(s) resolved remotely: "
            + ", ".join(t.ticket_id for t in remote_resolutions[:3])
        )
        score += 0.15 * min(len(remote_resolutions), 3)
    if onsite_resolutions:
        blocking.append(
            f"{len(onsite_resolutions)} similar past ticket(s) required on-site visit."
        )
        score -= 0.15 * min(len(onsite_resolutions), 3)

    # Rule 3: SOP content hints
    for sop in sop_matches:
        text = sop.content.lower()
        if any(kw in text for kw in ("ssh", "cli", "remote", "nms command", "restart service")):
            supporting.append(f"SOP '{sop.title}' includes remote-executable steps.")
            score += 0.1
        if any(kw in text for kw in ("field engineer", "dispatch", "physically", "on-site", "replace")):
            blocking.append(f"SOP '{sop.title}' requires physical access.")
            score -= 0.1

    score = max(0.0, min(1.0, score))
    feasible = score >= 0.5 and not any("always requires physical" in b for b in blocking)

    return RemoteFeasibility(
        feasible=feasible,
        confidence=round(score, 3),
        supporting_evidence=supporting,
        blocking_factors=blocking,
    )


# ---------------------------------------------------------------------------
# Correlation context — assembled BEFORE the LLM agent runs
# ---------------------------------------------------------------------------

class CorrelationContext(BaseModel):
    """
    All pre-dispatch check results assembled in parallel before the agent.
    Injected into the agent prompt as structured context.
    """
    ticket_id:          str
    affected_node:      str
    fault_type:         str
    alarm_check:        AlarmCheckResult
    maintenance_check:  MaintenanceCheckResult
    similar_tickets:    list[SimilarTicket]    = Field(default_factory=list)
    sop_matches:        list[SOPMatch]         = Field(default_factory=list)
    remote_feasibility: Optional[RemoteFeasibility] = None
    assembled_at:       datetime               = Field(default_factory=datetime.utcnow)

    @property
    def should_short_circuit(self) -> bool:
        """True when alarm cleared or in maintenance — skip LLM, return HOLD."""
        return self.alarm_check.dispatch_blocked or self.maintenance_check.dispatch_blocked

    @property
    def short_circuit_reason(self) -> str:
        reasons = []
        if self.alarm_check.dispatch_blocked:
            reasons.append(self.alarm_check.summary)
        if self.maintenance_check.dispatch_blocked:
            reasons.append(self.maintenance_check.summary)
        return " | ".join(reasons)

    def as_agent_context_str(self) -> str:
        """Render a structured text block for injection into the LLM prompt."""
        lines = [
            "=== PRE-DISPATCH CORRELATION CONTEXT ===",
            f"Node:       {self.affected_node}",
            f"Fault Type: {self.fault_type}",
            "",
            "--- ALARM STATUS ---",
            self.alarm_check.summary,
            "",
            "--- PLANNED MAINTENANCE ---",
            self.maintenance_check.summary,
        ]
        if self.remote_feasibility:
            rf = self.remote_feasibility
            lines += [
                "",
                "--- REMOTE FEASIBILITY ASSESSMENT ---",
                f"Feasible: {rf.feasible} (confidence: {rf.confidence:.0%})",
            ]
            if rf.supporting_evidence:
                lines.append("Supporting: " + "; ".join(rf.supporting_evidence))
            if rf.blocking_factors:
                lines.append("Blocking:   " + "; ".join(rf.blocking_factors))
        if self.similar_tickets:
            lines += ["", "--- SIMILAR PAST TICKETS ---"]
            for t in self.similar_tickets[:3]:
                lines.append(f"  [{t.ticket_id}] score={t.score:.2f} — {t.resolution_summary or 'no resolution recorded'}")
        if self.sop_matches:
            lines += ["", "--- RELEVANT SOPs ---"]
            for s in self.sop_matches[:3]:
                lines.append(f"  [{s.sop_id}] {s.title} (score={s.score:.2f})")
        lines.append("=" * 40)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Final dispatch decision
# ---------------------------------------------------------------------------

class DispatchDecision(BaseModel):
    """
    Complete output of the pre-dispatch correlation + agent pipeline.
    Replaces the generic RecommendationResult for telco use cases.
    """
    ticket_id:           str
    dispatch_mode:       DispatchMode
    confidence_score:    float                  = Field(ge=0.0, le=1.0)
    recommended_steps:   list[str]              = Field(default_factory=list)
    reasoning:           str                    = ""
    escalation_required: bool                   = False

    # Correlation evidence
    alarm_check:         Optional[AlarmCheckResult]       = None
    maintenance_check:   Optional[MaintenanceCheckResult] = None
    remote_feasibility:  Optional[RemoteFeasibility]      = None
    similar_ticket_ids:  list[str]                        = Field(default_factory=list)
    relevant_sops:       list[str]                        = Field(default_factory=list)

    # Short-circuit flag — True when HOLD was set before the LLM ran
    short_circuited:     bool = False
    short_circuit_reason: str = ""

    @property
    def truck_required(self) -> bool:
        return self.dispatch_mode == DispatchMode.ON_SITE

    @classmethod
    def hold_from_context(cls, ticket_id: str, ctx: CorrelationContext) -> "DispatchDecision":
        """Construct a HOLD decision directly from correlation context (no LLM needed)."""
        return cls(
            ticket_id=ticket_id,
            dispatch_mode=DispatchMode.HOLD,
            confidence_score=1.0,
            reasoning=ctx.short_circuit_reason,
            recommended_steps=[
                "Monitor alarm state in NMS.",
                "Close ticket automatically if alarm remains cleared for 30 minutes.",
            ] if ctx.alarm_check.dispatch_blocked else [
                "Coordinate with maintenance team.",
                "Re-evaluate after maintenance window closes.",
            ],
            alarm_check=ctx.alarm_check,
            maintenance_check=ctx.maintenance_check,
            short_circuited=True,
            short_circuit_reason=ctx.short_circuit_reason,
        )
