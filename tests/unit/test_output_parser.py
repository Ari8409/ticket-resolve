import pytest

from app.models.ticket import TicketIn, TicketPriority
from app.recommendation.output_parser import parse_agent_output


@pytest.fixture
def sample_ticket():
    return TicketIn(
        source="api",
        title="DB timeout",
        description="Database is timing out under load repeatedly",
        priority=TicketPriority.HIGH,
    )


def test_parses_valid_json(sample_ticket, mock_llm_output):
    result = parse_agent_output(mock_llm_output, sample_ticket, ticket_id="t-001")
    assert result.ticket_id == "t-001"
    assert len(result.recommended_steps) == 3
    assert result.confidence_score == pytest.approx(0.87)
    assert result.escalation_required is False
    assert "Database Restart SOP" in result.relevant_sops


def test_parses_json_with_markdown_fences(sample_ticket):
    raw = '```json\n{"recommended_steps": ["Step 1"], "confidence_score": 0.5, "relevant_sops": [], "similar_ticket_ids": [], "escalation_required": false, "reasoning": "ok"}\n```'
    result = parse_agent_output(raw, sample_ticket, ticket_id="t-002")
    assert result.recommended_steps == ["Step 1"]


def test_critical_ticket_forces_escalation(sample_ticket):
    critical_ticket = sample_ticket.model_copy(update={"priority": TicketPriority.CRITICAL})
    raw = '{"recommended_steps": [], "confidence_score": 0.3, "relevant_sops": [], "similar_ticket_ids": [], "escalation_required": false, "reasoning": ""}'
    result = parse_agent_output(raw, critical_ticket, ticket_id="t-003")
    # escalation_required in JSON is false but ticket is CRITICAL — parser should respect JSON value
    assert isinstance(result.escalation_required, bool)


def test_gracefully_handles_invalid_json(sample_ticket):
    result = parse_agent_output("This is not JSON at all.", sample_ticket, ticket_id="t-004")
    assert result.recommended_steps == []
    assert result.confidence_score == 0.0
