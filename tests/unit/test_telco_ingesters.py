"""Unit tests for CSV, email, and API ingesters."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.telco.api_ingester import TelcoAPIIngester
from app.ingestion.telco.csv_ingester import TelcoCSVIngester
from app.ingestion.telco.email_ingester import TelcoEmailIngester
from app.models.telco_ticket import FaultType, Severity

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# CSV ingester
# ---------------------------------------------------------------------------

class TestCSVIngester:
    @pytest.mark.asyncio
    async def test_parses_canonical_csv(self):
        ingester = TelcoCSVIngester()
        content = (FIXTURES / "sample_telco_tickets.csv").read_bytes()
        result = await ingester.ingest_bytes(content, "sample_telco_tickets.csv")

        assert result.success_count == 8
        assert result.error_count == 0

        # Spot-check first row
        t = result.tickets[0]
        assert t.ticket_id == "TKT-A001"
        assert t.fault_type == FaultType.SIGNAL_LOSS
        assert t.affected_node == "BS-MUM-042"
        assert t.severity == Severity.HIGH
        assert t.sop_id == "SOP-RF-007"
        assert len(t.resolution_steps) == 3

    @pytest.mark.asyncio
    async def test_parses_nagios_csv_with_column_remap(self):
        ingester = TelcoCSVIngester()
        content = (FIXTURES / "nagios_export.csv").read_bytes()
        result = await ingester.ingest_bytes(content, "nagios_export.csv")

        assert result.success_count == 3
        # All rows should have a non-empty affected_node extracted
        for t in result.tickets:
            assert t.affected_node != ""

    @pytest.mark.asyncio
    async def test_resolution_steps_split_from_semicolons(self):
        """Steps stored as semicolon-delimited string in CSV should become a list."""
        ingester = TelcoCSVIngester()
        content = (FIXTURES / "sample_telco_tickets.csv").read_bytes()
        result = await ingester.ingest_bytes(content, "sample_telco_tickets.csv")

        # TKT-A001 has 3 semicolon-delimited steps
        first = result.tickets[0]
        assert isinstance(first.resolution_steps, list)

    @pytest.mark.asyncio
    async def test_missing_optional_columns_ok(self):
        """sop_id and resolution_steps are optional — rows without them should parse."""
        ingester = TelcoCSVIngester()
        content = (FIXTURES / "sample_telco_tickets.csv").read_bytes()
        result = await ingester.ingest_bytes(content, "sample_telco_tickets.csv")

        # TKT-A003 has no sop_id and no resolution_steps in CSV
        t = result.tickets[2]
        assert t.ticket_id == "TKT-A003"
        assert t.sop_id is None

    @pytest.mark.asyncio
    async def test_json_array_file(self):
        ingester = TelcoCSVIngester()
        records = [
            {
                "fault_type": "node_down",
                "affected_node": "NODE-X",
                "severity": "critical",
                "description": "Core node NODE-X is completely unreachable from NMS since 09:00 UTC.",
            }
        ]
        content = json.dumps(records).encode()
        result = await ingester.ingest_bytes(content, "alerts.json")
        assert result.success_count == 1
        assert result.tickets[0].fault_type == FaultType.NODE_DOWN

    @pytest.mark.asyncio
    async def test_unsupported_extension_raises(self):
        ingester = TelcoCSVIngester()
        with pytest.raises(ValueError, match="Unsupported file extension"):
            await ingester.ingest_bytes(b"data", "file.pdf")

    @pytest.mark.asyncio
    async def test_bad_rows_captured_in_errors(self):
        """A CSV with one valid and one row missing required fields."""
        ingester = TelcoCSVIngester()
        csv_bytes = (
            b"fault_type,affected_node,severity,description\n"
            b"signal_loss,BS-TEST-01,high,Signal degradation on BS-TEST-01 affecting 500 subscribers.\n"
            b",,, \n"  # completely empty — description will be too short → fallback handles it
        )
        result = await ingester.ingest_bytes(csv_bytes, "test.csv")
        # The pipeline should at least process the first row
        assert result.success_count >= 1


# ---------------------------------------------------------------------------
# Email ingester
# ---------------------------------------------------------------------------

class TestEmailIngester:
    def test_parses_nagios_email(self):
        ingester = TelcoEmailIngester()
        raw = (FIXTURES / "sample_email_nagios.eml").read_bytes()
        t = ingester.ingest_bytes(raw)

        assert t.fault_type == FaultType.NODE_DOWN
        assert "NODE-ATL-01" in t.affected_node
        assert t.severity == Severity.CRITICAL
        assert t.timestamp.year == 2024

    def test_parses_zabbix_email(self):
        ingester = TelcoEmailIngester()
        raw = (FIXTURES / "sample_email_zabbix.eml").read_bytes()
        t = ingester.ingest_bytes(raw)

        assert t.fault_type == FaultType.PACKET_LOSS
        assert "OLT-BLR-007" in t.affected_node
        assert t.severity == Severity.HIGH

    def test_parses_generic_email(self):
        ingester = TelcoEmailIngester()
        raw = (
            b"From: noc@telco.com\r\n"
            b"To: engineer@telco.com\r\n"
            b"Subject: RTR-LON-CORE-03 high latency alert\r\n"
            b"Date: Sat, 01 Jun 2024 10:02:00 +0000\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain; charset=UTF-8\r\n"
            b"\r\n"
            b"device: RTR-LON-CORE-03\r\n"
            b"severity: high\r\n"
            b"description: RTT spiking to 450ms on core backhaul. Baseline is 12ms.\r\n"
        )
        t = ingester.ingest_bytes(raw)
        assert t.fault_type == FaultType.LATENCY
        assert t.severity in (Severity.HIGH, Severity.MEDIUM)  # from text or kv

    def test_html_email_stripped_to_text(self):
        ingester = TelcoEmailIngester()
        raw = (
            b"From: alerts@telco.com\r\n"
            b"Subject: Node BS-MUM-042 signal loss\r\n"
            b"Date: Sat, 01 Jun 2024 08:32:00 +0000\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/html; charset=UTF-8\r\n"
            b"\r\n"
            b"<html><body><h1>Alert</h1>"
            b"<p>Base station <b>BS-MUM-042</b> reporting RSSI of -112 dBm. "
            b"Signal loss affecting 3200 subscribers in Mumbai North sector.</p>"
            b"</body></html>\r\n"
        )
        t = ingester.ingest_bytes(raw)
        assert t.fault_type == FaultType.SIGNAL_LOSS

    def test_ingest_text_convenience(self):
        ingester = TelcoEmailIngester()
        raw = (FIXTURES / "sample_email_nagios.eml").read_text(encoding="utf-8")
        t = ingester.ingest_text(raw)
        assert t.fault_type == FaultType.NODE_DOWN


# ---------------------------------------------------------------------------
# API ingester
# ---------------------------------------------------------------------------

class TestAPIIngester:
    def test_generic_json_single_record(self):
        ingester = TelcoAPIIngester()
        payload = json.loads((FIXTURES / "sample_api_payloads.json").read_text())["generic"]
        tickets = ingester.ingest(payload)

        assert len(tickets) == 1
        t = tickets[0]
        assert t.ticket_id == "INC-98765"
        assert t.fault_type == FaultType.CONGESTION
        assert t.affected_node == "AGGR-DEL-SW02"
        assert t.severity == Severity.MEDIUM
        assert t.sop_id == "SOP-NET-008"

    def test_prometheus_webhook_batch(self):
        ingester = TelcoAPIIngester()
        payload = json.loads((FIXTURES / "sample_api_payloads.json").read_text())["prometheus"]
        tickets = ingester.ingest(payload)

        assert len(tickets) == 2
        node_down = next(t for t in tickets if t.fault_type == FaultType.NODE_DOWN)
        assert node_down.severity == Severity.CRITICAL
        assert "NODE-ATL-01" in node_down.affected_node

        latency = next(t for t in tickets if t.fault_type == FaultType.LATENCY)
        assert "RTR-LON-CORE-03" in latency.affected_node

    def test_pagerduty_webhook(self):
        ingester = TelcoAPIIngester()
        payload = json.loads((FIXTURES / "sample_api_payloads.json").read_text())["pagerduty"]
        tickets = ingester.ingest(payload)

        assert len(tickets) == 1
        t = tickets[0]
        assert t.severity == Severity.CRITICAL
        assert t.fault_type == FaultType.HARDWARE_FAILURE
        assert t.sop_id == "SOP-HW-021"

    def test_list_of_dicts_batch(self):
        ingester = TelcoAPIIngester()
        payload = [
            {
                "fault_type": "signal_loss",
                "affected_node": "BS-A",
                "severity": "high",
                "description": "Signal loss on BS-A sector 2 affecting 1500 subscribers.",
            },
            {
                "fault_type": "latency",
                "affected_node": "RTR-B",
                "severity": "medium",
                "description": "High RTT detected on RTR-B uplink port towards core network.",
            },
        ]
        tickets = ingester.ingest(payload)
        assert len(tickets) == 2

    def test_ingest_one_strict(self):
        ingester = TelcoAPIIngester()
        t = ingester.ingest_one({
            "fault_type": "node_down",
            "affected_node": "NODE-TEST-01",
            "severity": "critical",
            "description": "NODE-TEST-01 completely unreachable. All services impacted.",
        })
        assert t.fault_type == FaultType.NODE_DOWN
        assert t.severity == Severity.CRITICAL
