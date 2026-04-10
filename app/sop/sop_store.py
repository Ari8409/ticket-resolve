import logging
from typing import Optional

import chromadb

from app.models.recommendation import SOPMatch

log = logging.getLogger(__name__)


class SOPStore:
    def __init__(self, collection: chromadb.AsyncCollection):
        self._col = collection

    async def upsert_chunk(
        self,
        chunk_id: str,
        embedding: list[float],
        content: str,
        sop_id: str,
        title: str,
        chunk_index: int,
        doc_path: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        metadata = {
            "sop_id": sop_id,
            "title": title,
            "chunk_index": chunk_index,
            "doc_path": doc_path or "",
            "category": category or "",
        }
        await self._col.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
        )
        log.debug("Upserted SOP chunk %s", chunk_id)

    async def query_relevant(self, embedding: list[float], n_results: int = 3) -> list[SOPMatch]:
        results = await self._col.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["distances", "metadatas", "documents"],
        )

        matches: list[SOPMatch] = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]

        for chunk_id, dist, meta, doc in zip(ids, distances, metadatas, documents):
            score = 1.0 - dist
            matches.append(
                SOPMatch(
                    sop_id=meta.get("sop_id", chunk_id),
                    title=meta.get("title", ""),
                    content=doc,
                    score=round(score, 4),
                    doc_path=meta.get("doc_path") or None,
                )
            )
        return matches
