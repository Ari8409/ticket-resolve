"""
FaultClassifier — Claude-powered fault type and OSI-layer classifier.

Architecture
------------
classify() runs two tasks concurrently via asyncio.gather():

  ┌─────────────────────────────────┐   ┌──────────────────────────────────┐
  │  Anthropic Messages API         │   │  MatchingEngine                  │
  │  (claude-sonnet-4-6)            │   │  find_similar_resolved(text, k=3)│
  │                                 │   │  → Chroma cosine similarity      │
  │  Tool: classify_fault           │   │  → top-3 resolved ticket IDs     │
  │  → fault_type                   │   │                                  │
  │  → affected_layer               │   │                                  │
  │  → confidence_score             │   │                                  │
  │  → reasoning                    │   │                                  │
  └─────────────────────────────────┘   └──────────────────────────────────┘
                            ↓ merged into ↓
                       ClassificationResult

Failure handling
----------------
- If the Claude call fails, FaultClassifierError is raised (caller decides retry).
- If the similarity search fails (Chroma unavailable), similar_ticket_ids is []
  and a warning is logged — classification still succeeds.
- Malformed tool responses (missing keys, wrong enum values) raise
  FaultClassifierError with the raw payload for debugging.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import anthropic

from app.classifier.models import AffectedLayer, ClassificationResult
from app.classifier.prompts import CLASSIFY_TOOL, SYSTEM_PROMPT, TOOL_CHOICE
from app.matching.engine import MatchingEngine
from app.models.telco_ticket import FaultType

log = logging.getLogger(__name__)


class FaultClassifierError(Exception):
    """Raised when Claude returns an unusable response."""


class FaultClassifier:
    """
    Classifies a ticket's raw text into a FaultType + AffectedLayer using
    Claude's tool-use API, then enriches the result with up to 3 similar
    resolved ticket IDs retrieved from Chroma.

    Parameters
    ----------
    client:
        An initialised ``anthropic.AsyncAnthropic`` client.
    matching_engine:
        A ``MatchingEngine`` whose Chroma collection has been seeded with
        resolved historical tickets (``resolved=True``).
    model:
        Anthropic model ID.  Defaults to ``claude-sonnet-4-6``.
    similar_top_k:
        Number of resolved similar tickets to include.  Max 3 (per spec).
    max_tokens:
        Token budget for the Claude response.  Classification is compact
        so 256 is more than sufficient.
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        matching_engine: MatchingEngine,
        model: str = "claude-sonnet-4-6",
        similar_top_k: int = 3,
        max_tokens: int = 256,
    ) -> None:
        self._client         = client
        self._engine         = matching_engine
        self._model          = model
        self._similar_top_k  = min(similar_top_k, 3)  # cap at 3 per spec
        self._max_tokens     = max_tokens

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def classify(self, text: str) -> ClassificationResult:
        """
        Classify ``text`` and return a ``ClassificationResult``.

        The Claude API call and Chroma similarity search run concurrently.
        Total latency ≈ max(claude_latency, chroma_latency).

        Raises
        ------
        FaultClassifierError
            If Claude returns an unparseable or structurally invalid response.
        """
        t0 = time.monotonic()

        # Run Claude classification + vector similarity search in parallel
        claude_task     = self._call_claude(text)
        similarity_task = self._find_similar_ids(text)

        (tool_input, similar_ids) = await asyncio.gather(
            claude_task,
            similarity_task,
            return_exceptions=False,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Parse and validate the tool response
        fault_type     = self._parse_fault_type(tool_input)
        affected_layer = self._parse_affected_layer(tool_input)
        confidence     = self._parse_confidence(tool_input)
        reasoning      = str(tool_input.get("reasoning", "")).strip()

        log.info(
            "Classified ticket — fault=%s layer=%s confidence=%.2f similar=%s latency=%dms",
            fault_type.value, affected_layer.value, confidence,
            similar_ids, latency_ms,
        )

        return ClassificationResult(
            fault_type=fault_type,
            affected_layer=affected_layer,
            confidence_score=confidence,
            reasoning=reasoning,
            similar_ticket_ids=similar_ids,
            model=self._model,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Internal — Claude call
    # ------------------------------------------------------------------

    async def _call_claude(self, text: str) -> dict[str, Any]:
        """
        Call the Anthropic Messages API with tool_choice forced to
        ``classify_fault``.  Returns the tool's ``input`` dict.
        """
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                tools=[CLASSIFY_TOOL],
                tool_choice=TOOL_CHOICE,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Classify the following network fault ticket:\n\n"
                            f"<ticket>\n{text.strip()}\n</ticket>"
                        ),
                    }
                ],
            )
        except anthropic.APIError as exc:
            raise FaultClassifierError(f"Anthropic API error: {exc}") from exc

        # Extract the tool_use block
        tool_block = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if tool_block is None:
            raise FaultClassifierError(
                f"Claude did not call classify_fault. "
                f"Response content: {response.content!r}"
            )

        return tool_block.input  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Internal — similarity search
    # ------------------------------------------------------------------

    async def _find_similar_ids(self, text: str) -> list[str]:
        """
        Query Chroma for the top-k resolved tickets most similar to ``text``.
        Returns a list of ticket IDs (up to self._similar_top_k).

        Failures are caught and logged — the classifier degrades gracefully
        to an empty list rather than failing the whole request.
        """
        try:
            matches = await self._engine.find_similar_resolved(
                query=text,
                top_k=self._similar_top_k,
            )
            return [m.ticket_id for m in matches]
        except Exception as exc:
            log.warning(
                "Similarity search failed — similar_ticket_ids will be empty: %s", exc,
            )
            return []

    # ------------------------------------------------------------------
    # Internal — parsing helpers
    # ------------------------------------------------------------------

    def _parse_fault_type(self, tool_input: dict[str, Any]) -> FaultType:
        raw = str(tool_input.get("fault_type", "unknown")).strip().lower()
        try:
            return FaultType(raw)
        except ValueError:
            log.warning("Claude returned unknown fault_type=%r; defaulting to unknown", raw)
            return FaultType.UNKNOWN

    def _parse_affected_layer(self, tool_input: dict[str, Any]) -> AffectedLayer:
        raw = str(tool_input.get("affected_layer", "service")).strip().lower()
        try:
            return AffectedLayer(raw)
        except ValueError:
            log.warning("Claude returned unknown affected_layer=%r; defaulting to service", raw)
            return AffectedLayer.SERVICE

    def _parse_confidence(self, tool_input: dict[str, Any]) -> float:
        try:
            score = float(tool_input.get("confidence_score", 0.5))
            return max(0.0, min(1.0, score))  # clamp to [0, 1]
        except (TypeError, ValueError):
            log.warning("Claude returned non-numeric confidence_score; defaulting to 0.5")
            return 0.5
