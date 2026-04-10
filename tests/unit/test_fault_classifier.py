"""
Unit tests for FaultClassifier.

Both the Anthropic client and MatchingEngine are fully mocked — no API
keys or running Chroma instance required.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.classifier.classifier import FaultClassifier, FaultClassifierError
from app.classifier.models import AffectedLayer, ClassificationResult
from app.models.recommendation import SimilarTicket
from app.models.telco_ticket import FaultType


# ---------------------------------------------------------------------------
# Helpers — build fakes
# ---------------------------------------------------------------------------

def _tool_block(
    fault_type: str = "packet_loss",
    affected_layer: str = "transport",
    confidence_score: float = 0.88,
    reasoning: str = "Elevated drop rate with BGP flap indicates transport-layer issue.",
) -> SimpleNamespace:
    """Simulate a Claude tool_use content block."""
    block = SimpleNamespace()
    block.type = "tool_use"
    block.input = {
        "fault_type":       fault_type,
        "affected_layer":   affected_layer,
        "confidence_score": confidence_score,
        "reasoning":        reasoning,
    }
    return block


def _claude_response(*blocks) -> SimpleNamespace:
    resp = SimpleNamespace()
    resp.content = list(blocks)
    return resp


def _make_client(tool_block_or_exc) -> MagicMock:
    """Mock anthropic.AsyncAnthropic that returns a canned response or raises."""
    client = MagicMock()
    if isinstance(tool_block_or_exc, Exception):
        client.messages.create = AsyncMock(side_effect=tool_block_or_exc)
    else:
        response = _claude_response(tool_block_or_exc)
        client.messages.create = AsyncMock(return_value=response)
    return client


def _make_engine(similar_ids: list[str] | None = None) -> MagicMock:
    engine = MagicMock()
    tickets = [
        SimilarTicket(ticket_id=tid, title=f"Ticket {tid}", score=0.9)
        for tid in (similar_ids or [])
    ]
    engine.find_similar_resolved = AsyncMock(return_value=tickets)
    return engine


def _make_classifier(
    fault_type: str = "packet_loss",
    affected_layer: str = "transport",
    confidence_score: float = 0.88,
    similar_ids: list[str] | None = None,
    client_exc: Exception | None = None,
) -> FaultClassifier:
    if client_exc:
        client = _make_client(client_exc)
    else:
        client = _make_client(_tool_block(fault_type, affected_layer, confidence_score))
    engine = _make_engine(similar_ids or [])
    return FaultClassifier(client=client, matching_engine=engine, model="claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Tests — ClassificationResult structure
# ---------------------------------------------------------------------------

class TestFaultClassifierResult:

    @pytest.mark.asyncio
    async def test_returns_classification_result(self):
        clf = _make_classifier()
        result = await clf.classify("High packet loss on RTR-LON-CORE-03")
        assert isinstance(result, ClassificationResult)

    @pytest.mark.asyncio
    async def test_fault_type_parsed_correctly(self):
        clf = _make_classifier(fault_type="signal_loss")
        result = await clf.classify("RSSI dropped to -115 dBm on BS-MUM-042")
        assert result.fault_type == FaultType.SIGNAL_LOSS

    @pytest.mark.asyncio
    async def test_affected_layer_physical(self):
        clf = _make_classifier(affected_layer="physical")
        result = await clf.classify("Fibre cut on node NODE-ATL-01")
        assert result.affected_layer == AffectedLayer.PHYSICAL

    @pytest.mark.asyncio
    async def test_affected_layer_transport(self):
        clf = _make_classifier(affected_layer="transport")
        result = await clf.classify("BGP session flapping, 15% packet loss")
        assert result.affected_layer == AffectedLayer.TRANSPORT

    @pytest.mark.asyncio
    async def test_affected_layer_service(self):
        clf = _make_classifier(affected_layer="service", fault_type="configuration_error")
        result = await clf.classify("Misconfigured ACL blocking RADIUS authentication")
        assert result.affected_layer == AffectedLayer.SERVICE

    @pytest.mark.asyncio
    async def test_confidence_score_in_range(self):
        clf = _make_classifier(confidence_score=0.91)
        result = await clf.classify("test ticket")
        assert 0.0 <= result.confidence_score <= 1.0
        assert abs(result.confidence_score - 0.91) < 1e-6

    @pytest.mark.asyncio
    async def test_reasoning_propagated(self):
        clf = _make_classifier()
        result = await clf.classify("test ticket")
        assert len(result.reasoning) > 0

    @pytest.mark.asyncio
    async def test_model_name_in_result(self):
        clf = _make_classifier()
        result = await clf.classify("test")
        assert result.model == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_latency_ms_is_non_negative(self):
        clf = _make_classifier()
        result = await clf.classify("test")
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# Tests — similar ticket IDs
# ---------------------------------------------------------------------------

class TestFaultClassifierSimilarTickets:

    @pytest.mark.asyncio
    async def test_similar_ids_populated(self):
        clf = _make_classifier(similar_ids=["TKT-AAA", "TKT-BBB", "TKT-CCC"])
        result = await clf.classify("packet loss on backbone")
        assert result.similar_ticket_ids == ["TKT-AAA", "TKT-BBB", "TKT-CCC"]

    @pytest.mark.asyncio
    async def test_no_similar_tickets_returns_empty_list(self):
        clf = _make_classifier(similar_ids=[])
        result = await clf.classify("novel fault with no precedents")
        assert result.similar_ticket_ids == []

    @pytest.mark.asyncio
    async def test_similar_top_k_capped_at_3(self):
        client = _make_client(_tool_block())
        engine = _make_engine(["TKT-1", "TKT-2", "TKT-3"])
        # Request top_k=5 — should be capped to 3 internally
        clf = FaultClassifier(client=client, matching_engine=engine, similar_top_k=5)
        assert clf._similar_top_k == 3

    @pytest.mark.asyncio
    async def test_similarity_search_failure_degrades_gracefully(self):
        client = _make_client(_tool_block())
        engine = MagicMock()
        engine.find_similar_resolved = AsyncMock(side_effect=RuntimeError("Chroma down"))
        clf = FaultClassifier(client=client, matching_engine=engine)
        # Should not raise — similar_ticket_ids is [] instead
        result = await clf.classify("test ticket")
        assert result.similar_ticket_ids == []
        assert result.fault_type is not None  # classification still succeeds

    @pytest.mark.asyncio
    async def test_engine_called_with_ticket_text(self):
        client = _make_client(_tool_block())
        engine = _make_engine([])
        clf = FaultClassifier(client=client, matching_engine=engine)
        await clf.classify("fibre cut on segment B")
        engine.find_similar_resolved.assert_awaited_once_with(
            query="fibre cut on segment B", top_k=3
        )


# ---------------------------------------------------------------------------
# Tests — Claude API error handling
# ---------------------------------------------------------------------------

class TestFaultClassifierErrors:

    @pytest.mark.asyncio
    async def test_anthropic_api_error_raises_classifier_error(self):
        import anthropic as _anthropic
        exc = _anthropic.APIStatusError(
            "rate limited",
            response=MagicMock(status_code=429),
            body={},
        )
        clf = _make_classifier(client_exc=exc)
        with pytest.raises(FaultClassifierError, match="Anthropic API error"):
            await clf.classify("test")

    @pytest.mark.asyncio
    async def test_no_tool_block_raises_classifier_error(self):
        # Claude responds with a text block instead of tool_use
        text_block = SimpleNamespace()
        text_block.type = "text"
        text_block.text = "I cannot classify this."
        client = _make_client(text_block)  # _make_client accepts blocks too
        # Rebuild client to return text-only response
        client2 = MagicMock()
        client2.messages.create = AsyncMock(return_value=_claude_response(text_block))
        clf = FaultClassifier(client=client2, matching_engine=_make_engine([]))
        with pytest.raises(FaultClassifierError, match="did not call classify_fault"):
            await clf.classify("test")

    @pytest.mark.asyncio
    async def test_unknown_fault_type_falls_back_to_unknown(self):
        block = _tool_block(fault_type="fiber_break")  # not in enum
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine([]))
        result = await clf.classify("test")
        assert result.fault_type == FaultType.UNKNOWN

    @pytest.mark.asyncio
    async def test_unknown_layer_falls_back_to_service(self):
        block = _tool_block(affected_layer="network")  # not in enum
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine([]))
        result = await clf.classify("test")
        assert result.affected_layer == AffectedLayer.SERVICE

    @pytest.mark.asyncio
    async def test_confidence_score_clamped_above_1(self):
        block = _tool_block(confidence_score=1.5)
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine([]))
        result = await clf.classify("test")
        assert result.confidence_score == 1.0

    @pytest.mark.asyncio
    async def test_confidence_score_clamped_below_0(self):
        block = _tool_block(confidence_score=-0.5)
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine([]))
        result = await clf.classify("test")
        assert result.confidence_score == 0.0


# ---------------------------------------------------------------------------
# Tests — Claude API call shape
# ---------------------------------------------------------------------------

class TestFaultClassifierApiCall:

    @pytest.mark.asyncio
    async def test_messages_create_called_once(self):
        clf = _make_classifier()
        await clf.classify("test text")
        clf._client.messages.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_correct_model_sent_to_api(self):
        clf = _make_classifier()
        await clf.classify("test text")
        call_kwargs = clf._client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_tool_choice_forces_classify_fault(self):
        clf = _make_classifier()
        await clf.classify("test text")
        call_kwargs = clf._client.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"]["name"] == "classify_fault"

    @pytest.mark.asyncio
    async def test_ticket_text_appears_in_user_message(self):
        clf = _make_classifier()
        await clf.classify("very specific fault description XYZ")
        call_kwargs = clf._client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "very specific fault description XYZ" in user_content
