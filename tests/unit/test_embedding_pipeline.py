"""
Unit tests for TicketEmbeddingPipeline.

Both SentenceTransformerEmbedder and MatchingEngine are mocked so these
tests require no model download, no Chroma instance, and no GPU.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.matching.pipeline import TicketEmbeddingPipeline
from app.models.recommendation import SimilarTicket, TicketEmbeddingResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIM = 384


def _fake_embedding(dim: int = DIM) -> list[float]:
    return [0.01 * i for i in range(dim)]


def _make_similar(ticket_id: str, score: float, resolved: bool = True) -> SimilarTicket:
    return SimilarTicket(
        ticket_id=ticket_id,
        title=f"Historical ticket {ticket_id}",
        score=score,
        resolution_summary="Replaced faulty SFP module" if resolved else None,
    )


def _make_embedder(dim: int = DIM) -> MagicMock:
    embedder = MagicMock()
    embedder.model_name = "all-MiniLM-L6-v2"
    embedder.embedding_dim = dim
    embedder.embed_text = AsyncMock(return_value=_fake_embedding(dim))
    embedder.embed_batch = AsyncMock(
        side_effect=lambda texts: [_fake_embedding(dim) for _ in texts]
    )
    return embedder


def _make_engine(matches: list[SimilarTicket]) -> MagicMock:
    engine = MagicMock()
    engine.find_similar_resolved = AsyncMock(return_value=matches)
    return engine


# ---------------------------------------------------------------------------
# Tests — single ticket
# ---------------------------------------------------------------------------

class TestTicketEmbeddingPipelineRun:

    @pytest.mark.asyncio
    async def test_returns_ticket_embedding_result(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        result = await pipeline.run("TKT-001", "High latency on backbone link")
        assert isinstance(result, TicketEmbeddingResult)

    @pytest.mark.asyncio
    async def test_result_carries_ticket_id(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        result = await pipeline.run("TKT-XYZ", "signal loss")
        assert result.ticket_id == "TKT-XYZ"

    @pytest.mark.asyncio
    async def test_result_carries_description(self):
        desc = "Node NODE-ATL-01 is unreachable via ICMP"
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        result = await pipeline.run("TKT-001", desc)
        assert result.description == desc

    @pytest.mark.asyncio
    async def test_embedding_vector_has_correct_dimension(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(DIM),
            engine=_make_engine([]),
        )
        result = await pipeline.run("TKT-001", "latency spike")
        assert len(result.embedding) == DIM
        assert result.embedding_dim == DIM

    @pytest.mark.asyncio
    async def test_model_name_propagated(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        result = await pipeline.run("TKT-001", "hardware failure")
        assert result.model_name == "all-MiniLM-L6-v2"

    @pytest.mark.asyncio
    async def test_top_matches_returned(self):
        matches = [
            _make_similar("TKT-100", 0.92),
            _make_similar("TKT-101", 0.87),
            _make_similar("TKT-102", 0.81),
        ]
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine(matches),
        )
        result = await pipeline.run("TKT-001", "packet loss detected")

        assert len(result.top_matches) == 3
        assert result.top_matches[0].ticket_id == "TKT-100"
        assert result.top_matches[0].score == 0.92

    @pytest.mark.asyncio
    async def test_no_matches_returns_empty_list(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        result = await pipeline.run("TKT-001", "unknown fault")
        assert result.top_matches == []

    @pytest.mark.asyncio
    async def test_score_threshold_filters_low_scores(self):
        matches = [
            _make_similar("TKT-100", 0.90),
            _make_similar("TKT-101", 0.60),  # below threshold
            _make_similar("TKT-102", 0.50),  # below threshold
        ]
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine(matches),
            score_threshold=0.75,
        )
        result = await pipeline.run("TKT-001", "congestion on core router")
        assert len(result.top_matches) == 1
        assert result.top_matches[0].ticket_id == "TKT-100"

    @pytest.mark.asyncio
    async def test_top_k_passed_to_engine(self):
        engine = _make_engine([])
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=engine,
            top_k=3,
        )
        await pipeline.run("TKT-001", "test description")
        engine.find_similar_resolved.assert_awaited_once_with(
            query="test description", top_k=3
        )

    @pytest.mark.asyncio
    async def test_embedder_called_with_description(self):
        embedder = _make_embedder()
        pipeline = TicketEmbeddingPipeline(
            embedder=embedder,
            engine=_make_engine([]),
        )
        await pipeline.run("TKT-001", "fibre cut on segment B")
        embedder.embed_text.assert_awaited_once_with("fibre cut on segment B")


# ---------------------------------------------------------------------------
# Tests — batch
# ---------------------------------------------------------------------------

class TestTicketEmbeddingPipelineBatch:

    @pytest.mark.asyncio
    async def test_batch_returns_one_result_per_ticket(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        tickets = [("TKT-A", "desc A"), ("TKT-B", "desc B"), ("TKT-C", "desc C")]
        results = await pipeline.run_batch(tickets)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_batch_empty_input_returns_empty(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        results = await pipeline.run_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_uses_embed_batch_not_embed_text(self):
        """embed_batch should be called once, not embed_text N times."""
        embedder = _make_embedder()
        pipeline = TicketEmbeddingPipeline(
            embedder=embedder,
            engine=_make_engine([]),
        )
        tickets = [("TKT-1", "desc 1"), ("TKT-2", "desc 2")]
        await pipeline.run_batch(tickets)

        embedder.embed_batch.assert_awaited_once()
        embedder.embed_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_batch_ticket_ids_preserved(self):
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=_make_engine([]),
        )
        tickets = [("TKT-ALPHA", "desc"), ("TKT-BETA", "desc")]
        results = await pipeline.run_batch(tickets)
        ids = [r.ticket_id for r in results]
        assert ids == ["TKT-ALPHA", "TKT-BETA"]

    @pytest.mark.asyncio
    async def test_batch_each_ticket_queries_resolved_matches(self):
        engine = _make_engine([_make_similar("TKT-OLD", 0.88)])
        pipeline = TicketEmbeddingPipeline(
            embedder=_make_embedder(),
            engine=engine,
        )
        tickets = [("TKT-1", "a"), ("TKT-2", "b")]
        results = await pipeline.run_batch(tickets)

        # find_similar_resolved should be called once per ticket
        assert engine.find_similar_resolved.await_count == 2
        # Each result gets the mocked match
        assert results[0].top_matches[0].ticket_id == "TKT-OLD"
        assert results[1].top_matches[0].ticket_id == "TKT-OLD"
