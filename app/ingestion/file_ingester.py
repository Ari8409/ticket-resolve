import io
import json
from typing import AsyncIterator

import pandas as pd

from app.ingestion.base import BaseIngester
from app.ingestion.normalizer import TicketNormalizer
from app.models.ticket import TicketIn


class FileIngester(BaseIngester):
    """Parses CSV, JSON (array), or XLSX file content into TicketIn records."""

    def __init__(self):
        self._normalizer = TicketNormalizer()

    async def ingest(self, raw_payload: dict) -> TicketIn:
        """Single-record ingest from a dict (used as fallback)."""
        return self._normalizer.normalize(raw_payload, source="file")

    async def ingest_bytes(self, content: bytes, filename: str) -> AsyncIterator[TicketIn]:
        """Yield TicketIn records from file bytes."""
        ext = filename.rsplit(".", 1)[-1].lower()

        if ext == "json":
            records = json.loads(content)
            if isinstance(records, dict):
                records = [records]
        elif ext == "csv":
            df = pd.read_csv(io.BytesIO(content))
            records = df.where(pd.notna(df), None).to_dict(orient="records")
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(content))
            records = df.where(pd.notna(df), None).to_dict(orient="records")
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        for record in records:
            yield self._normalizer.normalize({k: v for k, v in record.items() if v is not None}, source="file")
