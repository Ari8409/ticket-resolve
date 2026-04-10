import logging
from typing import Optional

from app.matching.embedder import TicketEmbedder
from app.matching.ticket_store import TicketStore
from app.models.recommendation import SimilarTicket
from app.models.ticket import TicketIn

log = logging.getLogger(__name__)


class MatchingEngine:
    def __init__(
        self,
        embedder: TicketEmbedder,
        ticket_store: TicketStore,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ):
        self._embedder  = embedder
        self._store     = ticket_store
        self._top_k     = top_k
        self._score_threshold = score_threshold

    def _make_document(self, ticket: TicketIn) -> str:
        parts = [ticket.title, ticket.description]
        if ticket.category:
            parts.append(f"Category: {ticket.category}")
        return "\n".join(parts)

    async def index_ticket(
        self,
        ticket_id: str,
        ticket: TicketIn,
        resolution_summary: Optional[str] = None,
        resolved: bool = False,
    ) -> None:
        """
        Embed and upsert a ticket into the vector store.

        Parameters
        ----------
        resolved:
            Pass ``True`` when indexing a historically resolved ticket so it
            becomes eligible for ``find_similar_resolved`` queries.
            Defaults to ``False`` for incoming (not-yet-resolved) tickets.
        """
        doc = self._make_document(ticket)
        embedding = await self._embedder.embed_text(doc)
        await self._store.upsert_ticket(
            ticket_id=ticket_id,
            embedding=embedding,
            document=doc,
            title=ticket.title,
            priority=ticket.priority.value,
            category=ticket.category,
            resolution_summary=resolution_summary,
            resolved=resolved,
        )
        log.info("Indexed ticket %s (resolved=%s)", ticket_id, resolved)

    async def find_similar(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> list[SimilarTicket]:
        """Return the top-k most similar tickets regardless of resolution status."""
        embedding = await self._embedder.embed_text(query)
        return await self._store.query_similar(
            embedding=embedding,
            n_results=top_k or self._top_k,
            score_threshold=self._score_threshold,
        )

    async def find_similar_resolved(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> list[SimilarTicket]:
        """
        Return the top-k most similar tickets that are marked as *resolved*.

        Only tickets indexed with ``resolved=True`` are returned, ensuring
        results represent precedents with confirmed resolution paths.
        """
        embedding = await self._embedder.embed_text(query)
        return await self._store.query_resolved_similar(
            embedding=embedding,
            n_results=top_k or self._top_k,
            score_threshold=self._score_threshold,
        )

    async def find_similar_high_priority(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> list[SimilarTicket]:
        """
        Return resolved tickets that are both similar to ``query`` AND have
        critical or high priority.

        Provides an escalation-precedent signal that is distinct from the
        general resolved-ticket search: it surfaces the most severe past
        incidents that match the current fault description, regardless of
        whether those tickets rank in the top-k of the unrestricted search.
        """
        embedding = await self._embedder.embed_text(query)
        return await self._store.query_high_priority_similar(
            embedding=embedding,
            n_results=top_k or self._top_k,
            score_threshold=self._score_threshold,
        )

    async def find_similar_for_ticket(
        self,
        ticket: TicketIn,
        top_k: Optional[int] = None,
    ) -> list[SimilarTicket]:
        doc = self._make_document(ticket)
        return await self.find_similar(doc, top_k)
