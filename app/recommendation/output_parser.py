"""
Parses raw LLM agent output into structured DispatchDecision objects.

Handles:
  - Clean JSON output (happy path)
  - JSON embedded in prose or markdown fences
  - Partial JSON with missing keys (graceful defaults)
  - Completely unparseable output (returns safe fallback)
"""
from __future__ import annotations

import json
import logging
import re

from app.correlation.models import CorrelationContext, DispatchDecision, DispatchMode
from app.models.telco_ticket import Severity, TelcoTicketCreate

log = logging.getLogger(__name__)

_DISPATCH_MODE_MAP: dict[str, DispatchMode] = {
    "remote":   DispatchMode.REMOTE,
    "on_site":  DispatchMode.ON_SITE,
    "on-site":  DispatchMode.ON_SITE,
    "onsite":   DispatchMode.ON_SITE,
    "hold":     DispatchMode.HOLD,
    "escalate": DispatchMode.ESCALATE,
    "escalated":DispatchMode.ESCALATE,
}


def _extract_json(text: str) -> dict:
    """Extract a JSON object from free text, stripping markdown fences if present."""
    text = re.sub(r"```(?:json)?", "", text).strip("`").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in agent output: {text[:200]}")


def parse_agent_output(
    raw_output: str,
    ticket: TelcoTicketCreate,
    ticket_id: str,
    correlation_ctx: CorrelationContext | None = None,
) -> DispatchDecision:
    """
    Parse LLM output into a DispatchDecision.

    Falls back gracefully:
      - Invalid JSON      → DispatchMode.ON_SITE (safe default for telco)
      - Missing field     → sensible default for that field
      - Critical severity → escalation_required forced True
    """
    try:
        data = _extract_json(raw_output)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Failed to parse agent output as JSON: %s", exc)
        data = {}

    # dispatch_mode
    raw_mode = str(data.get("dispatch_mode", "on_site")).lower().strip()
    dispatch_mode = _DISPATCH_MODE_MAP.get(raw_mode, DispatchMode.ON_SITE)

    # escalation — force True for CRITICAL severity
    escalation = bool(data.get("escalation_required", False))
    if ticket.severity == Severity.CRITICAL and not escalation:
        escalation = True

    # Build DispatchDecision
    decision = DispatchDecision(
        ticket_id=ticket_id,
        dispatch_mode=dispatch_mode,
        confidence_score=float(data.get("confidence_score", 0.5)),
        recommended_steps=data.get("recommended_steps", []),
        reasoning=data.get("reasoning", ""),
        escalation_required=escalation,
        relevant_sops=data.get("relevant_sops", []),
        similar_ticket_ids=data.get("similar_ticket_ids", []),
        alarm_check=correlation_ctx.alarm_check if correlation_ctx else None,
        maintenance_check=correlation_ctx.maintenance_check if correlation_ctx else None,
        remote_feasibility=correlation_ctx.remote_feasibility if correlation_ctx else None,
        short_circuited=False,
    )

    log.info(
        "Parsed dispatch decision: ticket=%s mode=%s confidence=%.2f escalation=%s",
        ticket_id, dispatch_mode.value, decision.confidence_score, escalation,
    )
    return decision


# Keep backward-compatible shim for the generic (non-telco) pipeline
def parse_agent_output_generic(raw_output: str, ticket, ticket_id: str = ""):
    """Original generic parser — preserved for the non-telco RecommendationResult path."""
    from app.models.recommendation import RecommendationResult
    try:
        data = _extract_json(raw_output)
    except (json.JSONDecodeError, ValueError):
        data = {}
    return RecommendationResult(
        ticket_id=ticket_id,
        recommended_steps=data.get("recommended_steps", []),
        confidence_score=float(data.get("confidence_score", 0.0)),
        relevant_sops=data.get("relevant_sops", []),
        similar_ticket_ids=data.get("similar_ticket_ids", []),
        escalation_required=bool(data.get("escalation_required", False)),
        reasoning=data.get("reasoning", ""),
    )
