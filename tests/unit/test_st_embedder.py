"""
Unit tests for SentenceTransformerEmbedder.

sentence-transformers is mocked at the module level so these tests run
without downloading any model or requiring a GPU.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers — build a fake SentenceTransformer model
# ---------------------------------------------------------------------------

DIM = 384


def _fake_st_model(dim: int = DIM) -> MagicMock:
    """Returns a mock SentenceTransformer that produces unit vectors."""
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = dim

    def _encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False):
        if isinstance(texts, str):
            vec = np.random.rand(dim).astype(np.float32)
            if normalize_embeddings:
                vec /= np.linalg.norm(vec)
            return vec
        vecs = np.random.rand(len(texts), dim).astype(np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs /= np.maximum(norms, 1e-8)
        return vecs

    model.encode.side_effect = _encode
    return model


# ---------------------------------------------------------------------------
# Fixture — patch SentenceTransformer at import time
# ---------------------------------------------------------------------------

@pytest.fixture()
def st_embedder():
    """SentenceTransformerEmbedder with a mocked underlying model."""
    fake_model = _fake_st_model()
    with patch("app.matching.st_embedder.SentenceTransformerEmbedder.__init__") as mock_init:
        # Bypass the real __init__ and inject the mock model directly
        from app.matching.st_embedder import SentenceTransformerEmbedder

        def _patched_init(self, model_name="all-MiniLM-L6-v2", device=None,
                          normalize=True, batch_size=32):
            self._model_name = model_name
            self._normalize  = normalize
            self._batch_size = batch_size
            self._model      = fake_model
            self._dim        = fake_model.get_sentence_embedding_dimension()

        mock_init.side_effect = _patched_init
        yield SentenceTransformerEmbedder()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSentenceTransformerEmbedder:

    @pytest.mark.asyncio
    async def test_embed_text_returns_float_list(self, st_embedder):
        result = await st_embedder.embed_text("High latency on NODE-ATL-01")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    @pytest.mark.asyncio
    async def test_embed_text_correct_dimension(self, st_embedder):
        result = await st_embedder.embed_text("signal loss detected")
        assert len(result) == DIM

    @pytest.mark.asyncio
    async def test_embed_text_is_normalised(self, st_embedder):
        result = await st_embedder.embed_text("test input")
        norm = float(np.linalg.norm(result))
        assert abs(norm - 1.0) < 1e-5, f"Expected unit vector, got norm={norm}"

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list_of_lists(self, st_embedder):
        texts = ["ticket one", "ticket two", "ticket three"]
        results = await st_embedder.embed_batch(texts)
        assert len(results) == 3
        assert all(isinstance(r, list) for r in results)
        assert all(len(r) == DIM for r in results)

    @pytest.mark.asyncio
    async def test_embed_batch_single_item(self, st_embedder):
        results = await st_embedder.embed_batch(["only ticket"])
        assert len(results) == 1
        assert len(results[0]) == DIM

    def test_model_name_property(self, st_embedder):
        assert st_embedder.model_name == "all-MiniLM-L6-v2"

    def test_embedding_dim_property(self, st_embedder):
        assert st_embedder.embedding_dim == DIM

    def test_cosine_similarity_identical_vectors(self):
        from app.matching.st_embedder import SentenceTransformerEmbedder
        v = [0.6, 0.8, 0.0]
        score = SentenceTransformerEmbedder.cosine_similarity(v, v)
        assert abs(score - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        from app.matching.st_embedder import SentenceTransformerEmbedder
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        score = SentenceTransformerEmbedder.cosine_similarity(a, b)
        assert abs(score) < 1e-6

    def test_cosine_similarity_opposite_vectors(self):
        from app.matching.st_embedder import SentenceTransformerEmbedder
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        score = SentenceTransformerEmbedder.cosine_similarity(a, b)
        assert abs(score - (-1.0)) < 1e-6

    def test_cosine_similarity_zero_vector_returns_zero(self):
        from app.matching.st_embedder import SentenceTransformerEmbedder
        a = [0.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        score = SentenceTransformerEmbedder.cosine_similarity(a, b)
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_embed_text_calls_encode_once(self, st_embedder):
        await st_embedder.embed_text("test")
        st_embedder._model.encode.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_batch_calls_encode_once(self, st_embedder):
        await st_embedder.embed_batch(["a", "b", "c"])
        st_embedder._model.encode.assert_called_once()
