"""
ResolutionFeedbackIndexer — writes resolved tickets back to the Chroma vector store.

When a NOC engineer approves a recommendation and the ticket is marked RESOLVED,
this indexer embeds the full ticket + resolution details and upserts them into the
'tickets' Chroma collection with ``resolved=True``.

This creates a closed-loop training signal: future tickets with similar fault
descriptions, alarm names, or affected nodes will surface this resolution as a
high-confidence historical precedent via ``MatchingEngine.find_similar_resolved()``.

Document structure indexed per resolved ticket
----------------------------------------------
  {alarm_name} on {affected_node}
  Fault: {fault_type} | Network: {network_type} | Severity: {severity}
  Category: {alarm_category}
  Description: {description}
  Primary Cause: {primary_cause}
  Resolution: {resolution}
  Resolution Code: {resolution_code}
  Steps Applied:
    1. {step_1}
    2. {step_2}
    ...
  SOP Applied: {sop_id}

The resolution_summary stored in Chroma metadata is a compact one-liner:
  "{resolution_code} — {primary_cause} — via {sop_id}"
so it surfaces clearly in similarity search result previews.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.matching.engine import MatchingEngine
from app.models.telco_ticket import TelcoTicketCreate

log = logging.getLogger(__name__)


class ResolutionFeedbackIndexer:
    """
    Upserts a resolved telco ticket into the Chroma 'tickets' collection
    so it becomes a training signal for the similarity matcher.
    """

    def __init__(self, matching_engine: MatchingEngine) -> None:
        self._engine = matching_engine

    async def index_resolved(
        self,
        ticket_id: str,
        ticket: TelcoTicketCreate,
        executed_steps: list[str],
        sop_applied: str | None = None,
        reviewed_by: str | None = None,
    ) -> None:
        """
        Embed and index a resolved ticket as a training signal.

        Parameters
        ----------
        ticket_id:
            The persisted ticket ID (TKT-XXXXXXXX).
        ticket:
            The full TelcoTicketCreate with all CTTS fields populated.
            ``resolution``, ``resolution_code``, and ``primary_cause``
            should be set before calling this method.
        executed_steps:
            The ordered steps that were applied (from the approved
            DispatchDecision or from the overriding SOP).
        sop_applied:
            The SOP ID that was applied (from approve or override).
        reviewed_by:
            NOC engineer login stored in the document for audit purposes.
        """
        document = self._build_document(ticket, executed_steps, sop_applied, reviewed_by)
        resolution_summary = self._build_resolution_summary(ticket, sop_applied)

        await self._engine.index_telco_ticket(
            ticket_id=ticket_id,
            ticket=ticket,
            resolution_summary=resolution_summary,
            resolved=True,
        )

        log.info(
            "Indexed resolved ticket %s as training signal "
            "(sop=%s, resolution_code=%s, steps=%d)",
            ticket_id,
            sop_applied or "none",
            ticket.resolution_code or "unknown",
            len(executed_steps),
        )

    @staticmethod
    def _build_document(
        ticket: TelcoTicketCreate,
        executed_steps: list[str],
        sop_applied: str | None,
        reviewed_by: str | None,
    ) -> str:
        """
        Build the rich text document that will be embedded and stored in Chroma.

        This document is what future vector searches will score against, so it
        should contain every field that a human would consider when matching
        a new fault to a historical precedent.
        """
        parts = [
            f"{ticket.alarm_name or ticket.fault_type.value.replace('_', ' ').title()} "
            f"on {ticket.affected_node}",
            f"Fault: {ticket.fault_type.value}  |  "
            f"Network: {ticket.network_type or 'unknown'}  |  "
            f"Severity: {ticket.severity.value.upper()}",
        ]
        if ticket.alarm_category:
            parts.append(f"Category: {ticket.alarm_category}")
        if ticket.object_class:
            parts.append(f"Object Class: {ticket.object_class}")
        if ticket.location_details:
            parts.append(f"Site: {ticket.location_details}")

        parts.append(f"\nDescription:\n{ticket.description}")

        if ticket.primary_cause:
            parts.append(f"\nPrimary Cause: {ticket.primary_cause}")
        if ticket.remarks:
            parts.append(f"Remarks: {ticket.remarks}")
        if ticket.resolution:
            parts.append(f"Resolution: {ticket.resolution}")
        if ticket.resolution_code:
            parts.append(f"Resolution Code: {ticket.resolution_code}")

        if executed_steps:
            step_lines = "\n".join(f"  {i}. {s}" for i, s in enumerate(executed_steps, 1))
            parts.append(f"\nSteps Applied:\n{step_lines}")

        if sop_applied:
            parts.append(f"\nSOP Applied: {sop_applied}")
        if reviewed_by:
            parts.append(f"Reviewed By: {reviewed_by}")

        return "\n".join(parts)

    @staticmethod
    def _build_resolution_summary(
        ticket: TelcoTicketCreate,
        sop_applied: str | None,
    ) -> str:
        """
        Build the compact one-liner stored in Chroma metadata.
        Surfaces in SimilarTicket.resolution_summary previews.
        """
        parts = []
        if ticket.resolution_code:
            parts.append(ticket.resolution_code)
        if ticket.primary_cause:
            parts.append(ticket.primary_cause)
        if sop_applied:
            parts.append(f"via {sop_applied}")
        if ticket.resolution:
            # Truncate to 120 chars for the metadata preview
            parts.append(ticket.resolution[:120])
        return " — ".join(parts) if parts else "Resolved"

    # ------------------------------------------------------------------
    # Chat feedback indexing
    # ------------------------------------------------------------------

    async def index_chat_feedback(
        self,
        message_id: str,
        query_text: str,
        response_text: str,
        ticket_context: Optional[str] = None,
        comment: Optional[str] = None,
        engineer_id: Optional[str] = None,
    ) -> None:
        """
        Index a positively-rated chat exchange into Chroma as a training signal.

        Uses feedback_source="chat" metadata so future queries can retrieve
        only chat feedback (not ticket resolutions) via find_similar_with_filter.
        The resolved flag is set to False — these are not confirmed ticket
        resolutions, so they won't surface in find_similar_resolved() searches.
        """
        doc = f"Q: {query_text}\nA: {response_text}"
        if comment:
            doc += f"\nEngineer note: {comment}"

        metadata: dict = {
            "ticket_id":          ticket_context or f"chat:{message_id}",
            "title":              query_text[:120],
            "priority":           "medium",
            "category":           "chat_feedback",
            "resolution_summary": response_text[:300],
            "resolved":           False,
            "feedback_source":    "chat",
            "message_id":         message_id,
        }
        if engineer_id:
            metadata["engineer_id"] = engineer_id

        await self._engine.index_raw_doc(
            doc_id=f"chat:{message_id}",
            embedding_text=doc,
            metadata=metadata,
        )
        log.info(
            "Indexed positively-rated chat exchange as training signal "
            "(message_id=%s, ticket_context=%s)",
            message_id, ticket_context or "none",
        )


# ---------------------------------------------------------------------------
# Context retrieval helper
# ---------------------------------------------------------------------------

async def retrieve_chat_feedback_context(
    query: str,
    matching_engine: MatchingEngine,
    n_results: int = 3,
) -> str:
    """
    Query Chroma for the most relevant past positively-rated chat exchanges.

    Returns a formatted string ready to prepend to an assistant reply as
    "Related feedback from engineers" context.  Falls back to empty string
    on any error or when no relevant feedback exists yet.
    """
    try:
        results = await matching_engine.find_similar_with_filter(
            query=query,
            where={"feedback_source": {"$eq": "chat"}},
            n_results=n_results,
        )
        if not results:
            return ""

        lines = ["📌 **Related feedback from engineers on similar questions:**", ""]
        for r in results:
            doc = r.get("document", "")
            score = r.get("score", 0.0)
            if not doc or score < 0.3:
                continue
            # Parse Q: / A: lines back out for formatting
            q_part, a_part = "", ""
            for line in doc.split("\n"):
                if line.startswith("Q: "):
                    q_part = line[3:].strip()
                elif line.startswith("A: "):
                    a_part = line[3:100].strip()
            if q_part and a_part:
                lines.append(f"> **Q:** {q_part[:80]}")
                lines.append(f"> **A:** {a_part}{'…' if len(a_part) >= 97 else ''}")
                lines.append("")

        return "\n".join(lines).strip() if len(lines) > 2 else ""
    except Exception as exc:
        log.debug("retrieve_chat_feedback_context failed: %s", exc)
        return ""
