import logging
import re
from typing import Optional

from app.matching.embedder import TicketEmbedder
from app.models.recommendation import SOPMatch
from app.sop.sop_store import SOPStore

log = logging.getLogger(__name__)

# Matches lines like "1. Step text" or "2. Another step"
_NUMBERED_STEP_RE = re.compile(r"^\s*\d+\.\s+(.+)", re.MULTILINE)


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

    async def get_sop_steps_by_id(self, sop_id: str) -> list[str]:
        """
        Return the ordered resolution steps for a specific SOP identified by its sop_id.

        Strategy:
          1. Fetch all Chroma chunks for the given sop_id.
          2. Prefer chunks whose chunk_type is "step" — each carries one resolution step.
          3. If no structured step chunks exist (generic / unstructured SOP), fall back to
             extracting numbered lines (``1. …``) from all chunk text combined.
          4. Returns an empty list if the SOP is not found in the store.
        """
        chunks = await self._store.get_chunks_by_sop_id(sop_id)
        if not chunks:
            log.warning("No chunks found for sop_id=%s", sop_id)
            return []

        # --- Path 1: structured step chunks ---
        step_chunks = [c for c in chunks if c["chunk_type"] == "step"]
        if step_chunks:
            steps = []
            for c in step_chunks:
                # The step chunk text is: "Title [MO] — Step N: <text>"
                # Extract the step text after the last "— Step N: " marker if present
                text = c["content"]
                marker_match = re.search(r"—\s*Step\s+\d+:\s*(.+)", text, re.DOTALL)
                steps.append(marker_match.group(1).strip() if marker_match else text.strip())
            log.debug("Extracted %d structured steps for sop_id=%s", len(steps), sop_id)
            return steps

        # --- Path 2: numbered lines from all chunk text ---
        full_text = "\n".join(c["content"] for c in chunks)
        numbered = _NUMBERED_STEP_RE.findall(full_text)
        if numbered:
            log.debug("Extracted %d numbered steps (fallback) for sop_id=%s", len(numbered), sop_id)
            return [s.strip() for s in numbered]

        # --- Path 3: return overview chunk as a single step ---
        overview = next((c for c in chunks if c["chunk_type"] == "overview"), chunks[0])
        log.warning("No steps parseable for sop_id=%s; returning overview as single step", sop_id)
        return [overview["content"].strip()]
