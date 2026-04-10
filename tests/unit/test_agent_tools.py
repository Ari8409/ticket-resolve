import pytest
from unittest.mock import AsyncMock, MagicMock

from app.matching.engine import MatchingEngine
from app.models.recommendation import SimilarTicket, SOPMatch
from app.recommendation.tools import build_agent_tools
from app.sop.retriever import SOPRetriever


@pytest.fixture
def mock_sop_retriever():
    r = MagicMock(spec=SOPRetriever)
    r.retrieve = AsyncMock(return_value=[
        SOPMatch(sop_id="s1", title="DB SOP", content="Restart the DB service.", score=0.91),
    ])
    return r


@pytest.fixture
def mock_matching_engine():
    e = MagicMock(spec=MatchingEngine)
    e.find_similar = AsyncMock(return_value=[
        SimilarTicket(ticket_id="t-old-1", title="DB crash", score=0.88, resolution_summary="Rebooted replica"),
    ])
    return e


@pytest.fixture
def tools(mock_sop_retriever, mock_matching_engine):
    return build_agent_tools(mock_sop_retriever, mock_matching_engine)


@pytest.mark.asyncio
async def test_sop_retrieval_tool_returns_content(tools):
    sop_tool = next(t for t in tools if t.name == "sop_retrieval_tool")
    result = await sop_tool.ainvoke({"query": "database restart"})
    assert "DB SOP" in result
    assert "Restart the DB service" in result


@pytest.mark.asyncio
async def test_sop_retrieval_tool_no_results(tools, mock_sop_retriever):
    mock_sop_retriever.retrieve = AsyncMock(return_value=[])
    sop_tool = next(t for t in tools if t.name == "sop_retrieval_tool")
    result = await sop_tool.ainvoke({"query": "something obscure"})
    assert "No relevant SOPs" in result


@pytest.mark.asyncio
async def test_ticket_similarity_tool_returns_resolution(tools):
    sim_tool = next(t for t in tools if t.name == "ticket_similarity_tool")
    result = await sim_tool.ainvoke({"query": "database crash"})
    assert "t-old-1" in result
    assert "Rebooted replica" in result
