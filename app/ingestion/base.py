from abc import ABC, abstractmethod
from typing import Any

from app.models.ticket import TicketIn


class BaseIngester(ABC):
    @abstractmethod
    async def ingest(self, raw_payload: Any) -> TicketIn:
        """Parse raw source payload into a canonical TicketIn."""
        ...
