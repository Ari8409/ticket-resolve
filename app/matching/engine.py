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

    # ------------------------------------------------------------------
    # Telco-specific indexing (TelcoTicketCreate)
    # ------------------------------------------------------------------

    def _make_telco_document(self, ticket) -> str:
        """
        Build the vector-store document text for a TelcoTicketCreate.

        The document is structured to surface the most distinctive fields
        for similarity matching: alarm name, node, fault type, description,
        and resolution details (for resolved tickets).
        """
        parts = [
            ticket.alarm_name or ticket.fault_type.value.replace("_", " ").title(),
            f"Node: {ticket.affected_node}",
            f"Fault: {ticket.fault_type.value}",
        ]
        if ticket.network_type:
            parts.append(f"Network: {ticket.network_type}")
        if ticket.alarm_category:
            parts.append(f"Category: {ticket.alarm_category}")
        parts.append(ticket.description)
        if ticket.primary_cause:
            parts.append(f"Primary Cause: {ticket.primary_cause}")
        if ticket.resolution:
            parts.append(f"Resolution: {ticket.resolution}")
        if ticket.resolution_code:
            parts.append(f"Resolution Code: {ticket.resolution_code}")
        return "\n".join(parts)

    async def index_telco_ticket(
        self,
        ticket_id: str,
        ticket,
        resolution_summary: Optional[str] = None,
        resolved: bool = False,
    ) -> None:
        """
        Embed and upsert a TelcoTicketCreate into the vector store.

        Pass ``resolved=True`` when the ticket has been fully resolved so it
        becomes eligible for ``find_similar_resolved`` training-signal queries.
        """
        doc = self._make_telco_document(ticket)
        embedding = await self._embedder.embed_text(doc)
        await self._store.upsert_ticket(
            ticket_id=ticket_id,
            embedding=embedding,
            document=doc,
            title=ticket.title or ticket.affected_node,
            priority=ticket.severity.value,
            category=ticket.alarm_category or ticket.fault_type.value,
            resolution_summary=resolution_summary,
            resolved=resolved,
        )
        log.info("Indexed telco ticket %s (resolved=%s)", ticket_id, resolved)

    async def index_raw_doc(
        self,
        doc_id: str,
        embedding_text: str,
        metadata: dict,
    ) -> None:
        """
        Embed and upsert an arbitrary document with custom metadata.

        Used by ResolutionFeedbackIndexer.index_chat_feedback() to store
        positively-rated chat exchanges with feedback_source="chat" metadata
        so they can be retrieved separately from ticket resolutions.
        """
        embedding = await self._embedder.embed_text(embedding_text)
        await self._store._col.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[embedding_text],
            metadatas=[metadata],
        )
        log.debug("Indexed raw doc %s into Chroma", doc_id)

    async def find_similar_with_filter(
        self,
        query: str,
        where: dict,
        n_results: int = 3,
    ) -> list[dict]:
        """
        Query Chroma with an explicit where-filter and return raw result dicts.

        Used to retrieve chat feedback documents (where={"feedback_source": "chat"})
        without contaminating the regular ticket similarity search paths.
        Falls back to empty list if the collection has no matching documents.
        """
        try:
            embedding = await self._embedder.embed_text(query)
            results = await self._store._col.query(
                query_embeddings=[embedding],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            if not results or not results.get("ids") or not results["ids"][0]:
                return []
            ids       = results["ids"][0]
            docs      = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            return [
                {
                    "id":       ids[i],
                    "document": docs[i] if i < len(docs) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "score":    round(1.0 - distances[i], 4) if i < len(distances) else 0.0,
                }
                for i in range(len(ids))
            ]
        except Exception as exc:
            log.warning("find_similar_with_filter failed (where=%s): %s", where, exc)
            return []
