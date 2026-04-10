"""
SOPStore — Chroma collection operations for the SOP knowledge base.

Metadata schema
---------------
Every chunk (both generic and structured) stores at minimum:

  sop_id                    str   — identifies the parent SOP document
  title                     str   — SOP title
  chunk_index               int   — position within the document
  doc_path                  str   — source file path (empty string if unknown)
  category                  str   — generic category tag (legacy field)

Structured chunks (written by SOPKnowledgeBase) additionally carry:

  chunk_type                str   — "overview" | "step" | "escalation"
  fault_category            str   — normalised FaultType value
  escalation_path           str   — who to contact and when
  estimated_resolution_time str   — human-readable time budget
  precondition_count        int   — number of preconditions
  step_count                int   — total resolution steps in the SOP

RAN / Ericsson OPI fields (populated for RAN SOPs, empty for generic):

  managed_object            str   — Ericsson MO class, e.g. "NRSectorCarrier"
  additional_text           str   — alarm additional text that selects remedy branch
  alarm_severity            str   — "primary" | "secondary"
  on_site_required          bool  — whether field engineer attendance is required
  secondary_alarm_pointer   str   — primary alarm name (secondary SOPs only)

The richer metadata enables:
  • query_by_category()        — restrict search to a specific fault type
  • query_steps_only()         — return only step chunks (most precise retrieval)
  • query_by_managed_object()  — restrict search to a specific Ericsson MO
"""
import logging
from typing import Optional

import chromadb

from app.models.recommendation import SOPMatch

log = logging.getLogger(__name__)


