import pytest

from app.matching.engine import MatchingEngine
from app.matching.ticket_store import TicketStore
from app.models.ticket import TicketIn, TicketPriority


@pytest.fixture
def ticket_store(mock_chroma_ticket_collection):
    return TicketStore(mock_chroma_ticket_collection)


@pytest.fixture
def engine(mock_embedder, ticket_store):
    return MatchingEngine(
        embedder=mock_embedder,
        ticket_store=ticket_store,
        top_k=5,
        score_threshold=0.0,
    )


@pytest.fixture
def sample_ticket():
    return TicketIn(
        source="api",
        title="Database connection timeout",
        description="PostgreSQL times out after 30 seconds under load",
        priority=TicketPriority.HIGH,
    )


@pytest.mark.asyncio
async def test_find_similar_returns_results(engine, sample_ticket):
    results = await engine.find_similar_for_ticket(sample_ticket)
    assert len(results) == 2
    assert results[0].ticket_id == "t-hist-001"
    assert results[0].score == pytest.approx(0.85, abs=0.01)


@pytest.mark.asyncio
async def test_index_ticket_calls_upsert(engine, sample_ticket, mock_chroma_ticket_collection):
    await engine.index_ticket("t-new-001", sample_ticket, resolution_summary="Fixed by restart")
    mock_chroma_ticket_collection.upsert.assert_called_once()
    call_kwargs = mock_chroma_ticket_collection.upsert.call_args.kwargs
    assert call_kwargs["ids"] == ["t-new-001"]


@pytest.mark.asyncio
async def test_find_similar_by_query_string(engine):
    results = await engine.find_similar("database timeout error")
    assert len(results) > 0
