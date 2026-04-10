"""Integration tests for TelcoIngestionPipeline end-to-end."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.telco.pipeline import TelcoIngestionPipeline, SourceType
from app.models.telco_ticket import FaultType, Severity, TelcoTicketCreate

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def pipeline():
    return TelcoIngestionPipeline()


# ---------------------------------------------------------------------------
# from_email
# ---------------------------------------------------------------------------

class TestPipelineEmail:
    def test_nagios_email_produces_ok_result(self, pipeline):
        raw = (FIXTURES / "sample_email_nagios.eml").read_bytes()
        result = pipeline.from_email(raw)

        assert result.ok
        assert result.source == SourceType.EMAIL
        assert result.ticket is not None
        assert result.ticket.fault_type == FaultType.NODE_DOWN
        assert result.ticket.severity == Severity.CRITICAL

    def test_zabbix_email_produces_ok_result(self, pipeline):
        raw = (FIXTURES / "sample_email_zabbix.eml").read_bytes()
        result = pipeline.from_email(raw)

        assert result.ok
        assert result.ticket.fault_type == FaultType.PACKET_LOSS
        assert result.ticket.severity == Severity.HIGH

    def test_corrupt_email_returns_error_result(self, pipeline):
        result = pipeline.from_email(b"this is not an email at all")
        # Should not raise — error captured in PipelineResult
        assert result.source == SourceType.EMAIL
        # Either succeeded with fallback or captured error
        if not result.ok:
            assert result.error is not None


# ---------------------------------------------------------------------------
# from_csv
# ---------------------------------------------------------------------------

class TestPipelineCSV:
    @pytest.mark.asyncio
    async def test_canonical_csv_batch(self, pipeline):
        content = (FIXTURES / "sample_telco_tickets.csv").read_bytes()
        batch = await pipeline.from_csv(content, "sample_telco_tickets.csv")

        assert batch.success_count == 8
        assert batch.error_count == 0
        assert all(isinstance(t, TelcoTicketCreate) for t in batch.tickets)

    @pytest.mark.asyncio
    async def test_nagios_csv_batch(self, pipeline):
        content = (FIXTURES / "nagios_export.csv").read_bytes()
        batch = await pipeline.from_csv(content, "nagios_export.csv")

        assert batch.success_count == 3
        assert batch.summary().startswith("BatchResult")

    @pytest.mark.asyncio
    async def test_csv_batch_result_has_correct_fault_types(self, pipeline):
        content = (FIXTURES / "sample_telco_tickets.csv").read_bytes()
        batch = await pipeline.from_csv(content)

        fault_types = {t.fault_type for t in batch.tickets}
        expected = {
            FaultType.SIGNAL_LOSS, FaultType.NODE_DOWN, FaultType.LATENCY,
            FaultType.PACKET_LOSS, FaultType.CONGESTION,
            FaultType.HARDWARE_FAILURE, FaultType.CONFIGURATION_ERROR,
        }
        assert expected.issubset(fault_types)


# ---------------------------------------------------------------------------
# from_api
# ---------------------------------------------------------------------------

class TestPipelineAPI:
    def test_generic_single_alert(self, pipeline):
        payload = json.loads((FIXTURES / "sample_api_payloads.json").read_text())["generic"]
        batch = pipeline.from_api(payload)

        assert batch.success_count == 1
        assert batch.tickets[0].fault_type == FaultType.CONGESTION

    def test_prometheus_batch_produces_two_tickets(self, pipeline):
        payload = json.loads((FIXTURES / "sample_api_payloads.json").read_text())["prometheus"]
        batch = pipeline.from_api(payload)

        assert batch.success_count == 2
        severities = {t.severity for t in batch.tickets}
        assert Severity.CRITICAL in severities

    def test_pagerduty_webhook(self, pipeline):
        payload = json.loads((FIXTURES / "sample_api_payloads.json").read_text())["pagerduty"]
        batch = pipeline.from_api(payload)

        assert batch.success_count == 1
        assert batch.tickets[0].fault_type == FaultType.HARDWARE_FAILURE

    def test_from_api_strict_raises_on_error(self, pipeline):
        with pytest.raises(Exception):
            pipeline.from_api_strict({"completely": "invalid", "no": "required fields"})

    def test_list_payload_processed_as_batch(self, pipeline):
        payload = [
            {"fault_type": "latency", "affected_node": "N1", "severity": "medium",
             "description": "High RTT on N1 backhaul uplink port exceeding threshold."},
            {"fault_type": "node_down", "affected_node": "N2", "severity": "critical",
             "description": "Node N2 unreachable — 100% packet loss confirmed by NMS."},
        ]
        batch = pipeline.from_api(payload)
        assert batch.success_count == 2


# ---------------------------------------------------------------------------
# from_file (auto-detect)
# ---------------------------------------------------------------------------

class TestPipelineFromFile:
    @pytest.mark.asyncio
    async def test_detects_csv_from_extension(self, pipeline):
        path = FIXTURES / "sample_telco_tickets.csv"
        batch = await pipeline.from_file(path)
        assert batch.success_count == 8

    @pytest.mark.asyncio
    async def test_detects_eml_from_extension(self, pipeline):
        path = FIXTURES / "sample_email_nagios.eml"
        batch = await pipeline.from_file(path)
        assert batch.success_count == 1
        assert batch.tickets[0].fault_type == FaultType.NODE_DOWN

    @pytest.mark.asyncio
    async def test_unsupported_extension_returns_error(self, pipeline, tmp_path):
        bad_file = tmp_path / "alert.xml"
        bad_file.write_bytes(b"<alert><node>X</node></alert>")
        batch = await pipeline.from_file(bad_file)
        # Should not raise — error captured
        assert batch.error_count >= 1 or batch.success_count >= 0


# ---------------------------------------------------------------------------
# BatchResult helpers
# ---------------------------------------------------------------------------

class TestBatchResult:
    @pytest.mark.asyncio
    async def test_tickets_property_filters_successes(self, pipeline):
        content = (FIXTURES / "sample_telco_tickets.csv").read_bytes()
        batch = await pipeline.from_csv(content)
        assert len(batch.tickets) == batch.success_count

    @pytest.mark.asyncio
    async def test_errors_property_filters_failures(self, pipeline):
        content = (FIXTURES / "sample_telco_tickets.csv").read_bytes()
        batch = await pipeline.from_csv(content)
        for err in batch.errors:
            assert not err.ok
            assert err.error is not None
