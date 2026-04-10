"""
TicketEmbeddingPipeline — end-to-end embedding pipeline for incoming tickets.

Flow
----
  ticket description (str)
        │
        ▼
  SentenceTransformerEmbedder.embed_text()     →  embedding vector (list[float])
        │
        ├─────────────────────────────────────────────────────┐
        ▼                                                     ▼
  MatchingEngine.find_similar_resolved()    raw embedding carried through
  (Chroma cosine similarity, resolved=True)
        │
        ▼
  TicketEmbeddingResult
    ├── ticket_id
    ├── description
    ├── embedding       — float vector, length == embedding_dim
    ├── embedding_dim   — e.g. 384 for all-MiniLM-L6-v2
    ├── model_name      — e.g. "all-MiniLM-L6-v2"
    └── top_matches     — list[SimilarTicket] ranked by cosine similarity

Why return the raw embedding?
    • Callers can reuse it for other downstream comparisons without re-encoding
    • Enables caching / logging of embeddings for audit or drift detection
    • Lets the API surface the vector to clients that want to do their own reranking

Design note — embedding model consistency
    The SentenceTransformerEmbedder passed to this pipeline MUST be the same
    model used when historical tickets were indexed with resolved=True.
    Mixing models within a single Chroma collection produces meaningless scores.
    Use a single embedder singleton (see app/dependencies.py get_st_embedder).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.matching.engine import MatchingEngine
from app.matching.st_embedder import SentenceTransformerEmbedder
from app.models.recommendation import SimilarTicket, TicketEmbeddingResult

log = logging.getLogger(__name__)


class TicketEmbeddingPipeline:
    """
    Embeds an incoming ticket description and retrieves the top-k most
    similar *resolved* tickets from the vector store via cosine similarity.

    Parameters
    ----------
    embedder:
        A ``SentenceTransformerEmbedder`` instance (shared singleton).
    engine:
        A ``MatchingEngine`` whose internal store has been seeded with
        resolved historical tickets (``resolved=True``).
    top_k:
        Number of resolved similar tickets to return.  Defaults to 3.
    score_threshold:
        Minimum cosine similarity (0–1) to include a match.
        Defaults to 0.0 (return all top_k regardless of score).
    """

    def __init__(
        self,
        embedder: SentenceTransformerEmbedder,
        engine: MatchingEngine,
        top_k: int = 3,
        score_threshold: float = 0.0,
    ) -> None:
        self._embedder         = embedder
        self._engine           = engine
        self._top_k            = top_k
        self._score_threshold  = score_threshold

    async def run(
        self,
        ticket_id: str,
        description: str,
    ) -> TicketEmbeddingResult:
        """
        Embed ``description`` and return the top-k resolved similar tickets.

        Parameters
        ----------
        ticket_id:
            ID of the incoming ticket (not stored here — caller owns indexing).
        description:
            Raw text to embed.  May be the ticket's description field alone,
            or a concatenation of title + description for richer context.

        Returns
        -------
        TicketEmbeddingResult
            Contains the raw embedding, model metadata, and resolved matches.
        """
        log.debug("Running embedding pipeline for ticket %s", ticket_id)

        # Step 1 — embed the incoming description
        embedding: list[float] = await self._embedder.embed_text(description)

        # Step 2 — retrieve top-k resolved tickets by cosine similarity
        top_matches: list[SimilarTicket] = await self._engine.find_similar_resolved(
            query=description,
            top_k=self._top_k,
        )

        # Apply optional threshold filter (engine may return lower-score matches
        # when the collection is small and n_results > available resolved docs)
        if self._score_threshold > 0.0:
            top_matches = [m for m in top_matches if m.score >= self._score_threshold]

        log.info(
            "Embedding pipeline complete — ticket=%s dim=%d matches=%d",
            ticket_id, len(embedding), len(top_matches),
        )
        return TicketEmbeddingResult(
            ticket_id=ticket_id,
            description=description,
            embedding=embedding,
            embedding_dim=len(embedding),
            model_name=self._embedder.model_name,
            top_matches=top_matches,
        )

    async def run_batch(
        self,
        tickets: list[tuple[str, str]],
    ) -> list[TicketEmbeddingResult]:
        """
        Run the pipeline for a batch of (ticket_id, description) pairs.

        Descriptions are encoded in a single forward pass for efficiency.
        Chroma queries are still issued one at a time (no batched query API).
        """
        if not tickets:
            return []

        ids, descriptions = zip(*tickets)

        # Batch embed all descriptions in one pass
        embeddings: list[list[float]] = await self._embedder.embed_batch(list(descriptions))

        results: list[TicketEmbeddingResult] = []
        for ticket_id, description, embedding in zip(ids, descriptions, embeddings):
            top_matches = await self._engine.find_similar_resolved(
                query=description,
                top_k=self._top_k,
            )
            if self._score_threshold > 0.0:
                top_matches = [m for m in top_matches if m.score >= self._score_threshold]

            results.append(TicketEmbeddingResult(
                ticket_id=ticket_id,
                description=description,
                embedding=embedding,
                embedding_dim=len(embedding),
                model_name=self._embedder.model_name,
                top_matches=top_matches,
            ))

        log.info(
            "Batch embedding pipeline complete — %d tickets processed", len(results),
        )
        return results
