"""
LangChain tools available to the ResolutionAgent.

Tools:
  sop_retrieval_tool      — retrieves SOPs ranked by confidence score (top 3)
  ticket_similarity_tool  — retrieves similar historical tickets from Chroma
  alarm_check_tool        — reports live alarm state for the affected node
  maintenance_check_tool  — reports active planned maintenance for the node
  remote_feasibility_tool — summarises whether remote resolution is viable
"""
from __future__ import annotations

from langchain_core.tools import tool

from app.correlation.models import CorrelationContext
from app.matching.engine import MatchingEngine
from app.sop.retriever import SOPRetriever


def build_agent_tools(
    sop_retriever: SOPRetriever,
    matching_engine: MatchingEngine,
    correlation_ctx: CorrelationContext | None = None,
) -> list:

    # ------------------------------------------------------------------
    # RESOLUTION RESEARCH TOOLS
    # ------------------------------------------------------------------

    @tool
    async def sop_retrieval_tool(query: str) -> str:
        """
        Retrieves Standard Operating Procedures (SOPs) ranked by relevance confidence.

        Returns the top 3 SOPs scored by cosine similarity to the query.
        Each result includes: SOP ID, title, confidence score (0.0–1.0), and a
        content excerpt. Use the confidence scores to populate the ranked_sops
        field in your final output.

        Input:  natural language description of the fault or alarm name.
        Output: ranked list of SOPs with confidence scores and content excerpts.
        """
        matches = await sop_retriever.retrieve(query, top_k=3)
        if not matches:
            return "No relevant SOPs found for this query."

        parts = []
        for rank, m in enumerate(matches, 1):
            # Cosine distance from Chroma is in [0, 2]; convert to a [0, 1] confidence
            # The retriever already returns score as similarity (higher = better)
            content_preview = m.content[:600].strip()
            parts.append(
                f"RANK {rank} — [{m.sop_id}] {m.title}\n"
                f"Confidence: {m.score:.3f}\n"
                f"---\n"
                f"{content_preview}\n"
                f"[end of excerpt]"
            )

        header = (
            f"Retrieved {len(matches)} SOP(s) ranked by relevance confidence "
            f"(highest confidence = most relevant):\n\n"
        )
        return header + "\n\n" + ("=" * 60 + "\n\n").join(parts)

    @tool
    async def ticket_similarity_tool(query: str) -> str:
        """
        Searches historical resolved tickets similar to the current issue.

        Use to find how analogous past tickets were resolved and whether they
        required truck dispatch or were fixed remotely.

        Input:  description of the current problem.
        Output: list of similar past tickets with similarity scores and resolution summaries.
        """
        matches = await matching_engine.find_similar(query, top_k=5)
        if not matches:
            return "No similar historical tickets found."

        lines = [f"Found {len(matches)} similar past ticket(s):\n"]
        for m in matches:
            resolution = m.resolution_summary or "No resolution recorded"
            lines.append(
                f"  [{m.ticket_id}] similarity={m.score:.3f} — {m.title}\n"
                f"  Resolution: {resolution}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # PRE-DISPATCH TOOLS (read from pre-assembled CorrelationContext)
    # ------------------------------------------------------------------

    @tool
    def alarm_check_tool(node_id: str) -> str:
        """
        Reports the current live alarm state for the specified network node.

        ALWAYS call this tool before recommending truck dispatch.
        If the alarm has already CLEARED, the fault has self-healed and
        no physical intervention is required.

        Input:  node identifier (e.g. "LTE_ENB_780321", "NR_GNB_1039321").
        Output: alarm status (ACTIVE / CLEARED / NOT_FOUND) with timestamps.
        """
        if correlation_ctx is None:
            return "Alarm context not available for this ticket."

        result = correlation_ctx.alarm_check
        if not result.alarm_found:
            return f"No alarm record found for node '{node_id}' in NMS."

        lines = [
            f"Node:       {result.node}",
            f"Alarm ID:   {result.alarm_id}",
            f"Alarm Type: {result.alarm_type}",
            f"Severity:   {result.severity}",
            f"Status:     {result.status.value.upper() if result.status else 'UNKNOWN'}",
            f"Raised:     {result.raised_at.isoformat() if result.raised_at else 'unknown'}",
        ]
        if result.cleared_at:
            lines.append(f"Cleared:    {result.cleared_at.isoformat()}")
        lines.append("")
        lines.append(result.summary)
        if result.dispatch_blocked:
            lines.append(
                "\nDISPATCH RECOMMENDATION: HOLD — alarm is cleared. "
                "No truck roll required. Close ticket if alarm stays clear for 30 min."
            )
        return "\n".join(lines)

    @tool
    def maintenance_check_tool(node_id: str) -> str:
        """
        Checks whether the specified network node is currently under a
        planned maintenance window.

        ALWAYS call this tool before recommending truck dispatch.
        If the node is in an active maintenance window, the maintenance team
        is already on site — a second dispatch would be redundant and unsafe.

        Input:  node identifier.
        Output: maintenance window details or confirmation of no active window.
        """
        if correlation_ctx is None:
            return "Maintenance context not available for this ticket."

        result = correlation_ctx.maintenance_check
        if not result.in_maintenance:
            return f"No active planned maintenance window found for node '{node_id}'."

        w = result.window
        lines = [
            "NODE IN ACTIVE MAINTENANCE WINDOW",
            f"Title:    {w.title}",
            f"Type:     {w.maintenance_type.value}",
            f"Ref:      {w.external_ref or 'N/A'}",
            f"Window:   {w.start_time.isoformat()} → {w.end_time.isoformat()}",
            f"Contact:  {w.contact or 'NOC'}",
            f"Nodes:    {', '.join(w.affected_nodes[:10])}",
            "",
            result.summary,
            "\nDISPATCH RECOMMENDATION: HOLD — maintenance team is responsible. "
            "Coordinate with the maintenance contact listed above.",
        ]
        return "\n".join(lines)

    @tool
    def remote_feasibility_tool(fault_description: str) -> str:
        """
        Provides a structured assessment of whether the current fault can be
        resolved remotely (via NMS/CLI/SSH) versus requiring physical truck dispatch.

        Call this AFTER alarm_check_tool and maintenance_check_tool to determine
        the appropriate dispatch recommendation.

        Input:  description of the fault and affected node.
        Output: feasibility verdict, confidence score, supporting evidence, blocking factors.
        """
        if correlation_ctx is None:
            return "Remote feasibility context not available."

        rf = correlation_ctx.remote_feasibility
        if rf is None:
            return "Remote feasibility assessment not computed for this ticket."

        verdict = "REMOTE RESOLUTION LIKELY" if rf.feasible else "ON-SITE DISPATCH LIKELY REQUIRED"
        lines = [
            "REMOTE FEASIBILITY ASSESSMENT",
            f"Verdict:    {verdict}",
            f"Confidence: {rf.confidence:.0%}",
        ]
        if rf.supporting_evidence:
            lines.append("\nSupporting evidence:")
            lines.extend(f"  + {e}" for e in rf.supporting_evidence)
        if rf.blocking_factors:
            lines.append("\nBlocking factors:")
            lines.extend(f"  - {b}" for b in rf.blocking_factors)
        dispatch_str = "remote" if rf.feasible else "on_site"
        lines.append(
            f"\nRecommendation: set dispatch_mode = '{dispatch_str}' "
            f"unless other evidence overrides."
        )
        return "\n".join(lines)

    return [
        sop_retrieval_tool,
        ticket_similarity_tool,
        alarm_check_tool,
        maintenance_check_tool,
        remote_feasibility_tool,
    ]
