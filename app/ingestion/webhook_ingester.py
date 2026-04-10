import hashlib
import hmac

from app.ingestion.base import BaseIngester
from app.ingestion.normalizer import TicketNormalizer
from app.models.ticket import TicketIn


class WebhookIngester(BaseIngester):
    """Validates HMAC signature and normalises webhook payloads."""

    def __init__(self, secret: str):
        self._secret = secret.encode()
        self._normalizer = TicketNormalizer()

    def verify_signature(self, payload_bytes: bytes, signature_header: str) -> bool:
        expected = hmac.new(self._secret, payload_bytes, hashlib.sha256).hexdigest()
        received = signature_header.removeprefix("sha256=")
        return hmac.compare_digest(expected, received)

    async def ingest(self, raw_payload: dict) -> TicketIn:
        return self._normalizer.normalize(raw_payload, source="webhook")
