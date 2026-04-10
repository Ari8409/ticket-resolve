"""
Unit tests for ReviewHandler — approve / override / escalate paths.

All external dependencies (repo, SOP retriever, Chroma feedback indexer)
are mocked via AsyncMock so no DB or network is required.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import TicketNotFoundError
from app.models.review import ReviewAction, ReviewRequest, ReviewResult
from app.models.telco_ticket import TelcoTicketStatus
from app.review.handler import ReviewHandler, _append_remark, _dict_to_create


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TICKET_DICT = {
    "ticket_id":    "TKT-AABBCCDD",
    "affected_node": "LTE_ENB_780321",
    "severity":     "major",
    "fault_type":   "hardware_failure",
    "description":  "LTE_ENB_780321*equipmentAlarm/HW Fault*1*Hardware failure detected\n\nHW fault on LTE node.",
    "status":       "resolved",
    "timestamp":    "2025-11-27T00:00:00",
    "alarm_name":   "HW Fault",
    "alarm_category": "equipmentAlarm",
    "network_type": "4G",
    "object_class": "A2",
    "location_details": "209 Hougang Street 21",
    "primary_cause": "Hardware Fault",
    "resolution":   "Replaced faulty module",
    "resolution_code": "Hardware Replacement",
    "sop_id":       "SOP-HW-001",
    "remarks":      None,
    "title":        "A2 LTE_ENB_780321",
}

DISPATCH_DECISION = {
    "recommended_steps": ["Check hardware logs", "Replace faulty module", "Re-test connectivity"],
    "relevant_sops":     ["SOP-HW-001"],
    "dispatch_mode":     "on_site",
    "confidence_score":  0.91,
    "natural_language_summary": "Hardware fault on LTE node — on-site replacement required.",
    "ranked_sops": [],
    "short_circuited": False,
}


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get = AsyncMock(return_value=TICKET_DICT)
    repo.get_dispatch_decision = AsyncMock(return_value=DISPATCH_DECISION)
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_sop_retriever():
    retriever = MagicMock()
    retriever.get_sop_steps_by_id = AsyncMock(
        return_value=["Power-cycle the node", "Run diagnostics", "Re-seat hardware"]
    )
    return retriever


@pytest.fixture
def mock_feedback_indexer():
    indexer = MagicMock()
    indexer.index_resolved = AsyncMock()
    return indexer


@pytest.fixture
def handler(mock_repo, mock_sop_retriever, mock_feedback_indexer):
    return ReviewHandler(
        repo=mock_repo,
        sop_retriever=mock_sop_retriever,
        feedback_indexer=mock_feedback_indexer,
    )


# ---------------------------------------------------------------------------
# APPROVE path
# ---------------------------------------------------------------------------

class TestApprove:
    @pytest.mark.asyncio
    async def test_approve_returns_review_result(self, handler):
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")
        result = await handler.handle("TKT-AABBCCDD", req)

        assert isinstance(result, ReviewResult)
        assert result.action_taken == ReviewAction.APPROVE
        assert result.ticket_id == "TKT-AABBCCDD"

    @pytest.mark.asyncio
    async def test_approve_sets_resolved_status(self, handler):
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.new_status == TelcoTicketStatus.RESOLVED.value

    @pytest.mark.asyncio
    async def test_approve_records_executed_steps(self, handler):
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.executed_steps == DISPATCH_DECISION["recommended_steps"]

    @pytest.mark.asyncio
    async def test_approve_records_sop_from_decision(self, handler):
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.sop_applied == "SOP-HW-001"

    @pytest.mark.asyncio
    async def test_approve_calls_repo_update(self, handler, mock_repo):
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")
        await handler.handle("TKT-AABBCCDD", req)

        mock_repo.update.assert_awaited_once()
        call_args = mock_repo.update.call_args
        patch_arg = call_args[0][1]
        assert patch_arg.status == TelcoTicketStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_approve_indexes_training_signal(self, handler, mock_feedback_indexer):
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")
        result = await handler.handle("TKT-AABBCCDD", req)

        mock_feedback_indexer.index_resolved.assert_awaited_once()
        assert result.indexed_as_training_signal is True

    @pytest.mark.asyncio
    async def test_approve_still_succeeds_when_chroma_indexing_fails(
        self, mock_repo, mock_sop_retriever
    ):
        """Chroma failure is swallowed — ticket still gets RESOLVED."""
        failing_indexer = MagicMock()
        failing_indexer.index_resolved = AsyncMock(side_effect=RuntimeError("Chroma down"))

        handler = ReviewHandler(
            repo=mock_repo,
            sop_retriever=mock_sop_retriever,
            feedback_indexer=failing_indexer,
        )
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.new_status == TelcoTicketStatus.RESOLVED.value
        assert result.indexed_as_training_signal is False

    @pytest.mark.asyncio
    async def test_approve_raises_when_ticket_not_found(self, mock_repo, mock_sop_retriever, mock_feedback_indexer):
        mock_repo.get = AsyncMock(return_value=None)
        handler = ReviewHandler(
            repo=mock_repo,
            sop_retriever=mock_sop_retriever,
            feedback_indexer=mock_feedback_indexer,
        )
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")

        with pytest.raises(TicketNotFoundError):
            await handler.handle("TKT-NOTFOUND", req)

    @pytest.mark.asyncio
    async def test_approve_raises_when_no_dispatch_decision(self, mock_repo, mock_sop_retriever, mock_feedback_indexer):
        mock_repo.get_dispatch_decision = AsyncMock(return_value=None)
        handler = ReviewHandler(
            repo=mock_repo,
            sop_retriever=mock_sop_retriever,
            feedback_indexer=mock_feedback_indexer,
        )
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by="alice.noc")

        with pytest.raises(ValueError, match="No dispatch decision"):
            await handler.handle("TKT-AABBCCDD", req)

    @pytest.mark.asyncio
    async def test_approve_without_reviewer_name(self, handler):
        """reviewed_by is optional — should not fail."""
        req = ReviewRequest(action=ReviewAction.APPROVE, reviewed_by=None)
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.new_status == TelcoTicketStatus.RESOLVED.value
        assert result.reviewed_by is None


# ---------------------------------------------------------------------------
# OVERRIDE path
# ---------------------------------------------------------------------------

class TestOverride:
    @pytest.mark.asyncio
    async def test_override_returns_review_result(self, handler):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        assert isinstance(result, ReviewResult)
        assert result.action_taken == ReviewAction.OVERRIDE

    @pytest.mark.asyncio
    async def test_override_sets_in_progress_status(self, handler):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.new_status == TelcoTicketStatus.IN_PROGRESS.value

    @pytest.mark.asyncio
    async def test_override_loads_steps_from_chosen_sop(self, handler, mock_sop_retriever):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        mock_sop_retriever.get_sop_steps_by_id.assert_awaited_once_with("SOP-RF-005")
        assert result.executed_steps == [
            "Power-cycle the node", "Run diagnostics", "Re-seat hardware"
        ]

    @pytest.mark.asyncio
    async def test_override_records_sop_id(self, handler):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.sop_applied == "SOP-RF-005"

    @pytest.mark.asyncio
    async def test_override_does_not_index_training_signal(self, handler, mock_feedback_indexer):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        mock_feedback_indexer.index_resolved.assert_not_awaited()
        assert result.indexed_as_training_signal is False

    @pytest.mark.asyncio
    async def test_override_updates_repo_with_new_steps(self, handler, mock_repo):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
        )
        await handler.handle("TKT-AABBCCDD", req)

        mock_repo.update.assert_awaited_once()
        patch_arg = mock_repo.update.call_args[0][1]
        assert patch_arg.status == TelcoTicketStatus.IN_PROGRESS
        assert patch_arg.sop_id == "SOP-RF-005"
        assert patch_arg.resolution_steps == [
            "Power-cycle the node", "Run diagnostics", "Re-seat hardware"
        ]

    @pytest.mark.asyncio
    async def test_override_raises_without_sop_id(self, handler):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id=None,
        )
        with pytest.raises(ValueError, match="override_sop_id is required"):
            await handler.handle("TKT-AABBCCDD", req)

    @pytest.mark.asyncio
    async def test_override_raises_when_sop_not_found(self, mock_repo, mock_feedback_indexer):
        retriever = MagicMock()
        retriever.get_sop_steps_by_id = AsyncMock(return_value=[])
        handler = ReviewHandler(
            repo=mock_repo,
            sop_retriever=retriever,
            feedback_indexer=mock_feedback_indexer,
        )
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-NONEXISTENT",
        )
        with pytest.raises(ValueError, match="not found in the knowledge base"):
            await handler.handle("TKT-AABBCCDD", req)

    @pytest.mark.asyncio
    async def test_override_appends_notes_to_remarks(self, handler, mock_repo):
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
            override_notes="Original SOP inapplicable — Ericsson variant not covered.",
        )
        await handler.handle("TKT-AABBCCDD", req)

        patch_arg = mock_repo.update.call_args[0][1]
        assert "Ericsson variant not covered" in patch_arg.remarks

    @pytest.mark.asyncio
    async def test_override_raises_when_ticket_not_found(self, mock_repo, mock_sop_retriever, mock_feedback_indexer):
        mock_repo.get = AsyncMock(return_value=None)
        handler = ReviewHandler(
            repo=mock_repo,
            sop_retriever=mock_sop_retriever,
            feedback_indexer=mock_feedback_indexer,
        )
        req = ReviewRequest(
            action=ReviewAction.OVERRIDE,
            reviewed_by="bob.noc",
            override_sop_id="SOP-RF-005",
        )
        with pytest.raises(TicketNotFoundError):
            await handler.handle("TKT-NOTFOUND", req)


# ---------------------------------------------------------------------------
# ESCALATE path
# ---------------------------------------------------------------------------

class TestEscalate:
    @pytest.mark.asyncio
    async def test_escalate_returns_review_result(self, handler):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note="Repeated failure, possible systematic issue.",
            escalate_to="senior-rf-team",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        assert isinstance(result, ReviewResult)
        assert result.action_taken == ReviewAction.ESCALATE

    @pytest.mark.asyncio
    async def test_escalate_sets_escalated_status(self, handler):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note="Systematic failure pattern.",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.new_status == TelcoTicketStatus.ESCALATED.value

    @pytest.mark.asyncio
    async def test_escalate_records_escalated_to(self, handler):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalate_to="rf-tier2",
            escalation_note="Need RF specialist.",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.escalated_to == "rf-tier2"

    @pytest.mark.asyncio
    async def test_escalate_does_not_index_training_signal(self, handler, mock_feedback_indexer):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note="Complex case.",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        mock_feedback_indexer.index_resolved.assert_not_awaited()
        assert result.indexed_as_training_signal is False

    @pytest.mark.asyncio
    async def test_escalate_has_no_executed_steps(self, handler):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note="Cannot resolve remotely.",
        )
        result = await handler.handle("TKT-AABBCCDD", req)

        assert result.executed_steps == []

    @pytest.mark.asyncio
    async def test_escalate_updates_repo_status(self, handler, mock_repo):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note="Root cause unknown.",
        )
        await handler.handle("TKT-AABBCCDD", req)

        mock_repo.update.assert_awaited_once()
        patch_arg = mock_repo.update.call_args[0][1]
        assert patch_arg.status == TelcoTicketStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_escalate_appends_note_to_remarks(self, handler, mock_repo):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note="Site power instability suspected.",
            escalate_to="field-ops",
        )
        await handler.handle("TKT-AABBCCDD", req)

        patch_arg = mock_repo.update.call_args[0][1]
        assert "Site power instability suspected" in patch_arg.remarks
        assert "field-ops" in patch_arg.remarks

    @pytest.mark.asyncio
    async def test_escalate_uses_default_escalation_note(self, handler, mock_repo):
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note=None,
        )
        await handler.handle("TKT-AABBCCDD", req)

        patch_arg = mock_repo.update.call_args[0][1]
        assert "no specific note provided" in patch_arg.remarks.lower()

    @pytest.mark.asyncio
    async def test_escalate_raises_when_ticket_not_found(self, mock_repo, mock_sop_retriever, mock_feedback_indexer):
        mock_repo.get = AsyncMock(return_value=None)
        handler = ReviewHandler(
            repo=mock_repo,
            sop_retriever=mock_sop_retriever,
            feedback_indexer=mock_feedback_indexer,
        )
        req = ReviewRequest(
            action=ReviewAction.ESCALATE,
            reviewed_by="charlie.noc",
            escalation_note="Unclear fault type.",
        )
        with pytest.raises(TicketNotFoundError):
            await handler.handle("TKT-NOTFOUND", req)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_append_remark_to_none_returns_new_line(self):
        result = _append_remark(None, "New note here.")
        assert result == "New note here."

    def test_append_remark_to_existing_creates_two_lines(self):
        result = _append_remark("Old note.", "New note here.")
        assert result == "Old note.\nNew note here."

    def test_append_remark_preserves_existing_content(self):
        existing = "Line 1.\nLine 2."
        result = _append_remark(existing, "Line 3.")
        assert result.startswith("Line 1.\nLine 2.")
        assert "Line 3." in result

    def test_dict_to_create_round_trips_required_fields(self):
        ticket = _dict_to_create(TICKET_DICT)
        assert ticket.ticket_id == TICKET_DICT["ticket_id"]
        assert ticket.affected_node == TICKET_DICT["affected_node"]
        assert ticket.description == TICKET_DICT["description"]

    def test_dict_to_create_handles_string_enums(self):
        """Severity and FaultType passed as strings (as stored in DB) are coerced."""
        ticket = _dict_to_create(TICKET_DICT)
        from app.models.telco_ticket import FaultType, Severity
        assert ticket.severity == Severity.MAJOR
        assert ticket.fault_type == FaultType.HARDWARE_FAILURE

    def test_dict_to_create_maps_optional_ctts_fields(self):
        ticket = _dict_to_create(TICKET_DICT)
        assert ticket.alarm_name == "HW Fault"
        assert ticket.network_type == "4G"
        assert ticket.location_details == "209 Hougang Street 21"
        assert ticket.primary_cause == "Hardware Fault"
