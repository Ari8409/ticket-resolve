import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.config import Settings


@pytest.fixture
def settings():
    return Settings(
        OPENAI_API_KEY="sk-test",
        CHROMA_HOST="localhost",
        CHROMA_PORT=8001,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        WEBHOOK_SECRET="test-secret",
    )


@pytest.fixture
def mock_chroma_ticket_collection():
    col = MagicMock()
    col.query = AsyncMock(return_value={
        "ids": [["t-hist-001", "t-hist-002"]],
        "distances": [[0.15, 0.30]],
        "metadatas": [[
            {"ticket_id": "t-hist-001", "title": "DB timeout issue", "priority": "high", "resolution_summary": "Restarted Postgres replica"},
            {"ticket_id": "t-hist-002", "title": "Slow query under load", "priority": "medium", "resolution_summary": "Added index on user_id"},
        ]],
        "documents": [["DB timed out", "Slow queries under load"]],
    })
    col.upsert = AsyncMock()
    return col


@pytest.fixture
def mock_chroma_sop_collection():
    col = MagicMock()
    col.query = AsyncMock(return_value={
        "ids": [["sop-chunk-001"]],
        "distances": [[0.10]],
        "metadatas": [[{"sop_id": "sop-001", "title": "Database Restart SOP", "chunk_index": 0, "doc_path": "data/sops/db.md", "category": "database"}]],
        "documents": [["1. Connect to server\n2. Run systemctl restart postgresql\n3. Verify connections"]],
    })
    col.upsert = AsyncMock()
    return col


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed_text = AsyncMock(return_value=[0.1] * 1536)
    embedder.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
    return embedder


@pytest.fixture
def mock_llm_output():
    return (
        '{"recommended_steps": ["Restart the database service", "Check error logs", "Notify on-call"], '
        '"confidence_score": 0.87, "relevant_sops": ["Database Restart SOP"], '
        '"similar_ticket_ids": ["t-hist-001"], "escalation_required": false, '
        '"reasoning": "Based on historical ticket t-hist-001 and the DB Restart SOP."}'
    )
