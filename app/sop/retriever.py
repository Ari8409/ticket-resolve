import logging
from typing import Optional

from app.matching.embedder import TicketEmbedder
from app.models.recommendation import SOPMatch
from app.sop.sop_store import SOPStore

log = logging.getLogger(__name__)


class SOPRetriever:
    def __init__(self, embedder: TicketEmbedder, sop_store: SOPStore, top_k: int = 3):
        self._embedder = embedder
        self._store = sop_store
        self._top_k = top_k

    async def retrieve(self, query: str, top_k: Optional[int] = None) -> list[SOPMatch]:
        embedding = await self._embedder.embed_text(query)
        matches = await self._store.query_relevant(embedding, n_results=top_k or self._top_k)
        log.debug("SOP retrieval for query returned %d matches", len(matches))
        return matches
