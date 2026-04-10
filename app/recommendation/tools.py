"""
LangChain tools available to the ResolutionAgent.

Original tools (unchanged behaviour):
  sop_retrieval_tool      — retrieves relevant SOPs from Chroma
  ticket_similarity_tool  — retrieves similar historical tickets from Chroma

New pre-dispatch tools (require CorrelationContext injected at construction):
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
    # Original tools
    # ------------------------------------------------------------------

    @tool
    async def sop_retrieval_tool(query: str) -> str:
        """
        Retrieves Standard Operating Procedures (SOPs) relevant to a given query.
        Use this to find documented resolution procedures, compliance guidelines,
        or step-by-step instructions.
        Input: natural language description of the issue.
        Output: formatted SOP excerpts with titles and relevance scores.
        """
        matches = await sop_retriever.retrieve(query, top_k=3)
        if not matches:
            return "No relevant SOPs found."
        parts = []
        for m in matches:
            parts.append(f"## {m.title} (relevance: {m.score:.2f})\n{m.content[:800]}")
        return "\n\n---\n\n".join(parts)

    @tool
    async def ticket_similarity_tool(query: str) -> str:
        """
        Searches historical resolved tickets similar to the current issue.
        Use to find how analogous past tickets were resolved and whether
        they required truck dispatch or were fixed remotely.
        Input: description of the current problem.
        Output: list of similar past tickets with resolution summaries.
        """
        matches = await matching_engine.find_similar(query, top_k=5)
        if not matches:
            return "No similar historical tickets found."
        lines = []
        for m in matches:
            resolution = m.resolution_summary or "No resolution recorded"
            lines.append(
                f"- Ticket {m.ticket_id} (score {m.score:.2f}): {m.title}\n"
                f"  Resolution: {resolution}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # New pre-dispatch tools (use pre-assembled CorrelationContext)
    # ------------------------------------------------------------------

    @tool
    def alarm_check_tool(node_id: str) -> str:
        """
        Reports the current live alarm state for the specified network node.

        ALWAYS call this tool before recommending truck dispatch.
        If the alarm has already CLEARED, the fault has self-healed and
        no physical intervention is required.

        Input:  node identifier (e.g. "NODE-ATL-01", "BS-MUM-042").
        Output: alarm status (ACTIVE / CLEARED / NOT_FOUND) with timestamps.
        """
        if correlation_ctx is None:
            return "Alarm context not available for this ticket."

        result = correlation_ctx.alarm_check
        if not result.alarm_found:
            return f"No alarm record found for node '{node_id}' in NMS."

        lines = [
            f"Node:      {result.node}",
            f"Alarm ID:  {result.alarm_id}",
            f"Alarm Type:{result.alarm_type}",
            f"Severity:  {result.severity}",
            f"Status:    {result.status.value.upper() if result.status else 'UNKNOWN'}",
            f"Raised:    {result.raised_at.isoformat() if result.raised_at else 'unknown'}",
        ]
        if result.cleared_at:
            lines.append(f"Cleared:   {result.cleared_at.isoformat()}")
        lines.append("")
        lines.append(result.summary)
        if result.dispatch_blocked:
            lines.append(
                "\n⚠ DISPATCH RECOMMENDATION: HOLD — alarm is cleared. "
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
        is already on site — a second truck dispatch would be redundant and
        could create safety conflicts.

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
            f"⚠ NODE IN ACTIVE MAINTENANCE",
            f"Maintenance: {w.title}",
            f"Type:        {w.maintenance_type.value}",
            f"Ref:         {w.external_ref or 'N/A'}",
            f"Window:      {w.start_time.isoformat()} → {w.end_time.isoformat()}",
            f"Contact:     {w.contact or 'NOC'}",
            f"Nodes:       {', '.join(w.affected_nodes[:10])}",
            "",
            result.summary,
            "\n⚠ DISPATCH RECOMMENDATION: HOLD — maintenance team is responsible. "
            "Coordinate with the maintenance contact listed above.",
        ]
        return "\n".join(lines)

    @tool
    def remote_feasibility_tool(fault_description: str) -> str:
        """
        Provides a structured assessment of whether the current fault can
        realistically be resolved remotely (via NMS/CLI/SSH) versus requiring
        physical truck dispatch.

        Call this tool AFTER alarm_check_tool and maintenance_check_tool to
        determine the appropriate dispatch recommendation.

        Input:  description of the fault and affected node.
        Output: feasibility verdict with supporting evidence and confidence score.
        """
        if correlation_ctx is None:
            return "Remote feasibility context not available."

        rf = correlation_ctx.remote_feasibility
        if rf is None:
            return "Remote feasibility assessment not computed for this ticket."

        verdict = "REMOTE RESOLUTION LIKELY" if rf.feasible else "ON-SITE DISPATCH LIKELY REQUIRED"
        lines = [
            f"REMOTE FEASIBILITY ASSESSMENT",
            f"Verdict:    {verdict}",
            f"Confidence: {rf.confidence:.0%}",
        ]
        if rf.supporting_evidence:
            lines.append("\nSupporting evidence:")
            lines.extend(f"  ✓ {e}" for e in rf.supporting_evidence)
        if rf.blocking_factors:
            lines.append("\nBlocking factors:")
            lines.extend(f"  ✗ {b}" for b in rf.blocking_factors)
        lines.append(
            f"\nRecommendation: set dispatch_mode to "
            f"'{'remote' if rf.feasible else 'on_site'}' unless other evidence overrides."
        )
        return "\n".join(lines)

    return [
        sop_retrieval_tool,
        ticket_similarity_tool,
        alarm_check_tool,
        maintenance_check_tool,
        remote_feasibility_tool,
    ]
