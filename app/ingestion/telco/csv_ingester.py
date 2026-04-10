"""
CSV / XLSX ingester for telco tickets.

Handles exports from common NOC tooling:
  - Generic telco NOC CSV (any header naming)
  - Nagios / Icinga CSV exports
  - Zabbix problem CSV exports
  - Prometheus / Alertmanager CSV dumps
  - Excel (.xlsx / .xls) variants of the above

Each row is independently normalised; invalid rows are skipped and logged.
A summary of skipped rows is available via ``IngestionResult.errors``.
"""
from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

import pandas as pd

from app.ingestion.telco.normalizer import TelcoNormalizer
from app.models.telco_ticket import TelcoTicketCreate

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column remapping tables for well-known NOC tool exports
# Keys are source column names; values are the canonical alias names that
# TelcoNormalizer already understands.
# ---------------------------------------------------------------------------

_NAGIOS_COLUMN_MAP: dict[str, str] = {
    "HOST NAME":         "hostname",
    "SERVICE":           "fault_category",
    "STATE":             "severity",
    "DATE/TIME":         "timestamp",
    "DURATION":          "_duration",         # informational, kept as-is
    "INFORMATION":       "description",
    "PLUGIN OUTPUT":     "alarm_text",
}

_ZABBIX_COLUMN_MAP: dict[str, str] = {
    "Host":              "hostname",
    "Problem":           "description",
    "Severity":          "severity",
    "Duration":          "_duration",
    "Time":              "timestamp",
    "Tags":              "_tags",
    "Operational data":  "alarm_text",
}

_PROMETHEUS_COLUMN_MAP: dict[str, str] = {
    "alertname":         "alert_name",
    "instance":          "hostname",
    "job":               "fault_category",
    "severity":          "severity",
    "summary":           "description",
    "description":       "alarm_text",
    "startsAt":          "timestamp",
}

# Ordered list of (detector_columns, remap_dict).
# The first matching format is applied.
_FORMAT_DETECTORS: list[tuple[set[str], dict[str, str]]] = [
    ({"HOST NAME", "SERVICE", "STATE", "PLUGIN OUTPUT"},   _NAGIOS_COLUMN_MAP),
    ({"Host", "Problem", "Severity", "Operational data"},  _ZABBIX_COLUMN_MAP),
    ({"alertname", "instance", "startsAt"},                _PROMETHEUS_COLUMN_MAP),
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class CSVIngestionResult:
    tickets: list[TelcoTicketCreate] = field(default_factory=list)
    errors:  list[dict]              = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.tickets)

    @property
    def error_count(self) -> int:
        return len(self.errors)


# ---------------------------------------------------------------------------
# Ingester
# ---------------------------------------------------------------------------

class TelcoCSVIngester:
    """
    Reads CSV, XLSX, or JSON-array files and yields TelcoTicketCreate records.

    Example::

        ingester = TelcoCSVIngester()
        result = await ingester.ingest_bytes(content, "export.csv")
        for ticket in result.tickets:
            print(ticket.ticket_id, ticket.fault_type)
    """

    def __init__(self) -> None:
        self._normalizer = TelcoNormalizer()

    # ── private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _detect_and_remap(df: pd.DataFrame) -> pd.DataFrame:
        """Apply column remapping if the export matches a known NOC format."""
        cols = set(df.columns)
        for required_cols, remap in _FORMAT_DETECTORS:
            if required_cols.issubset(cols):
                log.debug("Detected NOC format with columns: %s", required_cols)
                return df.rename(columns=remap)
        return df  # no known format — pass through as-is

    @staticmethod
    def _read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext == "csv":
            return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
        if ext in ("xlsx", "xls"):
            return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
        if ext == "json":
            records = json.loads(content)
            if isinstance(records, dict):
                records = [records]
            return pd.DataFrame(records)
        raise ValueError(f"Unsupported file extension: .{ext}. Expected csv, xlsx, xls, or json.")

    def _process_row(self, row_dict: dict, row_index: int) -> TelcoTicketCreate:
        # Drop empty-string values so alias lookup treats them as missing
        cleaned = {k: v for k, v in row_dict.items() if v not in ("", None, "nan", "NaN")}
        return self._normalizer.normalize(cleaned, source="csv")

    # ── public API ─────────────────────────────────────────────────────────

    async def ingest_bytes(self, content: bytes, filename: str) -> CSVIngestionResult:
        """
        Parse file bytes into TelcoTicketCreate records.

        Returns a CSVIngestionResult with .tickets (successes) and
        .errors (list of {row, error} dicts for failed rows).
        """
        result = CSVIngestionResult()

        df = self._read_dataframe(content, filename)
        df = self._detect_and_remap(df)
        log.info("Parsed %d rows from '%s'", len(df), filename)

        for idx, row in enumerate(df.to_dict(orient="records")):
            try:
                ticket = self._process_row(row, idx)
                result.tickets.append(ticket)
            except Exception as exc:
                log.warning("Row %d skipped — %s: %s", idx, type(exc).__name__, exc)
                result.errors.append({"row": idx, "data": row, "error": str(exc)})

        log.info(
            "'%s' ingestion complete: %d ok, %d errors",
            filename, result.success_count, result.error_count,
        )
        return result

    async def ingest_file(self, path: Path) -> CSVIngestionResult:
        """Convenience wrapper that reads from a filesystem path."""
        content = path.read_bytes()
        return await self.ingest_bytes(content, path.name)

    async def iter_tickets(self, content: bytes, filename: str) -> AsyncIterator[TelcoTicketCreate]:
        """Async generator variant — yields tickets one at a time."""
        result = await self.ingest_bytes(content, filename)
        for ticket in result.tickets:
            yield ticket
