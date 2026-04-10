"""
Parses raw LLM agent output into structured DispatchDecision objects.

Handles:
  - Clean JSON output (happy path)
  - JSON embedded in prose or markdown fences
  - Partial JSON with missing keys (graceful defaults)
  - Completely unparseable output (returns safe on_site fallback)

New in this version:
  - Extracts natural_language_summary from agent output
  - Extracts ranked_sops list and converts each item to RankedSOP
"""
from __future__ import annotations

import json
import logging
import re

from app.correlation.models import CorrelationContext, DispatchDecision, DispatchMode
from app.models.recommendation import RankedSOP
from app.models.telco_ticket import Severity, TelcoTicketCreate

log = logging.getLogger(__name__)

_DISPATCH_MODE_MAP: dict[str, DispatchMode] = {
    "remote":    DispatchMode.REMOTE,
    "on_site":   DispatchMode.ON_SITE,
    "on-site":   DispatchMode.ON_SITE,
    "onsite":    DispatchMode.ON_SITE,
    "hold":      DispatchMode.HOLD,
    "escalate":  DispatchMode.ESCALATE,
    "escalated": DispatchMode.ESCALATE,
}


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from free text, stripping markdown fences."""
    text = re.sub(r"```(?:json)?", "", text).strip("`").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in agent output: {text[:200]}")


def _parse_ranked_sops(raw_sops: object) -> list[RankedSOP]:
    """
    Convert the raw ranked_sops value from the LLM JSON into RankedSOP objects.

    Accepts:
      - list[dict]  — happy path from a well-formed response
      - list[str]   — fallback when the LLM emits just titles
      - None / other — returns empty list
    """
    if not isinstance(raw_sops, list):
        return []

    result: list[RankedSOP] = []
    for item in raw_sops:
        if isinstance(item, dict):
            try:
                result.append(
                    RankedSOP(
                        sop_id=str(item.get("sop_id", "")),
                        title=str(item.get("title", "")),
                        confidence_score=float(item.get("confidence_score", 0.5)),
                        summary=str(item.get("summary", "")),
                        match_reason=str(item.get("match_reason", "")),
                        on_site_required=bool(item.get("on_site_required", False)),
                    )
                )
            except Exception as exc:
                log.debug("Skipping malformed ranked_sop entry: %s — %s", item, exc)
        elif isinstance(item, str) and item.strip():
            # LLM returned just a title string — create a minimal RankedSOP
            result.append(RankedSOP(sop_id="", title=item.strip(), confidence_score=0.5))

    # Sort by confidence descending (LLM should already do this, but enforce it)
    result.sort(key=lambda s: s.confidence_score, reverse=True)
    return result[:3]  # cap at top 3


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

    # escalation — force True for CRITICAL severity faults that are node down or hardware
    escalation = bool(data.get("escalation_required", False))
    if ticket.severity == Severity.CRITICAL and not escalation:
        escalation = True

    # ranked_sops — extracted and validated
    ranked_sops = _parse_ranked_sops(data.get("ranked_sops"))

    # natural_language_summary — generate a minimal fallback if absent
    nl_summary = str(data.get("natural_language_summary", "")).strip()
    if not nl_summary:
        nl_summary = _fallback_summary(ticket, dispatch_mode, escalation, ranked_sops)

    decision = DispatchDecision(
        ticket_id=ticket_id,
        dispatch_mode=dispatch_mode,
        confidence_score=float(data.get("confidence_score", 0.5)),
        recommended_steps=data.get("recommended_steps", []),
        reasoning=data.get("reasoning", ""),
        escalation_required=escalation,
        relevant_sops=data.get("relevant_sops", []),
        similar_ticket_ids=data.get("similar_ticket_ids", []),
        natural_language_summary=nl_summary,
        ranked_sops=ranked_sops,
        alarm_check=correlation_ctx.alarm_check if correlation_ctx else None,
        maintenance_check=correlation_ctx.maintenance_check if correlation_ctx else None,
        remote_feasibility=correlation_ctx.remote_feasibility if correlation_ctx else None,
        short_circuited=False,
    )

    log.info(
        "Parsed dispatch decision: ticket=%s mode=%s confidence=%.2f "
        "escalation=%s ranked_sops=%d summary_len=%d",
        ticket_id,
        dispatch_mode.value,
        decision.confidence_score,
        escalation,
        len(ranked_sops),
        len(nl_summary),
    )
    return decision


def _fallback_summary(
    ticket: TelcoTicketCreate,
    dispatch_mode: DispatchMode,
    escalation_required: bool,
    ranked_sops: list[RankedSOP],
) -> str:
    """Generate a minimal natural-language summary when the LLM didn't produce one."""
    sop_ref = f" Follow {ranked_sops[0].title}." if ranked_sops else ""
    escalation_note = " Escalation to senior NOC / vendor support is required." if escalation_required else ""
    mode_text = {
        DispatchMode.REMOTE:   "Remote resolution has been recommended — no truck roll required.",
        DispatchMode.ON_SITE:  "On-site dispatch is required for physical intervention.",
        DispatchMode.HOLD:     "Dispatch is on hold — the alarm has cleared or maintenance is active.",
        DispatchMode.ESCALATE: "This ticket requires escalation to senior NOC or vendor support.",
    }.get(dispatch_mode, "Resolution mode undetermined.")
    return (
        f"Ticket {ticket.ticket_id}: {ticket.fault_type.value.replace('_', ' ').title()} "
        f"detected on node {ticket.affected_node} (severity: {ticket.severity.value.upper()}). "
        f"{mode_text}{sop_ref}{escalation_note}"
    )


# ---------------------------------------------------------------------------
# Backward-compatible shim for the generic (non-telco) pipeline
# ---------------------------------------------------------------------------

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
