"""
FaultClassifier — Claude-powered fault type and OSI-layer classifier.

Architecture (two-phase)
------------------------

Phase 1 — Parallel data fetch from four independent sources
(all four I/O calls run concurrently via asyncio.gather)

  text ──┬── source 1: MatchingEngine.find_similar_resolved()   Chroma tickets (resolved=True)
         ├── source 2: SOPRetriever.retrieve()                  Chroma SOPs collection
         ├── source 3: MatchingEngine.find_similar()            Chroma tickets (all statuses)
         └── source 4: MatchingEngine.find_similar_high_priority() Chroma tickets (critical/high)

Phase 2 — Claude API call with enriched context
The fetched context is serialised into a structured <context> block and
injected into the user message.  Claude classifies more accurately because
it can see resolved precedents, relevant SOPs, and severity escalation
history alongside the raw ticket text.

  text + context block ──► Anthropic Messages API (tool_choice: classify_fault)
                                ↓
                          tool_input {fault_type, affected_layer,
                                      confidence_score, reasoning}

Result assembly
---------------
  ClassificationResult {
    fault_type, affected_layer, confidence_score, reasoning,
    similar_ticket_ids  ← source 1 (resolved precedents, top-3)
    relevant_sops       ← source 2 (SOP titles)
    model, latency_ms   ← measured across both phases
  }

Failure handling
----------------
- Any individual fetch failure (Chroma down, network error) is caught,
  logged as a warning, and replaced with an empty list.  Classification
  always proceeds — degraded context is better than a 500 error.
- If the Claude API call fails, FaultClassifierError is raised.
- Out-of-enum tool response values fall back to safe defaults (logged).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.classifier.models import AffectedLayer, ClassificationResult
from app.classifier.prompts import CLASSIFY_TOOL, SYSTEM_PROMPT, TOOL_CHOICE
from app.matching.engine import MatchingEngine
from app.models.recommendation import SimilarTicket, SOPMatch
from app.models.telco_ticket import FaultType
from app.sop.retriever import SOPRetriever

log = logging.getLogger(__name__)


class FaultClassifierError(Exception):
    """Raised when Claude returns an unusable response."""


# ---------------------------------------------------------------------------
# Internal context bundle — populated by the parallel fetch phase
# ---------------------------------------------------------------------------

@dataclass
class _FetchedContext:
    """Holds results from all four parallel data sources."""
    resolved:       list[SimilarTicket] = field(default_factory=list)  # source 1
    sops:           list[SOPMatch]      = field(default_factory=list)  # source 2
    all_incidents:  list[SimilarTicket] = field(default_factory=list)  # source 3
    high_priority:  list[SimilarTicket] = field(default_factory=list)  # source 4


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class FaultClassifier:
    """
    Classifies raw ticket text into FaultType + AffectedLayer using
    Claude's tool-use API, pre-seeding the prompt with context fetched
    in parallel from four data sources.

    Parameters
    ----------
    client:
        Initialised ``anthropic.AsyncAnthropic`` client.
    matching_engine:
        ``MatchingEngine`` whose Chroma collection is seeded with resolved
        historical tickets (``resolved=True``).
    sop_retriever:
        ``SOPRetriever`` backed by the Chroma SOPs collection.
    model:
        Anthropic model ID.  Defaults to ``claude-sonnet-4-6``.
    similar_top_k:
        Resolved tickets to surface in the result.  Capped at 3 (spec).
    max_tokens:
        Token budget for Claude's response — 512 is comfortable for the
        tool call even with a large context block in the prompt.
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        matching_engine: MatchingEngine,
        sop_retriever: SOPRetriever,
        model: str = "claude-sonnet-4-6",
        similar_top_k: int = 3,
        max_tokens: int = 512,
    ) -> None:
        self._client        = client
        self._engine        = matching_engine
        self._sop_retriever = sop_retriever
        self._model         = model
        self._similar_top_k = min(similar_top_k, 3)  # cap at 3 per spec
        self._max_tokens    = max_tokens

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def classify(self, text: str) -> ClassificationResult:
        """
        Classify ``text`` and return a ``ClassificationResult``.

        Phase 1 — four parallel fetches (Chroma + SOP store).
        Phase 2 — Claude API call with enriched context block.

        Raises
        ------
        FaultClassifierError
            If Claude returns an unparseable or structurally invalid response.
        """
        t0 = time.monotonic()

        # ── Phase 1: parallel data fetch ──────────────────────────────
        ctx = await self._fetch_context(text)

        # ── Phase 2: Claude with enriched context ─────────────────────
        tool_input = await self._call_claude(text, ctx)

        latency_ms = int((time.monotonic() - t0) * 1000)

        fault_type     = self._parse_fault_type(tool_input)
        affected_layer = self._parse_affected_layer(tool_input)
        confidence     = self._parse_confidence(tool_input)
        reasoning      = str(tool_input.get("reasoning", "")).strip()

        similar_ids = [m.ticket_id for m in ctx.resolved[: self._similar_top_k]]
        sop_titles  = [m.title for m in ctx.sops]

        log.info(
            "Classified — fault=%s layer=%s confidence=%.2f "
            "similar=%s sops=%s latency=%dms",
            fault_type.value, affected_layer.value, confidence,
            similar_ids, sop_titles, latency_ms,
        )

        return ClassificationResult(
            fault_type=fault_type,
            affected_layer=affected_layer,
            confidence_score=confidence,
            reasoning=reasoning,
            similar_ticket_ids=similar_ids,
            relevant_sops=sop_titles,
            model=self._model,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Phase 1 — parallel fetch
    # ------------------------------------------------------------------

    async def _fetch_context(self, text: str) -> _FetchedContext:
        """
        Run all four data-source queries concurrently.

        Each coroutine is wrapped in ``_safe_fetch`` so a single source
        failure never aborts the others.

        Sources
        -------
        1. find_similar_resolved    — Chroma tickets, resolved=True
        2. sop_retriever.retrieve   — Chroma SOPs collection
        3. find_similar             — Chroma tickets, all statuses
        4. find_similar_high_priority — Chroma tickets, critical/high priority
        """
        resolved, sops, all_incidents, high_priority = await asyncio.gather(
            self._safe_fetch(
                "resolved tickets",
                self._engine.find_similar_resolved(text, top_k=self._similar_top_k),
            ),
            self._safe_fetch(
                "SOPs",
                self._sop_retriever.retrieve(text, top_k=3),
            ),
            self._safe_fetch(
                "all incidents",
                self._engine.find_similar(text, top_k=5),
            ),
            self._safe_fetch(
                "high-priority precedents",
                self._engine.find_similar_high_priority(text, top_k=3),
            ),
        )
        return _FetchedContext(
            resolved=resolved,
            sops=sops,
            all_incidents=all_incidents,
            high_priority=high_priority,
        )

    @staticmethod
    async def _safe_fetch(label: str, coro) -> list:
        """Await ``coro`` and return its result; return [] on any exception."""
        try:
            return await coro
        except Exception as exc:
            log.warning("Fetch '%s' failed — using empty list: %s", label, exc)
            return []

    # ------------------------------------------------------------------
    # Phase 2 — Claude call
    # ------------------------------------------------------------------

    async def _call_claude(self, text: str, ctx: _FetchedContext) -> dict[str, Any]:
        """
        Call the Anthropic Messages API with ``classify_fault`` tool forced.

        The pre-fetched context is serialised into an XML-style block and
        appended to the user message so Claude can reference resolved
        precedents, SOPs, and severity history when deciding the label.
        """
        user_message = (
            f"Classify the following network fault ticket:\n\n"
            f"<ticket>\n{text.strip()}\n</ticket>\n\n"
            f"{self._build_context_block(ctx)}"
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                tools=[CLASSIFY_TOOL],
                tool_choice=TOOL_CHOICE,
                messages=[{"role": "user", "content": user_message}],
            )
        except anthropic.APIError as exc:
            raise FaultClassifierError(f"Anthropic API error: {exc}") from exc

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if tool_block is None:
            raise FaultClassifierError(
                f"Claude did not call classify_fault. "
                f"Response content: {response.content!r}"
            )
        return tool_block.input  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Context block formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context_block(ctx: _FetchedContext) -> str:
        """
        Serialise the four-source fetch results into a structured text block
        for injection into the Claude user message.

        Only non-empty sources are included.  If all four fetches returned
        empty lists the block is omitted entirely.
        """
        parts: list[str] = []

        if ctx.resolved:
            lines = ["[Source 1 — Resolved Precedents]"]
            for m in ctx.resolved:
                summary = f" → {m.resolution_summary}" if m.resolution_summary else ""
                lines.append(f"  • {m.ticket_id} (similarity {m.score:.2f}) — {m.title}{summary}")
            parts.append("\n".join(lines))

        if ctx.sops:
            lines = ["[Source 2 — Relevant SOPs]"]
            for m in ctx.sops:
                snippet = m.content[:200].replace("\n", " ")
                lines.append(f"  • {m.title} (relevance {m.score:.2f}) — {snippet}…")
            parts.append("\n".join(lines))

        if ctx.all_incidents:
            lines = ["[Source 3 — Recent Similar Incidents]"]
            for m in ctx.all_incidents:
                lines.append(f"  • {m.ticket_id} (similarity {m.score:.2f}) — {m.title}")
            parts.append("\n".join(lines))

        if ctx.high_priority:
            lines = ["[Source 4 — Critical/High Escalation Precedents]"]
            for m in ctx.high_priority:
                summary = f" → {m.resolution_summary}" if m.resolution_summary else ""
                lines.append(
                    f"  • {m.ticket_id} (similarity {m.score:.2f}) — {m.title}{summary}"
                )
            parts.append("\n".join(lines))

        if not parts:
            return ""

        header = "=== PRE-FETCHED CONTEXT (4 sources, fetched in parallel) ==="
        footer = "Use this context to improve the accuracy of your classification."
        return "\n\n".join([header] + parts + [footer])

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_fault_type(self, tool_input: dict[str, Any]) -> FaultType:
        raw = str(tool_input.get("fault_type", "unknown")).strip().lower()
        try:
            return FaultType(raw)
        except ValueError:
            log.warning("Unknown fault_type=%r from Claude; defaulting to unknown", raw)
            return FaultType.UNKNOWN

    def _parse_affected_layer(self, tool_input: dict[str, Any]) -> AffectedLayer:
        raw = str(tool_input.get("affected_layer", "service")).strip().lower()
        try:
            return AffectedLayer(raw)
        except ValueError:
            log.warning("Unknown affected_layer=%r from Claude; defaulting to service", raw)
            return AffectedLayer.SERVICE

    def _parse_confidence(self, tool_input: dict[str, Any]) -> float:
        try:
            return max(0.0, min(1.0, float(tool_input.get("confidence_score", 0.5))))
        except (TypeError, ValueError):
            log.warning("Non-numeric confidence_score from Claude; defaulting to 0.5")
            return 0.5
