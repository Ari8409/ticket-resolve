"""
ResolutionAgent — LangChain tool-calling agent for telco ticket resolution.

Produces a DispatchDecision that includes:
  • dispatch_mode          (remote / on_site / hold / escalate)
  • recommended_steps      (ordered action list)
  • ranked_sops            (top 2–3 SOPs with confidence scores)
  • natural_language_summary (human-readable NOC engineer summary)
  • reasoning              (evidence-based explanation)

Inputs injected into the prompt:
  • TelcoTicketCreate           — the ticket being resolved
  • ClassificationResult | None — fault classifier output (fault_type + confidence)
  • CorrelationContext | None   — pre-assembled alarm, maintenance, remote-feasibility data
                                  including pre-ranked candidate SOPs and similar tickets
"""
from __future__ import annotations

import logging

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.classifier.models import ClassificationResult
from app.correlation.models import CorrelationContext, DispatchDecision, DispatchMode
from app.matching.engine import MatchingEngine
from app.models.telco_ticket import TelcoTicketCreate
from app.recommendation.chains import build_structuring_chain
from app.recommendation.output_parser import parse_agent_output
from app.recommendation.prompts import (
    SYSTEM_PROMPT,
    TELCO_CONTEXT_TEMPLATE,
    _fmt_candidate_sops,
    _fmt_classifier,
    _fmt_matched_tickets,
)
from app.recommendation.tools import build_agent_tools
from app.sop.retriever import SOPRetriever

log = logging.getLogger(__name__)

_DISPATCH_MODE_MAP: dict[str, DispatchMode] = {
    "remote":    DispatchMode.REMOTE,
    "on_site":   DispatchMode.ON_SITE,
    "on-site":   DispatchMode.ON_SITE,
    "hold":      DispatchMode.HOLD,
    "escalate":  DispatchMode.ESCALATE,
}


class ResolutionAgent:
    """
    Tool-calling LangChain agent that produces a DispatchDecision.

    The agent receives:
      - A pre-assembled CorrelationContext (alarm state, maintenance window, remote
        feasibility, candidate SOPs, similar tickets).
      - An optional ClassificationResult from the fault classifier.

    It uses five tools to reach a final recommendation, produces a ranked SOP list,
    and writes a natural-language summary for the NOC engineer.
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        sop_retriever: SOPRetriever,
        matching_engine: MatchingEngine,
    ) -> None:
        self._llm           = llm
        self._sop_retriever = sop_retriever
        self._matching      = matching_engine
        self._structuring   = build_structuring_chain(llm)

    def _build_executor(self, correlation_ctx: CorrelationContext | None) -> AgentExecutor:
        tools = build_agent_tools(
            sop_retriever=self._sop_retriever,
            matching_engine=self._matching,
            correlation_ctx=correlation_ctx,
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{ticket_context}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        agent = create_tool_calling_agent(self._llm, tools, prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=8,
            handle_parsing_errors=True,
            return_intermediate_steps=False,
        )

    def _build_context(
        self,
        ticket: TelcoTicketCreate,
        correlation_ctx: CorrelationContext | None,
        classifier_result: ClassificationResult | None,
    ) -> str:
        corr_block = (
            correlation_ctx.as_agent_context_str()
            if correlation_ctx
            else "(No pre-dispatch context available — use tools to gather information.)"
        )

        # Pre-fetched similar tickets and candidate SOPs from the correlation context
        similar_tickets = correlation_ctx.similar_tickets if correlation_ctx else []
        sop_matches     = correlation_ctx.sop_matches     if correlation_ctx else []

        return TELCO_CONTEXT_TEMPLATE.format(
            ticket_id=ticket.ticket_id,
            fault_type=ticket.fault_type.value,
            affected_node=ticket.affected_node,
            severity=ticket.severity.value.upper(),
            description=ticket.description[:800],
            sop_id=ticket.sop_id or "None",
            timestamp=ticket.timestamp.isoformat(),
            classifier_block=_fmt_classifier(classifier_result),
            matched_tickets_block=_fmt_matched_tickets(similar_tickets),
            candidate_sops_block=_fmt_candidate_sops(sop_matches),
            correlation_context=corr_block,
        )

    async def resolve(
        self,
        ticket: TelcoTicketCreate,
        ticket_id: str = "",
        correlation_ctx: CorrelationContext | None = None,
        classifier_result: ClassificationResult | None = None,
    ) -> DispatchDecision:
        """
        Run the agent and return a DispatchDecision.

        Parameters
        ----------
        ticket:
            The telco ticket to resolve.
        ticket_id:
            Persisted ticket ID (may differ from ticket.ticket_id if reassigned).
        correlation_ctx:
            Pre-assembled context from CorrelationEngine — alarm state, maintenance
            window, remote feasibility, candidate SOPs, similar tickets.
        classifier_result:
            Output of FaultClassifier.classify() for this ticket. When provided,
            the classifier's fault_type and confidence are injected into the prompt
            so the agent can leverage them without re-deriving from the description.
        """
        executor = self._build_executor(correlation_ctx)
        context  = self._build_context(ticket, correlation_ctx, classifier_result)

        try:
            raw = await executor.ainvoke({"ticket_context": context})
            output_text = raw.get("output", "")
        except Exception as exc:
            log.error("Agent execution failed for ticket %s: %s", ticket_id, exc, exc_info=True)
            output_text = ""

        result = parse_agent_output(output_text, ticket, ticket_id, correlation_ctx)

        # Fallback: if steps are missing, run the structuring chain
        if not result.recommended_steps and output_text:
            log.warning("Primary parse returned no steps; running structuring chain fallback")
            try:
                structured = await self._structuring.ainvoke({"agent_output": output_text})
                mode = _DISPATCH_MODE_MAP.get(
                    str(structured.get("dispatch_mode", "on_site")).lower(),
                    DispatchMode.ON_SITE,
                )
                result = DispatchDecision(
                    ticket_id=ticket_id,
                    dispatch_mode=mode,
                    confidence_score=float(structured.get("confidence_score", 0.5)),
                    recommended_steps=structured.get("recommended_steps", []),
                    reasoning=structured.get("reasoning", ""),
                    escalation_required=bool(structured.get("escalation_required", False)),
                    relevant_sops=structured.get("relevant_sops", []),
                    similar_ticket_ids=structured.get("similar_ticket_ids", []),
                    natural_language_summary=structured.get("natural_language_summary", ""),
                    ranked_sops=[],
                    alarm_check=correlation_ctx.alarm_check if correlation_ctx else None,
                    maintenance_check=correlation_ctx.maintenance_check if correlation_ctx else None,
                )
            except Exception as exc:
                log.error("Structuring chain also failed: %s", exc)

        return result
