import pytest

from app.ingestion.normalizer import TicketNormalizer
from app.models.ticket import TicketPriority


@pytest.fixture
def normalizer():
    return TicketNormalizer()


def test_normalizes_canonical_fields(normalizer):
    raw = {"title": "Login broken", "description": "Cannot log in since update", "priority": "high"}
    result = normalizer.normalize(raw, source="api")
    assert result.title == "Login broken"
    assert result.description == "Cannot log in since update"
    assert result.priority == TicketPriority.HIGH
    assert result.source == "api"


def test_normalizes_jira_aliases(normalizer):
    raw = {"summary": "Service down", "body": "Service unavailable since 09:00 AM", "severity": "critical"}
    result = normalizer.normalize(raw, source="webhook")
    assert result.title == "Service down"
    assert result.description == "Service unavailable since 09:00 AM"
    assert result.priority == TicketPriority.CRITICAL


def test_normalizes_p0_priority(normalizer):
    raw = {"title": "Full outage", "description": "Everything is down", "priority": "p0"}
    result = normalizer.normalize(raw, source="api")
    assert result.priority == TicketPriority.CRITICAL


def test_default_priority_when_missing(normalizer):
    raw = {"title": "Minor bug", "description": "Button color is wrong in dark mode"}
    result = normalizer.normalize(raw, source="api")
    assert result.priority == TicketPriority.MEDIUM


def test_category_extraction(normalizer):
    raw = {"title": "VPN issue", "description": "Cannot connect to VPN from home", "category": "network"}
    result = normalizer.normalize(raw, source="api")
    assert result.category == "network"


def test_unknown_fields_go_to_metadata(normalizer):
    raw = {"title": "Issue", "description": "Something broke badly", "ticket_ref": "PROJ-123"}
    result = normalizer.normalize(raw, source="api")
    assert "ticket_ref" in result.metadata


def test_fallback_title_from_long_body(normalizer):
    raw = {"body": "The production database is completely unresponsive and all queries are timing out"}
    result = normalizer.normalize(raw, source="webhook")
    assert result.title != ""
    assert len(result.title) > 0
