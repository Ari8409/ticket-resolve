"""
Unit tests for FaultClassifier.

Anthropic client, MatchingEngine, and SOPRetriever are all fully mocked —
no API keys, no running Chroma instance required.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.classifier.classifier import FaultClassifier, FaultClassifierError, _FetchedContext
from app.classifier.models import AffectedLayer, ClassificationResult
from app.models.recommendation import SimilarTicket, SOPMatch
from app.models.telco_ticket import FaultType


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _tool_block(
    fault_type: str = "packet_loss",
    affected_layer: str = "transport",
    confidence_score: float = 0.88,
    reasoning: str = "BGP flap with 15% packet drop is a classic transport-layer issue.",
) -> SimpleNamespace:
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


def _similar(ticket_id: str, score: float = 0.90, summary: str | None = "Fixed.") -> SimilarTicket:
    return SimilarTicket(ticket_id=ticket_id, title=f"Ticket {ticket_id}",
                         score=score, resolution_summary=summary)


def _sop(title: str = "SOP-RF-007", score: float = 0.85) -> SOPMatch:
    return SOPMatch(sop_id="sop-1", title=title,
                    content="Check antenna alignment and feeder integrity.",
                    score=score)


def _make_client(tool_block_or_exc=None) -> MagicMock:
    client = MagicMock()
    if isinstance(tool_block_or_exc, Exception):
        client.messages.create = AsyncMock(side_effect=tool_block_or_exc)
    else:
        block = tool_block_or_exc or _tool_block()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
    return client


def _make_engine(
    resolved: list[SimilarTicket] | None = None,
    all_similar: list[SimilarTicket] | None = None,
    high_priority: list[SimilarTicket] | None = None,
) -> MagicMock:
    engine = MagicMock()
    engine.find_similar_resolved      = AsyncMock(return_value=resolved or [])
    engine.find_similar               = AsyncMock(return_value=all_similar or [])
    engine.find_similar_high_priority = AsyncMock(return_value=high_priority or [])
    return engine


def _make_sop_retriever(sops: list[SOPMatch] | None = None) -> MagicMock:
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=sops or [])
    return retriever


def _make_classifier(
    fault_type: str = "packet_loss",
    affected_layer: str = "transport",
    confidence_score: float = 0.88,
    resolved: list[SimilarTicket] | None = None,
    sops: list[SOPMatch] | None = None,
    all_similar: list[SimilarTicket] | None = None,
    high_priority: list[SimilarTicket] | None = None,
    client_exc: Exception | None = None,
) -> FaultClassifier:
    client = _make_client(client_exc or _tool_block(fault_type, affected_layer, confidence_score))
    return FaultClassifier(
        client=client,
        matching_engine=_make_engine(resolved, all_similar, high_priority),
        sop_retriever=_make_sop_retriever(sops),
        model="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# Tests — ClassificationResult structure
# ---------------------------------------------------------------------------

class TestFaultClassifierResult:

    @pytest.mark.asyncio
    async def test_returns_classification_result(self):
        result = await _make_classifier().classify("BGP flapping on core router")
        assert isinstance(result, ClassificationResult)

    @pytest.mark.asyncio
    async def test_fault_type_parsed(self):
        result = await _make_classifier(fault_type="signal_loss").classify("low RSSI")
        assert result.fault_type == FaultType.SIGNAL_LOSS

    @pytest.mark.asyncio
    async def test_affected_layer_physical(self):
        result = await _make_classifier(affected_layer="physical").classify("fibre cut")
        assert result.affected_layer == AffectedLayer.PHYSICAL

    @pytest.mark.asyncio
    async def test_affected_layer_transport(self):
        result = await _make_classifier(affected_layer="transport").classify("packet loss")
        assert result.affected_layer == AffectedLayer.TRANSPORT

    @pytest.mark.asyncio
    async def test_affected_layer_service(self):
        clf = _make_classifier(affected_layer="service", fault_type="configuration_error")
        result = await clf.classify("ACL misconfiguration")
        assert result.affected_layer == AffectedLayer.SERVICE

    @pytest.mark.asyncio
    async def test_confidence_in_range(self):
        result = await _make_classifier(confidence_score=0.91).classify("test")
        assert abs(result.confidence_score - 0.91) < 1e-6

    @pytest.mark.asyncio
    async def test_model_name_propagated(self):
        result = await _make_classifier().classify("test")
        assert result.model == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_latency_ms_non_negative(self):
        result = await _make_classifier().classify("test")
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# Tests — similar ticket IDs (source 1)
# ---------------------------------------------------------------------------

class TestSimilarTicketIds:

    @pytest.mark.asyncio
    async def test_similar_ids_from_resolved_source(self):
        resolved = [_similar("TKT-A"), _similar("TKT-B"), _similar("TKT-C")]
        result = await _make_classifier(resolved=resolved).classify("packet loss")
        assert result.similar_ticket_ids == ["TKT-A", "TKT-B", "TKT-C"]

    @pytest.mark.asyncio
    async def test_no_resolved_tickets_gives_empty_list(self):
        result = await _make_classifier(resolved=[]).classify("test")
        assert result.similar_ticket_ids == []

    @pytest.mark.asyncio
    async def test_similar_top_k_capped_at_3(self):
        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=_make_engine(),
            sop_retriever=_make_sop_retriever(),
            similar_top_k=10,
        )
        assert clf._similar_top_k == 3

    @pytest.mark.asyncio
    async def test_only_top_3_ids_in_result_even_if_more_returned(self):
        resolved = [_similar(f"TKT-{i}") for i in range(5)]
        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=_make_engine(resolved=resolved),
            sop_retriever=_make_sop_retriever(),
            similar_top_k=3,
        )
        result = await clf.classify("test")
        assert len(result.similar_ticket_ids) == 3


# ---------------------------------------------------------------------------
# Tests — relevant SOPs (source 2)
# ---------------------------------------------------------------------------

class TestRelevantSops:

    @pytest.mark.asyncio
    async def test_sop_titles_in_result(self):
        sops = [_sop("SOP-RF-007"), _sop("SOP-HW-003")]
        result = await _make_classifier(sops=sops).classify("signal loss")
        assert result.relevant_sops == ["SOP-RF-007", "SOP-HW-003"]

    @pytest.mark.asyncio
    async def test_no_sops_gives_empty_list(self):
        result = await _make_classifier(sops=[]).classify("test")
        assert result.relevant_sops == []


# ---------------------------------------------------------------------------
# Tests — parallel fetch (four sources)
# ---------------------------------------------------------------------------

class TestParallelFetch:

    @pytest.mark.asyncio
    async def test_all_four_sources_queried(self):
        engine   = _make_engine()
        retriever = _make_sop_retriever()
        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=engine,
            sop_retriever=retriever,
        )
        await clf.classify("fibre cut on segment B")

        engine.find_similar_resolved.assert_awaited_once()
        engine.find_similar.assert_awaited_once()
        engine.find_similar_high_priority.assert_awaited_once()
        retriever.retrieve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_sources_queried_with_same_text(self):
        text = "BGP session flapping on RTR-LON-CORE-03"
        engine    = _make_engine()
        retriever = _make_sop_retriever()
        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=engine,
            sop_retriever=retriever,
        )
        await clf.classify(text)

        engine.find_similar_resolved.assert_awaited_once_with(text, top_k=3)
        engine.find_similar.assert_awaited_once_with(text, top_k=5)
        engine.find_similar_high_priority.assert_awaited_once_with(text, top_k=3)
        retriever.retrieve.assert_awaited_once_with(text, top_k=3)

    @pytest.mark.asyncio
    async def test_source1_failure_does_not_abort_others(self):
        engine = MagicMock()
        engine.find_similar_resolved      = AsyncMock(side_effect=RuntimeError("Chroma down"))
        engine.find_similar               = AsyncMock(return_value=[_similar("TKT-X")])
        engine.find_similar_high_priority = AsyncMock(return_value=[])
        retriever = _make_sop_retriever([_sop()])

        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=engine,
            sop_retriever=retriever,
        )
        result = await clf.classify("test")
        # source 1 failed → empty similar IDs; classification still completes
        assert result.similar_ticket_ids == []
        assert result.fault_type is not None

    @pytest.mark.asyncio
    async def test_source2_failure_does_not_abort_others(self):
        engine    = _make_engine(resolved=[_similar("TKT-A")])
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(side_effect=ConnectionError("SOP store unavailable"))

        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=engine,
            sop_retriever=retriever,
        )
        result = await clf.classify("test")
        assert result.relevant_sops == []
        assert result.similar_ticket_ids == ["TKT-A"]

    @pytest.mark.asyncio
    async def test_source3_failure_does_not_abort_others(self):
        engine = MagicMock()
        engine.find_similar_resolved      = AsyncMock(return_value=[_similar("TKT-A")])
        engine.find_similar               = AsyncMock(side_effect=RuntimeError("timeout"))
        engine.find_similar_high_priority = AsyncMock(return_value=[])
        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=engine,
            sop_retriever=_make_sop_retriever(),
        )
        result = await clf.classify("test")
        assert result.similar_ticket_ids == ["TKT-A"]

    @pytest.mark.asyncio
    async def test_source4_failure_does_not_abort_others(self):
        engine = MagicMock()
        engine.find_similar_resolved      = AsyncMock(return_value=[_similar("TKT-A")])
        engine.find_similar               = AsyncMock(return_value=[])
        engine.find_similar_high_priority = AsyncMock(side_effect=RuntimeError("timeout"))
        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=engine,
            sop_retriever=_make_sop_retriever(),
        )
        result = await clf.classify("test")
        assert result.similar_ticket_ids == ["TKT-A"]

    @pytest.mark.asyncio
    async def test_all_sources_fail_classification_still_succeeds(self):
        engine = MagicMock()
        engine.find_similar_resolved      = AsyncMock(side_effect=Exception("err"))
        engine.find_similar               = AsyncMock(side_effect=Exception("err"))
        engine.find_similar_high_priority = AsyncMock(side_effect=Exception("err"))
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(side_effect=Exception("err"))

        clf = FaultClassifier(
            client=_make_client(),
            matching_engine=engine,
            sop_retriever=retriever,
        )
        result = await clf.classify("test")
        assert result.similar_ticket_ids == []
        assert result.relevant_sops == []
        assert result.fault_type is not None


# ---------------------------------------------------------------------------
# Tests — context block injected into Claude prompt
# ---------------------------------------------------------------------------

class TestContextInjection:

    @pytest.mark.asyncio
    async def test_resolved_ticket_ids_appear_in_prompt(self):
        resolved  = [_similar("TKT-ALPHA", score=0.92)]
        clf = _make_classifier(resolved=resolved)
        await clf.classify("latency spike")

        user_content = clf._client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "TKT-ALPHA" in user_content

    @pytest.mark.asyncio
    async def test_sop_title_appears_in_prompt(self):
        clf = _make_classifier(sops=[_sop("SOP-RF-007")])
        await clf.classify("signal loss")

        user_content = clf._client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "SOP-RF-007" in user_content

    @pytest.mark.asyncio
    async def test_empty_context_produces_no_context_block(self):
        clf = _make_classifier(resolved=[], sops=[], all_similar=[], high_priority=[])
        await clf.classify("test")

        user_content = clf._client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "PRE-FETCHED CONTEXT" not in user_content

    @pytest.mark.asyncio
    async def test_context_block_has_four_source_headers(self):
        clf = _make_classifier(
            resolved=[_similar("TKT-A")],
            sops=[_sop()],
            all_similar=[_similar("TKT-B")],
            high_priority=[_similar("TKT-C")],
        )
        await clf.classify("test")
        user_content = clf._client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Source 1" in user_content
        assert "Source 2" in user_content
        assert "Source 3" in user_content
        assert "Source 4" in user_content


# ---------------------------------------------------------------------------
# Tests — Claude API error handling
# ---------------------------------------------------------------------------

class TestFaultClassifierErrors:

    @pytest.mark.asyncio
    async def test_anthropic_api_error_raises_classifier_error(self):
        import anthropic as _anth
        exc = _anth.APIStatusError("rate limited", response=MagicMock(status_code=429), body={})
        clf = _make_classifier(client_exc=exc)
        with pytest.raises(FaultClassifierError, match="Anthropic API error"):
            await clf.classify("test")

    @pytest.mark.asyncio
    async def test_no_tool_block_raises_classifier_error(self):
        text_block = SimpleNamespace(type="text", text="I cannot classify this.")
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(text_block))
        clf = FaultClassifier(
            client=client,
            matching_engine=_make_engine(),
            sop_retriever=_make_sop_retriever(),
        )
        with pytest.raises(FaultClassifierError, match="did not call classify_fault"):
            await clf.classify("test")

    @pytest.mark.asyncio
    async def test_unknown_fault_type_falls_back(self):
        block = _tool_block(fault_type="fiber_break")
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine(),
                              sop_retriever=_make_sop_retriever())
        result = await clf.classify("test")
        assert result.fault_type == FaultType.UNKNOWN

    @pytest.mark.asyncio
    async def test_unknown_layer_falls_back_to_service(self):
        block = _tool_block(affected_layer="network")
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine(),
                              sop_retriever=_make_sop_retriever())
        result = await clf.classify("test")
        assert result.affected_layer == AffectedLayer.SERVICE

    @pytest.mark.asyncio
    async def test_confidence_clamped_above_1(self):
        block = _tool_block(confidence_score=1.8)
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine(),
                              sop_retriever=_make_sop_retriever())
        result = await clf.classify("test")
        assert result.confidence_score == 1.0

    @pytest.mark.asyncio
    async def test_confidence_clamped_below_0(self):
        block = _tool_block(confidence_score=-0.3)
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_claude_response(block))
        clf = FaultClassifier(client=client, matching_engine=_make_engine(),
                              sop_retriever=_make_sop_retriever())
        result = await clf.classify("test")
        assert result.confidence_score == 0.0


# ---------------------------------------------------------------------------
# Tests — _FetchedContext dataclass
# ---------------------------------------------------------------------------

class TestFetchedContext:

    def test_defaults_to_empty_lists(self):
        ctx = _FetchedContext()
        assert ctx.resolved == []
        assert ctx.sops == []
        assert ctx.all_incidents == []
        assert ctx.high_priority == []

    def test_context_block_empty_when_all_empty(self):
        block = FaultClassifier._build_context_block(_FetchedContext())
        assert block == ""

    def test_context_block_contains_ticket_ids(self):
        ctx = _FetchedContext(resolved=[_similar("TKT-XYZ", score=0.95)])
        block = FaultClassifier._build_context_block(ctx)
        assert "TKT-XYZ" in block
        assert "0.95" in block

    def test_context_block_contains_sop_title(self):
        ctx = _FetchedContext(sops=[_sop("SOP-RF-007", score=0.82)])
        block = FaultClassifier._build_context_block(ctx)
        assert "SOP-RF-007" in block

    def test_context_block_omits_empty_sources(self):
        ctx = _FetchedContext(
            resolved=[_similar("TKT-A")],
            sops=[],
            all_incidents=[],
            high_priority=[],
        )
        block = FaultClassifier._build_context_block(ctx)
        assert "Source 1" in block
        assert "Source 2" not in block
        assert "Source 3" not in block
        assert "Source 4" not in block
