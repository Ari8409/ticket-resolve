"""
TicketStore — Chroma collection operations for indexed tickets.

Metadata schema per document
-----------------------------
  ticket_id          str   — primary key
  title              str
  priority           str   — TicketPriority value
  category           str   — empty string when absent (Chroma requires str)
  resolution_summary str   — empty string when not yet resolved
  resolved           bool  — True only for historically resolved tickets;
                             used by query_resolved_similar to restrict search
                             to tickets that have a confirmed resolution path

Cosine distance
---------------
Chroma stores and returns L2 distances by default when the collection is
created without an explicit distance function, but the collections in this
project are created with ``cosine`` distance (see storage/chroma_client.py).
query_similar converts distance → similarity via ``score = 1.0 - distance``.
"""
import logging
from typing import Optional

import chromadb

from app.models.recommendation import SimilarTicket

log = logging.getLogger(__name__)


class TicketStore:
    def __init__(self, collection: chromadb.AsyncCollection):
        self._col = collection

    async def upsert_ticket(
        self,
        ticket_id: str,
        embedding: list[float],
        document: str,
        title: str,
        priority: str,
        category: Optional[str],
        resolution_summary: Optional[str] = None,
        resolved: bool = False,
    ) -> None:
        """
        Insert or update a ticket in the vector store.

        Parameters
        ----------
        resolved:
            Set to True for historical tickets that have a confirmed resolution.
            Incoming (not-yet-resolved) tickets default to False.
            This flag enables ``query_resolved_similar`` to restrict search
            results to actionable precedents.
        """
        metadata: dict = {
            "ticket_id":          ticket_id,
            "title":              title,
            "priority":           priority,
            "category":           category or "",
            "resolution_summary": resolution_summary or "",
            "resolved":           resolved,
        }
        await self._col.upsert(
            ids=[ticket_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )
        log.debug("Upserted ticket %s (resolved=%s) into Chroma", ticket_id, resolved)

    async def query_similar(
        self,
        embedding: list[float],
        n_results: int = 5,
        score_threshold: float = 0.0,
    ) -> list[SimilarTicket]:
        """Return the top-n most similar tickets regardless of resolution status."""
        return await self._query(
            embedding=embedding,
            n_results=n_results,
            score_threshold=score_threshold,
            where=None,
        )

    async def query_resolved_similar(
        self,
        embedding: list[float],
        n_results: int = 3,
        score_threshold: float = 0.0,
    ) -> list[SimilarTicket]:
        """
        Return the top-n most similar tickets that are marked as resolved.

        Only tickets indexed with ``resolved=True`` are considered.  This
        ensures results represent actionable precedents with a known resolution
        path, not open or in-progress tickets.
        """
        return await self._query(
            embedding=embedding,
            n_results=n_results,
            score_threshold=score_threshold,
            where={"resolved": {"$eq": True}},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _query(
        self,
        embedding: list[float],
        n_results: int,
        score_threshold: float,
        where: Optional[dict],
    ) -> list[SimilarTicket]:
        kwargs: dict = {
            "query_embeddings": [embedding],
            "n_results": n_results,
            "include": ["distances", "metadatas", "documents"],
        }
        if where:
            kwargs["where"] = where

        results = await self._col.query(**kwargs)

        similar: list[SimilarTicket] = []
        ids       = results.get("ids",       [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for tid, dist, meta in zip(ids, distances, metadatas):
            score = 1.0 - dist  # cosine distance → cosine similarity
            if score < score_threshold:
                continue
            similar.append(
                SimilarTicket(
                    ticket_id=tid,
                    title=meta.get("title", ""),
                    score=round(score, 4),
                    resolution_summary=meta.get("resolution_summary") or None,
                )
            )
        return similar
