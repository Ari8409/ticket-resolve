"""
SentenceTransformerEmbedder — local embedding backend using sentence-transformers.

Default model: all-MiniLM-L6-v2
  • 384-dimensional embeddings
  • Optimised for cosine-similarity / semantic textual similarity tasks
  • ~80 MB, CPU-only, no API key required
  • Apache 2.0 licence

Embeddings are L2-normalised before being returned so that Chroma's
cosine-distance metric (distance = 1 − similarity) produces correct rankings.

The SentenceTransformer model is loaded once at construction time.
Treat instances as singletons (see app/dependencies.py get_st_embedder).

All public methods mirror the TicketEmbedder interface so both backends
are interchangeable inside MatchingEngine without any changes to callers.

Thread-safety
-------------
SentenceTransformer.encode() releases the GIL during the forward pass, so
running it in an asyncio executor is safe even under concurrent requests.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


class SentenceTransformerEmbedder:
    """
    Local sentence-transformers embedding backend.

    Parameters
    ----------
    model_name:
        Any model available on the Hugging Face hub or a local path.
        Defaults to ``all-MiniLM-L6-v2``.
    device:
        PyTorch device string — ``"cpu"``, ``"cuda"``, ``"mps"``.
        ``None`` lets sentence-transformers auto-detect.
    normalize:
        L2-normalise embeddings before returning.  Must be True when
        the downstream vector store uses cosine distance (Chroma default).
    batch_size:
        Number of texts to encode per forward pass in ``embed_batch``.
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        normalize: bool = True,
        batch_size: int = 32,
    ) -> None:
        # Lazy import so the module can be imported without sentence-transformers
        # installed (unit tests mock this class).
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self._model_name = model_name
        self._normalize = normalize
        self._batch_size = batch_size

        log.info(
            "Loading sentence-transformers model '%s' on device=%s",
            model_name, device or "auto",
        )
        self._model: SentenceTransformer = SentenceTransformer(model_name, device=device)
        self._dim: int = self._model.get_sentence_embedding_dimension()
        log.info("Model ready — embedding dim=%d", self._dim)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dim(self) -> int:
        return self._dim

    # ------------------------------------------------------------------
    # Public async interface (same signature as TicketEmbedder)
    # ------------------------------------------------------------------

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single string; returns a float list of length ``embedding_dim``."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._encode_single, text))

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple strings in one forward pass (more efficient than looping)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._encode_batch, texts))

    # ------------------------------------------------------------------
    # Synchronous internals (run in executor to avoid blocking the event loop)
    # ------------------------------------------------------------------

    def _encode_single(self, text: str) -> list[float]:
        vec: np.ndarray = self._model.encode(
            text,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
        )
        return vec.tolist()

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        vecs: np.ndarray = self._model.encode(
            texts,
            normalize_embeddings=self._normalize,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        return vecs.tolist()

    # ------------------------------------------------------------------
    # Utility — useful for reranking / debugging without a vector store
    # ------------------------------------------------------------------

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """
        Cosine similarity between two embedding vectors.

        If both vectors are already L2-normalised (``normalize=True``),
        this reduces to a dot product and is O(dim) fast.
        """
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        norm_a = float(np.linalg.norm(va))
        norm_b = float(np.linalg.norm(vb))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(va, vb)) / (norm_a * norm_b)
