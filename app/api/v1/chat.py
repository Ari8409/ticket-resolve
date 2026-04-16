"""
Cognitive chat endpoint for NOC engineers.

POST /api/v1/chat
    Accepts a natural language message from an engineer.
    The handler:
      1. Detects intent from the message (regex + keyword heuristics)
      2. Executes the matched action (ticket lookup, recommendation fetch,
         assign, manual-resolve, stats query, or free-form classification)
      3. Returns a structured reply with human-readable text + optional data

Supported intents
-----------------
  show ticket <id>         → fetch ticket + dispatch decision
  pending / queue          → list PENDING_REVIEW tickets
  assign <id> to <eng>     → assign ticket to engineer
  resolve <id>             → prompt for resolution or submit it
  stats / dashboard        → return current ticket counts
  classify / fault         → classify fault description via FaultClassifier
  help                     → list available commands
  <anything else>          → general guidance with available actions
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends

from app.dependencies import (
    get_chat_feedback_repo,
    get_matching_engine,
    get_telco_repo,
    get_triage_handler,
)
from app.matching.engine import MatchingEngine
from app.models.human_triage import AssignRequest
from app.review.feedback import retrieve_chat_feedback_context
from app.review.triage import HumanTriageHandler
from app.storage.chat_feedback_store import ChatFeedbackRepository, ChatFeedbackRow
from app.storage.telco_repositories import TelcoTicketRepository

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    engineer_id: Optional[str] = Field(default="noc_engineer", max_length=128)
    context: Optional[dict] = Field(default=None)
    history: Optional[list[ChatMessage]] = Field(default=None)


class ChatResponse(BaseModel):
    reply: str
    intent: str
    data: Optional[Any] = None
    suggested_actions: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ChatFeedbackRequest(BaseModel):
    message_id: str
    rating: Literal[1, -1]
    comment: Optional[str] = Field(default=None, max_length=500)
    engineer_id: Optional[str] = Field(default=None, max_length=128)
    query_text: str = Field(..., max_length=2000)
    response_text: str = Field(..., max_length=5000)
    ticket_context: Optional[str] = Field(default=None, max_length=64)
    intent: Optional[str] = Field(default=None, max_length=64)


class ChatFeedbackResponse(BaseModel):
    message_id: str
    rating: int
    indexed: bool
    message: str


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

_TICKET_ID_RE        = re.compile(r"\b(TKT-[A-Z0-9]{8}|XLS-\d{1,4})\b", re.IGNORECASE)
_SHOW_RE             = re.compile(r"\b(show|get|fetch|view|open|detail)\b", re.IGNORECASE)
_ASSIGN_RE           = re.compile(r"\bassign\b", re.IGNORECASE)
_ASSIGN_TO_RE        = re.compile(r"\bto\s+(\S+)", re.IGNORECASE)
_RESOLVE_RE          = re.compile(r"\b(resolve|fix|close|complete|done|finish)\b", re.IGNORECASE)
_PENDING_RE          = re.compile(r"\b(pending|queue|triage|waiting|escalat)\b", re.IGNORECASE)
_STATS_RE            = re.compile(r"\b(stats|statistics|dashboard|summary|count|total|overview)\b", re.IGNORECASE)
_CLASSIFY_RE         = re.compile(r"\b(classify|fault|alarm|diagnos|what is|detect)\b", re.IGNORECASE)
_HELP_RE             = re.compile(r"\b(help|commands|what can|what do|guide)\b", re.IGNORECASE)
_LIST_RE             = re.compile(r"\b(list|all|show all|recent)\b", re.IGNORECASE)
_RESOLUTION_TREE_RE  = re.compile(
    r"\b(how was|how did|why was|explain.*resolv|resolution tree|execution tree|pipeline|what matched|how it was)\b",
    re.IGNORECASE,
)
_PENDING_TREE_RE     = re.compile(
    r"\b(why.*pending|why.*human|why.*review|why.*intervention|why.*held|why.*not resolved|explain.*pending|reason.*pending|what failed|why need)\b",
    re.IGNORECASE,
)


def _detect_intent(msg: str) -> str:
    if _HELP_RE.search(msg):    return "help"
    if _STATS_RE.search(msg):   return "stats"
    if _PENDING_RE.search(msg) and not _TICKET_ID_RE.search(msg): return "pending_queue"

    has_ticket = bool(_TICKET_ID_RE.search(msg))
    if has_ticket and _RESOLUTION_TREE_RE.search(msg): return "resolution_tree"
    if has_ticket and _PENDING_TREE_RE.search(msg):    return "pending_tree"
    if has_ticket and _ASSIGN_RE.search(msg):          return "assign"
    if has_ticket and _RESOLVE_RE.search(msg):         return "show_ticket"
    if has_ticket and _SHOW_RE.search(msg):            return "show_ticket"
    if has_ticket:                                     return "show_ticket"

    if _PENDING_RE.search(msg): return "pending_queue"
    if _LIST_RE.search(msg):    return "list_tickets"
    if _CLASSIFY_RE.search(msg): return "classify_hint"
    return "general"


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------

async def _handle_stats(repo: TelcoTicketRepository) -> ChatResponse:
    stats = await repo.get_stats()
    lines = [
        "📊 **Current NOC Dashboard Statistics**",
        "",
        f"• **Total Tickets**    : {stats['total']}",
        f"• **Open / Active**    : {stats['open']}",
        f"• **In Progress**      : {stats['in_progress']}",
        f"• **Pending Review**   : {stats['pending_review']}  ← awaiting human triage",
        f"• **Resolved**         : {stats['resolved']}",
        f"• **Escalated**        : {stats['escalated']}",
        f"• **Closed**           : {stats['closed']}",
        f"• **Failed (pipeline)**  : {stats['failed']}",
    ]
    return ChatResponse(
        reply="\n".join(lines),
        intent="stats",
        data=stats,
        suggested_actions=["Show pending queue", "Show recent tickets", "Show open tickets"],
    )


async def _handle_pending(triage: HumanTriageHandler) -> ChatResponse:
    summaries = await triage.list_pending(limit=20)
    if not summaries:
        return ChatResponse(
            reply="✅ No tickets are currently in the PENDING_REVIEW queue. The pipeline has handled all recent tickets automatically.",
            intent="pending_queue",
            data=[],
            suggested_actions=["Show stats", "Show recent tickets"],
        )

    lines = [
        f"🔔 **{len(summaries)} ticket(s) awaiting human triage** (oldest first):",
        "",
    ]
    for s in summaries[:10]:
        reasons_str = ", ".join(r.value.replace("_", " ") for r in s.reasons)
        lines.append(
            f"• **{s.ticket_id}** | {s.affected_node} | {s.severity.upper()} | {s.fault_type}"
            f"\n  Reasons: {reasons_str}"
            + (f" | Assigned to: {s.assigned_to}" if s.assigned_to else " | *Unassigned*")
        )

    if len(summaries) > 10:
        lines.append(f"\n_…and {len(summaries) - 10} more._")

    lines.append("\n💡 Tip: Type `show TKT-XXXXXXXX` to see full details, or `assign TKT-XXXXXXXX to <engineer>` to route a ticket.")

    return ChatResponse(
        reply="\n".join(lines),
        intent="pending_queue",
        data=[s.model_dump() for s in summaries],
        suggested_actions=[f"Show {s.ticket_id}" for s in summaries[:3]]
        + ["Show stats"],
    )


async def _handle_show_ticket(
    msg: str,
    repo: TelcoTicketRepository,
) -> ChatResponse:
    match = _TICKET_ID_RE.search(msg)
    if not match:
        return ChatResponse(
            reply="⚠️ I couldn't find a valid ticket ID in your message. Ticket IDs look like `TKT-A1B2C3D4`.",
            intent="show_ticket",
            suggested_actions=["Show pending queue", "Show stats"],
        )

    ticket_id = match.group(0).upper()
    ticket = await repo.get(ticket_id)
    if not ticket:
        return ChatResponse(
            reply=f"❌ Ticket **{ticket_id}** was not found in the database.",
            intent="show_ticket",
            suggested_actions=["Show pending queue", "Show stats"],
        )

    decision = await repo.get_dispatch_decision(ticket_id)
    status = str(ticket["status"].value if hasattr(ticket["status"], "value") else ticket["status"])
    severity = str(ticket["severity"].value if hasattr(ticket["severity"], "value") else ticket["severity"])
    fault_type = str(ticket["fault_type"].value if hasattr(ticket["fault_type"], "value") else ticket["fault_type"])

    lines = [
        f"🎫 **Ticket {ticket_id}**",
        "",
        f"• **Node**       : {ticket['affected_node']}",
        f"• **Status**     : {status.upper()}",
        f"• **Severity**   : {severity.upper()}",
        f"• **Fault Type** : {fault_type}",
        f"• **Network**    : {ticket.get('network_type') or 'N/A'}",
        f"• **Alarm**      : {ticket.get('alarm_name') or 'N/A'}",
    ]

    if ticket.get("assigned_to"):
        lines.append(f"• **Assigned to** : {ticket['assigned_to']}")

    if ticket.get("pending_review_reasons"):
        reasons = ", ".join(r.replace("_", " ") for r in ticket["pending_review_reasons"])
        lines.append(f"• **Pending reasons** : {reasons}")

    lines.append("")
    lines.append(f"**Description**: _{ticket['description'][:300]}_")

    if decision:
        lines += [
            "",
            f"**Pipeline Decision**: {decision.get('dispatch_mode', 'N/A').upper()} "
            f"(confidence: {decision.get('confidence_score', 0):.0%})",
        ]
        if decision.get("natural_language_summary"):
            lines.append(f"**Summary**: {decision['natural_language_summary'][:400]}")

    suggestions = []
    if status == "pending_review":
        suggestions = [
            f"Assign {ticket_id} to <engineer_name>",
            f"Resolve {ticket_id}",
        ]
    elif status in ("open", "in_progress"):
        suggestions = [f"Show review for {ticket_id}"]

    return ChatResponse(
        reply="\n".join(lines),
        intent="show_ticket",
        data={
            "ticket": {
                k: str(v.value if hasattr(v, "value") else v) if v is not None else None
                for k, v in ticket.items()
                if k in ("ticket_id", "affected_node", "fault_type", "severity",
                         "status", "network_type", "alarm_name", "description",
                         "assigned_to", "created_at", "updated_at")
            },
            "decision": decision,
        },
        suggested_actions=suggestions,
    )


async def _handle_assign(
    msg: str,
    triage: HumanTriageHandler,
) -> ChatResponse:
    ticket_match = _TICKET_ID_RE.search(msg)
    to_match     = _ASSIGN_TO_RE.search(msg)

    if not ticket_match:
        return ChatResponse(
            reply="⚠️ Please include a ticket ID. Example: `assign TKT-A1B2C3D4 to ahmad.zulkifli`",
            intent="assign",
        )

    ticket_id = ticket_match.group(0).upper()

    if not to_match:
        return ChatResponse(
            reply=f"⚠️ Please specify who to assign **{ticket_id}** to. Example: `assign {ticket_id} to ahmad.zulkifli`",
            intent="assign",
            suggested_actions=[f"Assign {ticket_id} to noc.engineer01", f"Assign {ticket_id} to ATO-BSM-East"],
        )

    assign_to = to_match.group(1).strip().rstrip(".,;!?")

    try:
        result = await triage.assign(ticket_id, AssignRequest(assign_to=assign_to))
        return ChatResponse(
            reply=(
                f"✅ **{ticket_id}** has been assigned to **{assign_to}**.\n\n"
                f"The ticket remains in PENDING_REVIEW status until {assign_to} submits a resolution.\n"
                f"Assignment time: {result.assigned_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            intent="assign",
            data=result.model_dump(),
            suggested_actions=[f"Show {ticket_id}", "Show pending queue"],
        )
    except ValueError as exc:
        return ChatResponse(
            reply=f"⚠️ Could not assign ticket: {exc}",
            intent="assign",
        )
    except Exception as exc:
        return ChatResponse(
            reply=f"❌ Assignment failed: {exc}",
            intent="assign",
        )


async def _handle_list_tickets(
    msg: str,
    repo: TelcoTicketRepository,
) -> ChatResponse:
    # Detect status filter from message
    status_filter = None
    for s in ("open", "pending_review", "resolved", "in_progress", "escalated", "failed", "closed"):
        if s.replace("_", " ") in msg.lower() or s in msg.lower():
            status_filter = s
            break

    rows, total = await repo.list_tickets(status=status_filter, limit=15)

    if not rows:
        filter_str = f" with status **{status_filter}**" if status_filter else ""
        return ChatResponse(
            reply=f"No tickets found{filter_str}.",
            intent="list_tickets",
            data={"tickets": [], "total": 0},
        )

    label = f"(filtered: {status_filter})" if status_filter else "(most recent)"
    lines = [f"📋 **{total} total tickets** {label} — showing up to 15:", ""]
    for r in rows:
        status = str(r["status"].value if hasattr(r["status"], "value") else r["status"])
        fault  = str(r["fault_type"].value if hasattr(r["fault_type"], "value") else r["fault_type"])
        sev    = str(r["severity"].value if hasattr(r["severity"], "value") else r["severity"])
        lines.append(f"• **{r['ticket_id']}** | {r['affected_node']} | {sev.upper()} | {fault} | {status.upper()}")

    serialised = []
    for r in rows:
        serialised.append({
            k: str(v.value if hasattr(v, "value") else v)
            for k, v in r.items()
            if k in ("ticket_id", "affected_node", "fault_type", "severity", "status", "network_type")
        })

    return ChatResponse(
        reply="\n".join(lines),
        intent="list_tickets",
        data={"tickets": serialised, "total": total},
        suggested_actions=["Show pending queue", "Show stats"],
    )


_REASON_LABELS: dict[str, str] = {
    "no_similar_ticket":        "No historical ticket match (similarity score below 0.60 threshold)",
    "no_sop_match":             "No SOP match found (similarity score below 0.45 threshold)",
    "LOW_CONFIDENCE":           "Pipeline confidence too low for auto-resolution",
    "NO_SOP_MATCH":             "No matching SOP in knowledge base",
    "NO_HISTORICAL_PRECEDENT":  "No similar resolved ticket found in history",
    "UNKNOWN_FAULT_TYPE":       "Fault type could not be reliably classified",
}


async def _handle_resolution_tree(
    msg: str,
    repo: TelcoTicketRepository,
) -> ChatResponse:
    match = _TICKET_ID_RE.search(msg)
    if not match:
        return ChatResponse(
            reply="Please include a ticket ID. Example: `how was XLS-0001 resolved?`",
            intent="resolution_tree",
            suggested_actions=["Show pending queue", "Show stats"],
        )

    ticket_id = match.group(0).upper()
    ticket = await repo.get(ticket_id)
    if not ticket:
        return ChatResponse(
            reply=f"Ticket **{ticket_id}** was not found.",
            intent="resolution_tree",
            suggested_actions=["Show pending queue"],
        )

    decision = await repo.get_dispatch_decision(ticket_id)
    status     = str(ticket["status"].value if hasattr(ticket["status"], "value") else ticket["status"])
    fault_type = str(ticket["fault_type"].value if hasattr(ticket["fault_type"], "value") else ticket["fault_type"])

    sim_ids  = decision.get("similar_ticket_ids", []) if decision else []
    sop_refs = decision.get("relevant_sops", []) if decision else []
    conf     = decision.get("confidence_score", 0.0) if decision else 0.0
    dispatch = decision.get("dispatch_mode") if decision else None
    reasoning = decision.get("reasoning", "") if decision else ""
    res_steps = ticket.get("resolution_steps") or []
    rec_steps = decision.get("recommended_steps", []) if decision else []

    # Use recommended_steps as fallback when resolution_steps is empty
    steps_to_show = res_steps if res_steps else rec_steps

    execution_tree = {
        "ticket_id":         ticket_id,
        "mode":              "resolution",
        "final_status":      status,
        "alarm_name":        ticket.get("alarm_name"),
        "affected_node":     ticket.get("affected_node"),
        "fault_type":        fault_type,
        "network_type":      ticket.get("network_type"),
        "gate_passed":       status == "resolved",
        "similar_ticket_ids": sim_ids,
        "relevant_sops":     sop_refs,
        "confidence_score":  conf,
        "dispatch_mode":     dispatch,
        "reasoning":         reasoning,
        "short_circuited":   decision.get("short_circuited", False) if decision else False,
        "short_circuit_reason": decision.get("short_circuit_reason") if decision else None,
        "resolution_steps":  steps_to_show,
        "alarm_status":      decision.get("alarm_status") if decision else None,
        "remote_feasible":   decision.get("remote_feasible") if decision else None,
        "remote_confidence": decision.get("remote_confidence") if decision else None,
    }

    sim_str = f"`{sim_ids[0]}`" if sim_ids else "None"
    sop_str = f"`{sop_refs[0]}`" if sop_refs else "None"

    lines = [
        f"**Resolution Pipeline — {ticket_id}**",
        "",
        f"**[1] Fault**   {ticket.get('alarm_name') or fault_type} on `{ticket.get('affected_node')}` ({ticket.get('network_type') or 'N/A'})",
        f"**[2] Search**  Similar ticket: {sim_str} | SOP: {sop_str}",
        f"**[3] Gate**    PASSED — {reasoning or 'vector similarity match'}",
        f"**[4] Action**  {(dispatch or 'N/A').upper()} · confidence {conf:.0%}",
        f"**[5] Status**  {status.upper()}",
    ]
    if steps_to_show:
        lines += ["", f"**Resolution Steps** ({len(steps_to_show)} total):"]
        for i, step in enumerate(steps_to_show[:6], 1):
            lines.append(f"{i}. {step}")
        if len(steps_to_show) > 6:
            lines.append(f"_…and {len(steps_to_show) - 6} more steps._")

    return ChatResponse(
        reply="\n".join(lines),
        intent="resolution_tree",
        data=execution_tree,
        suggested_actions=[f"Show {ticket_id}", "Show pending queue"],
    )


async def _handle_pending_tree(
    msg: str,
    repo: TelcoTicketRepository,
) -> ChatResponse:
    match = _TICKET_ID_RE.search(msg)
    if not match:
        return ChatResponse(
            reply="Please include a ticket ID. Example: `why does XLS-0002 need human review?`",
            intent="pending_tree",
            suggested_actions=["Show pending queue"],
        )

    ticket_id = match.group(0).upper()
    ticket = await repo.get(ticket_id)
    if not ticket:
        return ChatResponse(
            reply=f"Ticket **{ticket_id}** was not found.",
            intent="pending_tree",
            suggested_actions=["Show pending queue"],
        )

    decision  = await repo.get_dispatch_decision(ticket_id)
    fault_type = str(ticket["fault_type"].value if hasattr(ticket["fault_type"], "value") else ticket["fault_type"])
    reasons   = ticket.get("pending_review_reasons") or []
    sim_ids   = decision.get("similar_ticket_ids", []) if decision else []
    sop_refs  = decision.get("relevant_sops", []) if decision else []
    conf      = decision.get("confidence_score", 0.0) if decision else 0.0
    reasoning = decision.get("reasoning", "") if decision else ""

    execution_tree = {
        "ticket_id":          ticket_id,
        "mode":               "pending",
        "final_status":       "pending_review",
        "alarm_name":         ticket.get("alarm_name"),
        "affected_node":      ticket.get("affected_node"),
        "fault_type":         fault_type,
        "network_type":       ticket.get("network_type"),
        "gate_passed":        False,
        "pending_reasons":    reasons,
        "similar_ticket_ids": sim_ids,
        "relevant_sops":      sop_refs,
        "confidence_score":   conf,
        "reasoning":          reasoning,
        "assigned_to":        ticket.get("assigned_to"),
        "assigned_at":        ticket.get("assigned_at").isoformat() if ticket.get("assigned_at") else None,
    }

    lines = [
        f"**Why Pending Review — {ticket_id}**",
        "",
        f"**[1] Fault**   {ticket.get('alarm_name') or fault_type} on `{ticket.get('affected_node')}` ({ticket.get('network_type') or 'N/A'})",
        f"**[2] Search**  Similar tickets: {'none found' if not sim_ids else sim_ids} | SOPs: {'none found' if not sop_refs else sop_refs}",
        f"**[3] Gate**    FAILED — {reasoning or 'no_match'}",
        f"**[4] Result**  Escalated to human review queue",
        "",
        "**Reasons this ticket was not auto-resolved:**",
    ]
    for r in reasons:
        lines.append(f"- {_REASON_LABELS.get(r, r.replace('_', ' '))}")

    if not reasons:
        lines.append("- No matching SOP or similar historical ticket found")

    if ticket.get("assigned_to"):
        lines += ["", f"**Assigned to**: `{ticket['assigned_to']}`"]
    else:
        lines += ["", "_Not yet assigned — use `assign {ticket_id} to <engineer>` to route this ticket._".replace("{ticket_id}", ticket_id)]

    return ChatResponse(
        reply="\n".join(lines),
        intent="pending_tree",
        data=execution_tree,
        suggested_actions=[
            f"Assign {ticket_id} to <engineer_name>",
            f"Show {ticket_id}",
            "Show pending queue",
        ],
    )


def _handle_classify_hint() -> ChatResponse:
    return ChatResponse(
        reply=(
            "🔍 **Fault Classification**\n\n"
            "To classify a fault description, use the **Classify** panel in the dashboard, "
            "or POST to `/api/v1/classify/` with:\n\n"
            "```json\n"
            '{"text": "LTE_ENB_780321*equipmentAlarm/HW Fault*1*HW Fault\\n\\nHW Fault Unknown"}\n'
            "```\n\n"
            "The classifier will return the fault type, affected layer, confidence score, "
            "and relevant SOPs."
        ),
        intent="classify_hint",
        suggested_actions=["Show stats", "Show pending queue"],
    )


def _handle_help() -> ChatResponse:
    return ChatResponse(
        reply=(
            "🤖 **NOC Cognitive Assistant — Available Commands**\n\n"
            "| Command | Example |\n"
            "|---------|----------|\n"
            "| Show ticket | `show XLS-0001` |\n"
            "| Resolution pipeline | `how was XLS-0001 resolved?` |\n"
            "| Why pending review | `why does XLS-0002 need human intervention?` |\n"
            "| List all tickets | `list tickets` |\n"
            "| List by status | `list open tickets` / `list pending tickets` |\n"
            "| Pending triage queue | `show pending queue` |\n"
            "| Assign ticket | `assign XLS-0002 to ahmad.zulkifli` |\n"
            "| Dashboard stats | `show stats` |\n"
            "| Help | `help` |\n\n"
            "💡 You can also use the action buttons in the Triage Queue panel to assign and resolve tickets directly."
        ),
        intent="help",
        suggested_actions=["Show stats", "Show pending queue", "List tickets"],
    )


def _handle_general(msg: str) -> ChatResponse:
    return ChatResponse(
        reply=(
            "I didn't quite understand that. Here are some things I can help with:\n\n"
            "• **`show stats`** — Dashboard ticket counts\n"
            "• **`show pending queue`** — Tickets waiting for human review\n"
            "• **`show TKT-XXXXXXXX`** — Details for a specific ticket\n"
            "• **`assign TKT-XXXXXXXX to <engineer>`** — Route a ticket\n"
            "• **`list tickets`** — Recent ticket list\n"
            "• **`help`** — Full command reference\n\n"
            f"_Your message: \"{msg[:100]}\"_"
        ),
        intent="general",
        suggested_actions=["Show stats", "Show pending queue", "Help"],
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Cognitive chat interface for NOC engineers",
)
async def chat(
    request:         ChatRequest,
    repo:            Annotated[TelcoTicketRepository, Depends(get_telco_repo)],
    triage:          Annotated[HumanTriageHandler,    Depends(get_triage_handler)],
    matching_engine: Annotated[MatchingEngine,        Depends(get_matching_engine)],
):
    """
    Natural language chat interface for NOC engineers.

    Detects intent from the message and calls the appropriate backend
    service — ticket lookup, triage queue, assign, stats, etc.

    For general/unrecognised queries, retrieves relevant past engineer
    feedback from Chroma and prepends it to the reply as contextual guidance.

    Returns a structured reply with:
    - `reply`             — markdown-formatted human-readable response
    - `intent`            — detected intent label
    - `data`              — structured payload (ticket dict, stats dict, etc.)
    - `suggested_actions` — follow-up commands the UI can surface as quick-reply buttons
    - `message_id`        — UUID for referencing this response in feedback submissions
    """
    msg    = request.message.strip()
    intent = _detect_intent(msg)

    log.info("Chat request — engineer=%s intent=%s", request.engineer_id, intent)

    if intent == "help":
        response = _handle_help()
    elif intent == "stats":
        response = await _handle_stats(repo)
    elif intent == "pending_queue":
        response = await _handle_pending(triage)
    elif intent == "show_ticket":
        response = await _handle_show_ticket(msg, repo)
    elif intent == "resolution_tree":
        response = await _handle_resolution_tree(msg, repo)
    elif intent == "pending_tree":
        response = await _handle_pending_tree(msg, repo)
    elif intent == "assign":
        response = await _handle_assign(msg, triage)
    elif intent == "list_tickets":
        response = await _handle_list_tickets(msg, repo)
    elif intent == "classify_hint":
        response = _handle_classify_hint()
    else:
        response = _handle_general(msg)

    # For general queries, augment reply with relevant past engineer feedback
    if intent == "general":
        feedback_ctx = await retrieve_chat_feedback_context(msg, matching_engine)
        if feedback_ctx:
            response.reply = feedback_ctx + "\n\n---\n\n" + response.reply

    return response


@router.post(
    "/chat/feedback",
    response_model=ChatFeedbackResponse,
    summary="Submit thumbs-up / thumbs-down feedback on a chat response",
)
async def submit_chat_feedback(
    req:           ChatFeedbackRequest,
    feedback_repo: Annotated[ChatFeedbackRepository, Depends(get_chat_feedback_repo)],
    matching_engine: Annotated[MatchingEngine,       Depends(get_matching_engine)],
):
    """
    Record engineer feedback on a specific assistant message.

    - Persists the rating (1 / -1) and optional comment to SQLite.
    - If rating == 1 (positive): indexes the Q&A into Chroma with
      feedback_source="chat" so future queries can surface it as context.
    - Returns indexed=True only when Chroma indexing succeeded.
    """
    from app.review.feedback import ResolutionFeedbackIndexer

    row = ChatFeedbackRow(
        message_id=req.message_id,
        ticket_context=req.ticket_context,
        query_text=req.query_text,
        response_text=req.response_text,
        rating=req.rating,
        comment=req.comment,
        engineer_id=req.engineer_id,
        intent=req.intent,
    )
    await feedback_repo.record(row)

    indexed = False
    if req.rating == 1:
        try:
            indexer = ResolutionFeedbackIndexer(matching_engine=matching_engine)
            await indexer.index_chat_feedback(
                message_id=req.message_id,
                query_text=req.query_text,
                response_text=req.response_text,
                ticket_context=req.ticket_context,
                comment=req.comment,
                engineer_id=req.engineer_id,
            )
            indexed = True
        except Exception as exc:
            log.warning("Chat feedback Chroma indexing failed (message_id=%s): %s", req.message_id, exc)

    log.info(
        "Chat feedback recorded — message_id=%s rating=%s indexed=%s engineer=%s",
        req.message_id, req.rating, indexed, req.engineer_id,
    )
    return ChatFeedbackResponse(
        message_id=req.message_id,
        rating=req.rating,
        indexed=indexed,
        message="Thank you for your feedback!" if req.rating == 1 else "Feedback recorded.",
    )
