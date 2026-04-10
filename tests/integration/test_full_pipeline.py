"""End-to-end pipeline test with all external dependencies mocked."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.matching.engine import MatchingEngine
from app.matching.ticket_store import TicketStore
from app.models.recommendation import SimilarTicket, SOPMatch
from app.models.ticket import TicketIn, TicketPriority
from app.recommendation.agent import ResolutionAgent
from app.sop.retriever import SOPRetriever
from app.tasks.background import run_resolution_pipeline


@pytest.fixture
def ticket():
    return TicketIn(
        source="api",
        title="All services unreachable",
        description="Every microservice is returning 503 — load balancer may be down",
        priority=TicketPriority.CRITICAL,
    )


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.update_status = AsyncMock()
    repo.save_recommendation = AsyncMock()
    return repo


@pytest.fixture
def mock_agent(mock_llm_output):
    from app.models.recommendation import RecommendationResult
    agent = MagicMock(spec=ResolutionAgent)
    agent.resolve = AsyncMock(return_value=RecommendationResult(
        ticket_id="t-e2e-001",
        recommended_steps=["Check LB health", "Restart LB", "Notify team"],
        confidence_score=0.92,
        relevant_sops=["Load Balancer SOP"],
        similar_ticket_ids=["t-old-42"],
        escalation_required=True,
        reasoning="Critical priority + LB pattern",
    ))
    return agent


@pytest.fixture
def mock_matching_engine(mock_embedder, mock_chroma_ticket_collection):
    store = TicketStore(mock_chroma_ticket_collection)
    return MatchingEngine(embedder=mock_embedder, ticket_store=store)


@pytest.fixture
def mock_sop_retriever(mock_embedder, mock_chroma_sop_collection):
    store = MagicMock()
    store.query_relevant = AsyncMock(return_value=[
        SOPMatch(sop_id="s1", title="LB SOP", content="Check health endpoint", score=0.88)
    ])
    from app.sop.sop_store import SOPStore
    return SOPRetriever(embedder=mock_embedder, sop_store=SOPStore(mock_chroma_sop_collection))


@pytest.mark.asyncio
async def test_full_pipeline_succeeds(ticket, mock_repo, mock_agent, mock_matching_engine, mock_sop_retriever):
    await run_resolution_pipeline(
        ticket_id="t-e2e-001",
        ticket=ticket,
        matching_engine=mock_matching_engine,
        sop_retriever=mock_sop_retriever,
        agent=mock_agent,
        repo=mock_repo,
    )

    mock_agent.resolve.assert_called_once()
    mock_repo.save_recommendation.assert_called_once()

    # Status should be updated to PROCESSING then RESOLVED
    status_calls = [call.args[1] for call in mock_repo.update_status.call_args_list]
    assert any("processing" in str(s).lower() for s in status_calls)
    assert any("resolved" in str(s).lower() for s in status_calls)


@pytest.mark.asyncio
async def test_pipeline_marks_failed_on_agent_error(ticket, mock_repo, mock_matching_engine, mock_sop_retriever):
    failing_agent = MagicMock(spec=ResolutionAgent)
    failing_agent.resolve = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    await run_resolution_pipeline(
        ticket_id="t-e2e-002",
        ticket=ticket,
        matching_engine=mock_matching_engine,
        sop_retriever=mock_sop_retriever,
        agent=failing_agent,
        repo=mock_repo,
    )

    status_calls = [str(call.args[1]) for call in mock_repo.update_status.call_args_list]
    assert any("failed" in s.lower() for s in status_calls)
    mock_repo.save_recommendation.assert_not_called()
