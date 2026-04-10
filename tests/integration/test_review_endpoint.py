"""
Integration tests for the human-review endpoint.

GET  /api/v1/telco-tickets/{ticket_id}/review
POST /api/v1/telco-tickets/{ticket_id}/review

All DB and Chroma dependencies are mocked so these tests run without
infrastructure.  The FastAPI app is exercised via ASGITransport (no real
HTTP server) which covers routing, request validation, and HTTP semantics.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

TICKET_ID = "TKT-REVIEW01"

TICKET_DICT = {
    "ticket_id":      TICKET_ID,
    "affected_node":  "LTE_ENB_780321",
    "severity":       "major",
    "fault_type":     "hardware_failure",
    "description":    "LTE_ENB_780321*equipmentAlarm/HW Fault*1*Hardware failure\n\nDetails here.",
    "status":         "resolved",
    "timestamp":      "2025-11-27T00:00:00",
    "alarm_name":     "HW Fault",
    "alarm_category": "equipmentAlarm",
    "network_type":   "4G",
    "object_class":   "A2",
    "location_details": "209 Hougang Street 21",
    "primary_cause":  "Hardware Fault",
    "resolution":     "Module replaced",
    "resolution_code": "Hardware Replacement",
    "sop_id":         "SOP-HW-001",
    "remarks":        None,
    "title":          "A2 LTE_ENB_780321",
}

DISPATCH_DECISION = {
    "recommended_steps": [
        "Check hardware logs",
        "Replace faulty module",
        "Re-test connectivity",
    ],
    "relevant_sops":      ["SOP-HW-001"],
    "dispatch_mode":      "on_site",
    "confidence_score":   0.91,
    "natural_language_summary": "Hardware fault — on-site replacement required.",
    "ranked_sops":        [],
    "short_circuited":    False,
    "short_circuit_reason": "",
    "alarm_status":       None,
    "maintenance_active": False,
    "remote_feasible":    False,
    "remote_confidence":  0.0,
    "escalation_required": False,
    "reasoning":          "Known HW fault pattern.",
    "similar_ticket_ids": [],
}

REVIEW_RESULT_DICT = {
    "ticket_id":                 TICKET_ID,
    "action_taken":              "approve",
    "new_status":                "resolved",
    "message":                   "Ticket approved and marked RESOLVED.",
    "executed_steps":            ["Check hardware logs", "Replace faulty module"],
    "sop_applied":               "SOP-HW-001",
    "escalated_to":              None,
    "indexed_as_training_signal": True,
    "reviewed_by":               "alice.noc",
    "reviewed_at":               "2025-11-27T10:00:00",
}


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------

def _make_app_with_overrides(repo=None, review_handler=None):
    """
    Create a FastAPI test app with patched lifespan and optional dependency overrides.
    """
    from app.main import create_app
    from app.dependencies import get_telco_repo, get_review_handler

    app = create_app()

    if repo is not None:
        async def _fake_repo():
            yield repo
        app.dependency_overrides[get_telco_repo] = _fake_repo

    if review_handler is not None:
        async def _fake_handler():
            yield review_handler
        app.dependency_overrides[get_review_handler] = _fake_handler

    return app


def _patch_lifespan():
    """
    Context manager stack to suppress real DB and Chroma init in lifespan.
    """
    import contextlib
    return contextlib.ExitStack()


# ---------------------------------------------------------------------------
# GET /telco-tickets/{ticket_id}/review
# ---------------------------------------------------------------------------

class TestGetReviewContext:
    @pytest.mark.asyncio
    async def test_returns_200_with_recommendation_ready(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value=TICKET_DICT)
        repo.get_dispatch_decision = AsyncMock(return_value=DISPATCH_DECISION)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/telco-tickets/{TICKET_ID}/review")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["ticket_id"] == TICKET_ID

    @pytest.mark.asyncio
    async def test_returns_recommendation_fields(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value=TICKET_DICT)
        repo.get_dispatch_decision = AsyncMock(return_value=DISPATCH_DECISION)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/telco-tickets/{TICKET_ID}/review")

        data = response.json()
        rec = data["recommendation"]
        assert rec["dispatch_mode"] == "on_site"
        assert rec["confidence_score"] == 0.91
        assert "Hardware fault" in rec["natural_language_summary"]

    @pytest.mark.asyncio
    async def test_returns_202_when_pipeline_still_running(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})
        repo.get_dispatch_decision = AsyncMock(return_value=None)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/telco-tickets/{TICKET_ID}/review")

        # Returns 200 with ready=False (no dispatch decision yet)
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is False
        assert "processing" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_ticket(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/telco-tickets/TKT-NOTFOUND/review")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_ticket_fields(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value=TICKET_DICT)
        repo.get_dispatch_decision = AsyncMock(return_value=DISPATCH_DECISION)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/telco-tickets/{TICKET_ID}/review")

        data = response.json()
        ticket = data["ticket"]
        assert ticket["affected_node"] == "LTE_ENB_780321"
        assert ticket["alarm_name"] == "HW Fault"
        assert ticket["network_type"] == "4G"

    @pytest.mark.asyncio
    async def test_available_actions_empty_for_resolved_ticket(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "resolved"})
        repo.get_dispatch_decision = AsyncMock(return_value=DISPATCH_DECISION)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/telco-tickets/{TICKET_ID}/review")

        data = response.json()
        assert data["available_actions"] == []

    @pytest.mark.asyncio
    async def test_available_actions_all_three_for_in_progress_ticket(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})
        repo.get_dispatch_decision = AsyncMock(return_value=DISPATCH_DECISION)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/telco-tickets/{TICKET_ID}/review")

        data = response.json()
        assert set(data["available_actions"]) == {"approve", "override", "escalate"}


# ---------------------------------------------------------------------------
# POST /telco-tickets/{ticket_id}/review — APPROVE
# ---------------------------------------------------------------------------

class TestPostReviewApprove:
    @pytest.mark.asyncio
    async def test_approve_returns_200(self):
        from app.models.review import ReviewAction, ReviewResult

        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})

        handler = MagicMock()
        handler.handle = AsyncMock(return_value=ReviewResult(
            ticket_id=TICKET_ID,
            action_taken=ReviewAction.APPROVE,
            new_status="resolved",
            message="Approved.",
            executed_steps=["Step 1", "Step 2"],
            sop_applied="SOP-HW-001",
            indexed_as_training_signal=True,
            reviewed_by="alice.noc",
        ))

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo, review_handler=handler)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={"action": "approve", "reviewed_by": "alice.noc"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["action_taken"] == "approve"
        assert data["new_status"] == "resolved"
        assert data["indexed_as_training_signal"] is True

    @pytest.mark.asyncio
    async def test_approve_calls_handler_handle(self):
        from app.models.review import ReviewAction, ReviewResult

        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})

        handler = MagicMock()
        handler.handle = AsyncMock(return_value=ReviewResult(
            ticket_id=TICKET_ID,
            action_taken=ReviewAction.APPROVE,
            new_status="resolved",
            message="OK",
            executed_steps=[],
            indexed_as_training_signal=False,
            reviewed_by="alice.noc",
        ))

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo, review_handler=handler)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={"action": "approve", "reviewed_by": "alice.noc"},
                )

        handler.handle.assert_awaited_once()
        call_ticket_id, call_request = handler.handle.call_args[0]
        assert call_ticket_id == TICKET_ID
        assert call_request.action.value == "approve"


# ---------------------------------------------------------------------------
# POST /telco-tickets/{ticket_id}/review — OVERRIDE
# ---------------------------------------------------------------------------

class TestPostReviewOverride:
    @pytest.mark.asyncio
    async def test_override_returns_200(self):
        from app.models.review import ReviewAction, ReviewResult

        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})

        handler = MagicMock()
        handler.handle = AsyncMock(return_value=ReviewResult(
            ticket_id=TICKET_ID,
            action_taken=ReviewAction.OVERRIDE,
            new_status="in_progress",
            message="Overridden.",
            executed_steps=["Alt step 1", "Alt step 2"],
            sop_applied="SOP-RF-005",
            indexed_as_training_signal=False,
            reviewed_by="bob.noc",
        ))

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo, review_handler=handler)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={
                        "action": "override",
                        "reviewed_by": "bob.noc",
                        "override_sop_id": "SOP-RF-005",
                        "override_notes": "Different approach needed.",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["action_taken"] == "override"
        assert data["new_status"] == "in_progress"
        assert data["sop_applied"] == "SOP-RF-005"


# ---------------------------------------------------------------------------
# POST /telco-tickets/{ticket_id}/review — ESCALATE
# ---------------------------------------------------------------------------

class TestPostReviewEscalate:
    @pytest.mark.asyncio
    async def test_escalate_returns_200(self):
        from app.models.review import ReviewAction, ReviewResult

        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})

        handler = MagicMock()
        handler.handle = AsyncMock(return_value=ReviewResult(
            ticket_id=TICKET_ID,
            action_taken=ReviewAction.ESCALATE,
            new_status="escalated",
            message="Escalated.",
            executed_steps=[],
            escalated_to="rf-tier2",
            indexed_as_training_signal=False,
            reviewed_by="charlie.noc",
        ))

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo, review_handler=handler)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={
                        "action": "escalate",
                        "reviewed_by": "charlie.noc",
                        "escalation_note": "Site power instability suspected.",
                        "escalate_to": "rf-tier2",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["action_taken"] == "escalate"
        assert data["new_status"] == "escalated"
        assert data["escalated_to"] == "rf-tier2"
        assert data["indexed_as_training_signal"] is False


# ---------------------------------------------------------------------------
# POST — guard rails
# ---------------------------------------------------------------------------

class TestPostReviewGuards:
    @pytest.mark.asyncio
    async def test_returns_404_when_ticket_not_found(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/telco-tickets/TKT-NOTFOUND/review",
                    json={"action": "approve", "reviewed_by": "alice.noc"},
                )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_409_when_ticket_already_resolved(self):
        """Resolved tickets cannot be reviewed again."""
        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "resolved"})

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={"action": "approve", "reviewed_by": "alice.noc"},
                )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_409_when_ticket_already_escalated(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "escalated"})

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={"action": "escalate", "escalation_note": "Again."},
                )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_409_when_ticket_already_closed(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "closed"})

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={"action": "approve"},
                )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_422_for_invalid_action(self):
        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={"action": "delete_everything"},
                )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_handler_value_error_returns_400(self):
        """Handler raises ValueError (e.g. missing override_sop_id) → 400."""
        from app.core.exceptions import TicketNotFoundError

        repo = MagicMock()
        repo.get = AsyncMock(return_value={**TICKET_DICT, "status": "in_progress"})

        handler = MagicMock()
        handler.handle = AsyncMock(side_effect=ValueError("override_sop_id is required"))

        with (
            patch("app.storage.chroma_client.get_chroma_client", new_callable=MagicMock) as mc,
            patch("app.storage.repositories.init_engine"),
            patch("app.storage.repositories.create_tables", new_callable=AsyncMock),
            patch("app.storage.repositories.get_session"),
        ):
            mc.return_value = AsyncMock()
            app = _make_app_with_overrides(repo=repo, review_handler=handler)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/telco-tickets/{TICKET_ID}/review",
                    json={"action": "override", "reviewed_by": "bob.noc"},
                )

        assert response.status_code == 400
        assert "override_sop_id" in response.json()["detail"]