class SOPStore:
    def __init__(self, collection: chromadb.AsyncCollection):
        self._col = collection

    # ------------------------------------------------------------------
    # Upsert — generic (unstructured) chunks
    # ------------------------------------------------------------------

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
        """Upsert a generic (unstructured) SOP chunk. Used by SOPLoader."""
        metadata = {
            "sop_id":      sop_id,
            "title":       title,
            "chunk_index": chunk_index,
            "doc_path":    doc_path or "",
            "category":    category or "",
            # Structured fields — defaults so schema is consistent
            "chunk_type":                "generic",
            "fault_category":            category or "",
            "escalation_path":           "",
            "estimated_resolution_time": "",
            "precondition_count":        0,
            "step_count":                0,
            # RAN fields — defaults
            "managed_object":          "",
            "additional_text":         "",
            "alarm_severity":          "primary",
            "on_site_required":        False,
            "secondary_alarm_pointer": "",
        }
        await self._col.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
        )
        log.debug("Upserted generic SOP chunk %s", chunk_id)

    # ------------------------------------------------------------------
    # Upsert — structured chunks (written by SOPKnowledgeBase)
    # ------------------------------------------------------------------

    async def upsert_structured_chunk(
        self,
        chunk_id: str,
        embedding: list[float],
        content: str,
        sop_id: str,
        title: str,
        chunk_index: int,
        chunk_type: str,
        doc_path: str = "",
        fault_category: str = "",
        escalation_path: str = "",
        estimated_resolution_time: str = "",
        precondition_count: int = 0,
        step_count: int = 0,
        # RAN / Ericsson OPI fields
        managed_object: str = "",
        additional_text: str = "",
        alarm_severity: str = "primary",
        on_site_required: bool = False,
        secondary_alarm_pointer: str = "",
    ) -> None:
        """
        Upsert a structured SOP chunk produced by SOPKnowledgeBase.

        Carries the full metadata set so callers can filter by
        fault_category, chunk_type, managed_object, or any other dimension.
        """
        metadata = {
            "sop_id":                    sop_id,
            "title":                     title,
            "chunk_index":               chunk_index,
            "doc_path":                  doc_path,
            "category":                  fault_category,       # keep legacy field consistent
            "chunk_type":                chunk_type,
            "fault_category":            fault_category,
            "escalation_path":           escalation_path,
            "estimated_resolution_time": estimated_resolution_time,
            "precondition_count":        precondition_count,
            "step_count":                step_count,
            # RAN fields
            "managed_object":            managed_object,
            "additional_text":           additional_text,
            "alarm_severity":            alarm_severity,
            "on_site_required":          on_site_required,
            "secondary_alarm_pointer":   secondary_alarm_pointer,
        }
        await self._col.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
        )
        log.debug(
            "Upserted structured SOP chunk %s (type=%s, mo=%s)",
            chunk_id, chunk_type, managed_object or "—",
        )

    # ------------------------------------------------------------------
    # Query — all chunks
    # ------------------------------------------------------------------

    async def query_relevant(
        self,
        embedding: list[float],
        n_results: int = 3,
    ) -> list[SOPMatch]:
        """Return the top-n most relevant SOP chunks across all types."""
        return await self._query(embedding, n_results, where=None)

    # ------------------------------------------------------------------
    # Query — filtered by fault category
    # ------------------------------------------------------------------

    async def query_by_category(
        self,
        embedding: list[float],
        fault_category: str,
        n_results: int = 3,
    ) -> list[SOPMatch]:
        """
        Return the top-n SOP chunks whose fault_category matches exactly.

        Useful when the classifier has already determined the fault type
        and the agent wants SOPs specific to that category.
        """
        return await self._query(
            embedding,
            n_results,
            where={"fault_category": {"$eq": fault_category.lower()}},
        )

    # ------------------------------------------------------------------
    # Query — step chunks only (most precise retrieval)
    # ------------------------------------------------------------------

    async def query_steps_only(
        self,
        embedding: list[float],
        n_results: int = 5,
    ) -> list[SOPMatch]:
        """
        Return only step-type chunks — one chunk per resolution step.

        Use this when you want the most precise procedure match rather
        than overview or escalation content.
        """
        return await self._query(
            embedding,
            n_results,
            where={"chunk_type": {"$eq": "step"}},
        )

    # ------------------------------------------------------------------
    # Query — filtered by Managed Object (RAN)
    # ------------------------------------------------------------------

    async def query_by_managed_object(
        self,
        embedding: list[float],
        managed_object: str,
        n_results: int = 5,
    ) -> list[SOPMatch]:
        """
        Return the top-n SOP chunks for a specific Ericsson Managed Object.

        Useful when the alarm source MO is known (e.g. "NRSectorCarrier")
        and the agent wants only remedy actions applicable to that MO.
        """
        return await self._query(
            embedding,
            n_results,
            where={"managed_object": {"$eq": managed_object}},
        )

    # ------------------------------------------------------------------
    # Query — primary alarms only (skip secondary/symptom SOPs)
    # ------------------------------------------------------------------

    async def query_primary_alarms(
        self,
        embedding: list[float],
        n_results: int = 3,
    ) -> list[SOPMatch]:
        """
        Return only SOPs for primary (root-cause) alarms.

        Secondary alarms (like Service Unavailable) require finding and
        resolving the correlated primary alarm first.  Use this query
        when you want to avoid surfacing symptom-only procedures.
        """
        return await self._query(
            embedding,
            n_results,
            where={"alarm_severity": {"$eq": "primary"}},
        )

    # ------------------------------------------------------------------
    # Query — combined category + MO (RAN precision retrieval)
    # ------------------------------------------------------------------

    async def query_by_category_and_mo(
        self,
        embedding: list[float],
        fault_category: str,
        managed_object: str,
        n_results: int = 3,
    ) -> list[SOPMatch]:
        """
        Return SOP chunks matching both fault category and Managed Object.

        The most precise retrieval path for RAN alarms where both the
        alarm type and the raising MO are known.
        """
        return await self._query(
            embedding,
            n_results,
            where={
                "$and": [
                    {"fault_category": {"$eq": fault_category.lower()}},
                    {"managed_object": {"$eq": managed_object}},
                ]
            },
        )

    # ------------------------------------------------------------------
    # Get by SOP ID (for override resolution step fetch)
    # ------------------------------------------------------------------

    async def get_chunks_by_sop_id(self, sop_id: str) -> list[dict]:
        """
        Return all stored chunks for a given SOP ID, ordered by chunk_index.

        Each dict contains:
          ``chunk_type``  — "overview" | "step" | "escalation" | "generic"
          ``chunk_index`` — position within the document (for ordering)
          ``content``     — raw chunk text
          ``metadata``    — full metadata dict

        Used by the human review override flow to extract the resolution
        steps from a reviewer-selected SOP.
        """
        results = await self._col.get(
            where={"sop_id": {"$eq": sop_id}},
            include=["documents", "metadatas"],
        )
        ids       = results.get("ids",       [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])

        chunks = []
        for doc, meta in zip(documents, metadatas):
            chunks.append({
                "chunk_type":  meta.get("chunk_type", "generic"),
                "chunk_index": int(meta.get("chunk_index", 0)),
                "content":     doc,
                "metadata":    meta,
            })

        # Order by chunk_index so steps come out in the correct sequence
        chunks.sort(key=lambda c: c["chunk_index"])
        log.debug("get_chunks_by_sop_id(%s) returned %d chunks", sop_id, len(chunks))
        return chunks

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _query(
        self,
        embedding: list[float],
        n_results: int,
        where: Optional[dict],
    ) -> list[SOPMatch]:
        kwargs: dict = {
            "query_embeddings": [embedding],
            "n_results":        n_results,
            "include":          ["distances", "metadatas", "documents"],
        }
        if where:
            kwargs["where"] = where

        results = await self._col.query(**kwargs)

        matches: list[SOPMatch] = []
        ids       = results.get("ids",       [[]])[0]
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
