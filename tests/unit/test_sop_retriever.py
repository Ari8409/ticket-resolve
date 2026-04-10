import pytest

from app.sop.retriever import SOPRetriever
from app.sop.sop_store import SOPStore


@pytest.fixture
def sop_store(mock_chroma_sop_collection):
    return SOPStore(mock_chroma_sop_collection)


@pytest.fixture
def retriever(mock_embedder, sop_store):
    return SOPRetriever(embedder=mock_embedder, sop_store=sop_store, top_k=3)


@pytest.mark.asyncio
async def test_retrieve_returns_matches(retriever):
    matches = await retriever.retrieve("database restart procedure")
    assert len(matches) == 1
    assert matches[0].title == "Database Restart SOP"
    assert matches[0].score == pytest.approx(0.90, abs=0.01)


@pytest.mark.asyncio
async def test_retrieve_respects_top_k(retriever, mock_chroma_sop_collection):
    await retriever.retrieve("some query", top_k=2)
    call_kwargs = mock_chroma_sop_collection.query.call_args.kwargs
    assert call_kwargs["n_results"] == 2
