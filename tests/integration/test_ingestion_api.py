import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def sample_payload():
    return {
        "source": "api",
        "title": "Database connection timeout",
        "description": "PostgreSQL times out after 30 seconds under load on prod",
        "priority": "high",
        "category": "database",
    }


@pytest.mark.asyncio
async def test_ingest_ticket_returns_202(sample_payload):
    """Smoke test: POST /tickets returns 202 with a ticket_id."""
    with (
        patch("app.storage.chroma_client.get_chroma_client") as mock_chroma,
        patch("app.storage.repositories.init_engine"),
        patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
        patch("app.storage.repositories.get_session"),
    ):
        mock_chroma.return_value = AsyncMock()
        mock_chroma.return_value.heartbeat = AsyncMock()

        from app.main import create_app
        app = create_app()

        # Override the repo dependency to avoid real DB
        async def fake_repo():
            repo = MagicMock()
            repo.save = AsyncMock(return_value="test-ticket-id-001")
            repo.update_status = AsyncMock()
            yield repo

        from app.dependencies import get_repo
        app.dependency_overrides[get_repo] = fake_repo

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/tickets/", json=sample_payload)

        assert response.status_code == 202
        data = response.json()
        assert "ticket_id" in data
        assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_ingest_ticket_validates_short_title(sample_payload):
    sample_payload["title"] = "DB"  # too short (min_length=3 allows 3 chars; let's use 1)
    sample_payload["title"] = "X"
    with (
        patch("app.storage.chroma_client.get_chroma_client") as mock_chroma,
        patch("app.storage.repositories.init_engine"),
        patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
        patch("app.storage.repositories.get_session"),
    ):
        mock_chroma.return_value = AsyncMock()
        from app.main import create_app
        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/tickets/", json=sample_payload)

        assert response.status_code == 422
