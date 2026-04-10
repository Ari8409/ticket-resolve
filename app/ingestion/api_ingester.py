from app.ingestion.base import BaseIngester
from app.models.ticket import TicketIn


class APIIngester(BaseIngester):
    """Handles direct JSON payloads from the REST API — already canonical TicketIn."""

    async def ingest(self, raw_payload: dict) -> TicketIn:
        raw_payload.setdefault("source", "api")
        return TicketIn(**raw_payload)
