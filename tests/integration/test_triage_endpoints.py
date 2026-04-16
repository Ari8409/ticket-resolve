"""
Integration tests for the HITL triage endpoints.

Endpoints under test
--------------------
GET  /api/v1/telco-tickets/pending-review
POST /api/v1/telco-tickets/{ticket_id}/assign
POST /api/v1/telco-tickets/{ticket_id}/manual-resolve

All heavy dependencies (HumanTriageHandler) are mocked via FastAPI's
dependency_overrides so no database or Chroma is needed.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import TicketNotFoundError
from app.dependencies import get_triage_handler
from app.main import app
from app.models.human_triage import (
    AssignResult,
    ManualResolveResult,
    TriageSummary,
    UnresolvableReason,
)
from app.models.telco_ticket import TelcoTicketStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_triage_handler():
    return MagicMock()


@pytest.fixture()
def client(mock_triage_handler):
    app.dependency_overrides[get_triage_handler] = lambda: mock_triage_handler
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _summary(ticket_id: str = "TKT-001", **overrides) -> TriageSummary:
    defaults = dict(
        ticket_id=ticket_id,
        affected_node="NODE-X",
        fault_type="hardware_failure",
        severity="critical",
        network_type="4G",
        alarm_name="HW Fault",
        alarm_category="equipmentAlarm",
        location_details="Site A",
        description="Critical HW fault on NODE-X.",
        reasons=[UnresolvableReason.NO_SOP_MATCH, UnresolvableReason.LOW_CONFIDENCE],
        confidence_score=0.35,
        sop_candidates_found=0,
        similar_tickets_found=1,
        flagged_at=datetime(2024, 6, 1, 10, 0, 0),
        assigned_to=None,
        assigned_at=None,
    )
    defaults.update(overrides)
    return TriageSummary(**defaults)


def _assign_result(ticket_id: str = "TKT-001") -> AssignResult:
    return AssignResult(
        ticket_id=ticket_id,
        assigned_to="noc.engineer01",
        assigned_at=datetime(2024, 6, 1, 11, 0, 0),
        message=f"Ticket {ticket_id} assigned to noc.engineer01. Status remains PENDING_REVIEW until manually resolved.",
    )


def _resolve_result(ticket_id: str = "TKT-001") -> ManualResolveResult:
    return ManualResolveResult(
        ticket_id=ticket_id,
        new_status=TelcoTicketStatus.RESOLVED.value,
        message=f"Ticket {ticket_id} manually resolved by noc.engineer01. 3 step(s) recorded. Resolution indexed as training signal.",
        executed_steps=["Step 1", "Step 2", "Step 3"],
        sop_reference="SOP-RAN-004",
        resolved_by="noc.engineer01",
        resolved_at=datetime(2024, 6, 1, 12, 0, 0),
        indexed_as_training_signal=True,
    )


# ---------------------------------------------------------------------------
# GET /pending-review
# ---------------------------------------------------------------------------

class TestListPendingReview:

    def test_returns_200_with_summary_list(self, client, mock_triage_handler):
        mock_triage_handler.list_pending = AsyncMock(
            return_value=[_summary("TKT-001"), _summary("TKT-002")]
        )

        resp = client.get("/api/v1/telco-tickets/pending-review")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["ticket_id"] == "TKT-001"
        assert data[1]["ticket_id"] == "TKT-002"

    def test_returns_empty_list_when_no_pending(self, client, mock_triage_handler):
        mock_triage_handler.list_pending = AsyncMock(return_value=[])

        resp = client.get("/api/v1/telco-tickets/pending-review")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_passes_limit_query_param(self, client, mock_triage_handler):
        mock_triage_handler.list_pending = AsyncMock(return_value=[])

        client.get("/api/v1/telco-tickets/pending-review?limit=25")

        mock_triage_handler.list_pending.assert_called_once_with(limit=25)

    def test_default_limit_is_100(self, client, mock_triage_handler):
        mock_triage_handler.list_pending = AsyncMock(return_value=[])

        client.get("/api/v1/telco-tickets/pending-review")

        mock_triage_handler.list_pending.assert_called_once_with(limit=100)

    def test_summary_includes_reasons(self, client, mock_triage_handler):
        summary = _summary(
            reasons=[UnresolvableReason.NO_SOP_MATCH, UnresolvableReason.UNKNOWN_FAULT_TYPE]
        )
        mock_triage_handler.list_pending = AsyncMock(return_value=[summary])

        resp = client.get("/api/v1/telco-tickets/pending-review")
        reasons = resp.json()[0]["reasons"]

        assert "no_sop_match"       in reasons
        assert "unknown_fault_type" in reasons

    def test_invalid_limit_returns_422(self, client, mock_triage_handler):
        mock_triage_handler.list_pending = AsyncMock(return_value=[])

        # limit < 1 is invalid
        resp = client.get("/api/v1/telco-tickets/pending-review?limit=0")
        assert resp.status_code == 422

    def test_limit_over_500_returns_422(self, client, mock_triage_handler):
        mock_triage_handler.list_pending = AsyncMock(return_value=[])

        resp = client.get("/api/v1/telco-tickets/pending-review?limit=501")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /{ticket_id}/assign
# ---------------------------------------------------------------------------

class TestAssignEndpoint:

    def test_assign_returns_200(self, client, mock_triage_handler):
        mock_triage_handler.assign = AsyncMock(return_value=_assign_result())

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/assign",
            json={"assign_to": "noc.engineer01"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticket_id"]   == "TKT-001"
        assert data["assigned_to"] == "noc.engineer01"

    def test_assign_with_notes(self, client, mock_triage_handler):
        mock_triage_handler.assign = AsyncMock(return_value=_assign_result())

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/assign",
            json={"assign_to": "team.alpha", "notes": "Check fibre at FERRARI site."},
        )
        assert resp.status_code == 200

    def test_assign_404_when_ticket_missing(self, client, mock_triage_handler):
        mock_triage_handler.assign = AsyncMock(side_effect=TicketNotFoundError("TKT-MISSING"))

        resp = client.post(
            "/api/v1/telco-tickets/TKT-MISSING/assign",
            json={"assign_to": "noc.engineer01"},
        )
        assert resp.status_code == 404
        assert "TKT-MISSING" in resp.json()["detail"]

    def test_assign_409_when_wrong_status(self, client, mock_triage_handler):
        mock_triage_handler.assign = AsyncMock(
            side_effect=ValueError("Ticket TKT-001 is not in PENDING_REVIEW status (current: resolved).")
        )

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/assign",
            json={"assign_to": "noc.engineer01"},
        )
        assert resp.status_code == 409
        assert "PENDING_REVIEW" in resp.json()["detail"]

    def test_assign_422_when_assign_to_missing(self, client, mock_triage_handler):
        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/assign",
            json={},  # assign_to is required
        )
        assert resp.status_code == 422

    def test_assign_422_when_assign_to_empty(self, client, mock_triage_handler):
        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/assign",
            json={"assign_to": ""},  # min_length=1
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /{ticket_id}/manual-resolve
# ---------------------------------------------------------------------------

class TestManualResolveEndpoint:

    _VALID_PAYLOAD = {
        "resolved_by": "noc.engineer01",
        "resolution_steps": ["Checked cable", "Re-seated E1 connector", "Confirmed recovery"],
        "sop_reference": "SOP-RAN-004",
        "primary_cause": "Physical cable fault at DDF",
        "resolution_code": "Hardware Replacement",
        "notes": "E1 cable was unplugged at DDF panel during civil works.",
    }

    def test_manual_resolve_returns_200(self, client, mock_triage_handler):
        mock_triage_handler.manual_resolve = AsyncMock(return_value=_resolve_result())

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/manual-resolve",
            json=self._VALID_PAYLOAD,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == TelcoTicketStatus.RESOLVED.value
        assert data["indexed_as_training_signal"] is True

    def test_manual_resolve_404_when_ticket_missing(self, client, mock_triage_handler):
        mock_triage_handler.manual_resolve = AsyncMock(
            side_effect=TicketNotFoundError("TKT-GONE")
        )

        resp = client.post(
            "/api/v1/telco-tickets/TKT-GONE/manual-resolve",
            json=self._VALID_PAYLOAD,
        )
        assert resp.status_code == 404

    def test_manual_resolve_409_when_wrong_status(self, client, mock_triage_handler):
        mock_triage_handler.manual_resolve = AsyncMock(
            side_effect=ValueError(
                "Ticket TKT-001 cannot be manually resolved from status 'resolved'."
            )
        )

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/manual-resolve",
            json=self._VALID_PAYLOAD,
        )
        assert resp.status_code == 409

    def test_manual_resolve_422_when_steps_empty(self, client, mock_triage_handler):
        payload = {**self._VALID_PAYLOAD, "resolution_steps": []}
        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/manual-resolve",
            json=payload,
        )
        assert resp.status_code == 422

    def test_manual_resolve_422_when_resolved_by_missing(self, client, mock_triage_handler):
        payload = {k: v for k, v in self._VALID_PAYLOAD.items() if k != "resolved_by"}
        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/manual-resolve",
            json=payload,
        )
        assert resp.status_code == 422

    def test_manual_resolve_without_optional_fields(self, client, mock_triage_handler):
        """Minimal payload (no sop_reference / primary_cause / notes) is valid."""
        result = ManualResolveResult(
            ticket_id="TKT-001",
            new_status=TelcoTicketStatus.RESOLVED.value,
            message="Manually resolved.",
            executed_steps=["Rebooted NodeB"],
            sop_reference=None,
            resolved_by="noc.engineer02",
            resolved_at=datetime.utcnow(),
            indexed_as_training_signal=False,
        )
        mock_triage_handler.manual_resolve = AsyncMock(return_value=result)

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/manual-resolve",
            json={
                "resolved_by":      "noc.engineer02",
                "resolution_steps": ["Rebooted NodeB"],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["sop_reference"] is None

    def test_manual_resolve_executed_steps_in_response(self, client, mock_triage_handler):
        mock_triage_handler.manual_resolve = AsyncMock(return_value=_resolve_result())

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/manual-resolve",
            json=self._VALID_PAYLOAD,
        )
        steps = resp.json()["executed_steps"]
        assert len(steps) == 3

    def test_manual_resolve_not_indexed_reflected_in_response(self, client, mock_triage_handler):
        result = _resolve_result()
        # Simulate Chroma failure — signal not indexed
        result = result.model_copy(update={"indexed_as_training_signal": False})
        mock_triage_handler.manual_resolve = AsyncMock(return_value=result)

        resp = client.post(
            "/api/v1/telco-tickets/TKT-001/manual-resolve",
            json=self._VALID_PAYLOAD,
        )
        assert resp.json()["indexed_as_training_signal"] is False
