"""
TelcoIngestionPipeline — single entry point for all telco ticket sources.

                    ┌─────────────────────────────────────────┐
   email bytes ────►│                                         │
   CSV/XLSX bytes ──►│   TelcoIngestionPipeline.ingest()      │
   API JSON dict ───►│                                         ├──► list[PipelineResult]
   file path ────────►│                                         │
                    └──────────────┬──────────────────────────┘
                                   │
               ┌───────────────────┼────────────────────────┐
               ▼                   ▼                        ▼
         EmailIngester       CSVIngester              APIIngester
               │                   │                        │
               └───────────────────┴────────────────────────┘
                                   │
                            TelcoNormalizer
                                   │
                         TelcoTicketCreate  ──► (caller persists)

Each record passes through three pipeline stages:
  1. Parse      — source-specific parsing into a raw dict
  2. Normalise  — TelcoNormalizer maps raw → TelcoTicketCreate
  3. Validate   — Pydantic validation (already done by TelcoTicketCreate)

Failures at any stage are captured in PipelineResult.error rather than
raising, so one bad record doesn't abort a batch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from app.ingestion.telco.api_ingester import TelcoAPIIngester
from app.ingestion.telco.csv_ingester import TelcoCSVIngester
from app.ingestion.telco.email_ingester import TelcoEmailIngester
from app.models.telco_ticket import TelcoTicketCreate

log = logging.getLogger(__name__)


class SourceType(str, Enum):
    EMAIL = "email"
    CSV   = "csv"
    API   = "api"
    FILE  = "file"   # auto-detect from extension


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Outcome for a single ingest attempt."""
    source:    SourceType
    ticket:    Optional[TelcoTicketCreate] = None
    error:     Optional[str]              = None
    raw_hint:  Optional[str]              = None   # snippet of raw input for debugging

    @property
    def ok(self) -> bool:
        return self.ticket is not None and self.error is None


@dataclass
class BatchResult:
    """Aggregated outcome of a batch ingest call."""
    results: list[PipelineResult] = field(default_factory=list)

    @property
    def tickets(self) -> list[TelcoTicketCreate]:
        return [r.ticket for r in self.results if r.ticket]

    @property
    def errors(self) -> list[PipelineResult]:
        return [r for r in self.results if not r.ok]

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def summary(self) -> str:
        return (
            f"BatchResult: {self.success_count} ok, {self.error_count} errors "
            f"out of {len(self.results)} total"
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TelcoIngestionPipeline:
    """
    Unified ingestion pipeline for telco alert tickets from any source.

    Usage examples::

        pipeline = TelcoIngestionPipeline()

        # From email
        result = pipeline.from_email(eml_bytes)

        # From CSV file bytes
        batch = await pipeline.from_csv(csv_bytes, filename="export.csv")

        # From API JSON dict (Prometheus / PagerDuty / generic)
        batch = pipeline.from_api(webhook_body)

        # Auto-detect from file path
        batch = await pipeline.from_file(Path("alerts.csv"))
    """

    def __init__(self) -> None:
        self._email = TelcoEmailIngester()
        self._csv   = TelcoCSVIngester()
        self._api   = TelcoAPIIngester()

    # ── email ──────────────────────────────────────────────────────────────

    def from_email(self, raw_email: bytes) -> PipelineResult:
        """Parse a single RFC-2822 email into one PipelineResult."""
        try:
            ticket = self._email.ingest_bytes(raw_email)
            log.info("Email ingested → %s (%s / %s)", ticket.ticket_id, ticket.fault_type, ticket.severity)
            return PipelineResult(source=SourceType.EMAIL, ticket=ticket)
        except Exception as exc:
            log.error("Email ingest failed: %s", exc, exc_info=True)
            return PipelineResult(
                source=SourceType.EMAIL,
                error=str(exc),
                raw_hint=raw_email[:120].decode("utf-8", errors="replace"),
            )

    # ── CSV / XLSX ─────────────────────────────────────────────────────────

    async def from_csv(self, content: bytes, filename: str = "upload.csv") -> BatchResult:
        """Parse a CSV/XLSX/JSON file into a BatchResult."""
        batch = BatchResult()
        try:
            csv_result = await self._csv.ingest_bytes(content, filename)
            for ticket in csv_result.tickets:
                batch.results.append(PipelineResult(source=SourceType.CSV, ticket=ticket))
            for err in csv_result.errors:
                batch.results.append(PipelineResult(
                    source=SourceType.CSV,
                    error=err["error"],
                    raw_hint=str(err.get("data", ""))[:120],
                ))
        except Exception as exc:
            log.error("CSV batch ingest failed: %s", exc, exc_info=True)
            batch.results.append(PipelineResult(source=SourceType.CSV, error=str(exc)))

        log.info("CSV ingest '%s': %s", filename, batch.summary())
        return batch

    # ── API / webhook ──────────────────────────────────────────────────────

    def from_api(self, payload: dict | list) -> BatchResult:
        """Parse an API JSON payload (single dict or batch list) into a BatchResult."""
        batch = BatchResult()
        try:
            tickets = self._api.ingest(payload)
            for ticket in tickets:
                batch.results.append(PipelineResult(source=SourceType.API, ticket=ticket))
        except Exception as exc:
            log.error("API ingest failed: %s", exc, exc_info=True)
            batch.results.append(PipelineResult(source=SourceType.API, error=str(exc)))

        log.info("API ingest: %s", batch.summary())
        return batch

    # ── file auto-detect ───────────────────────────────────────────────────

    async def from_file(self, path: Path) -> BatchResult:
        """
        Auto-detect format from file extension and ingest.

        Supported: .csv  .xlsx  .xls  .json  .eml
        """
        ext = path.suffix.lower()
        content = path.read_bytes()

        if ext == ".eml":
            result = self.from_email(content)
            batch = BatchResult()
            batch.results.append(result)
            return batch

        if ext in (".csv", ".xlsx", ".xls", ".json"):
            return await self.from_csv(content, filename=path.name)

        # Unknown — attempt API/JSON parse as last resort
        log.warning("Unknown file extension '%s'; attempting JSON parse", ext)
        try:
            import json
            payload = json.loads(content)
            return self.from_api(payload)
        except Exception as exc:
            batch = BatchResult()
            batch.results.append(PipelineResult(
                source=SourceType.FILE,
                error=f"Unsupported file type '{ext}': {exc}",
            ))
            return batch

    # ── convenience: ingest and filter successes ───────────────────────────

    def from_api_strict(self, payload: dict | list) -> list[TelcoTicketCreate]:
        """Like from_api() but raises on any error instead of collecting them."""
        batch = self.from_api(payload)
        if batch.errors:
            msgs = [e.error for e in batch.errors]
            raise ValueError(f"Ingestion errors: {msgs}")
        return batch.tickets
