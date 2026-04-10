"""
SOPKnowledgeBase — loads, parses, indexes, and queries structured SOPs.

Responsibilities
----------------
1. Load          — scan a directory tree for ``*.md`` files and parse each
                   into a ``SOPRecord`` via ``SOPMarkdownParser``.
2. Index         — embed and upsert each record into the Chroma SOPs
                   collection with rich structured metadata.
3. Query         — in-memory lookup by sop_id or fault_category, and
                   keyword search over title / resolution steps.
4. Report        — ``load_report()`` summarises what was loaded, what failed,
                   and which fault categories are covered.

Indexing strategy — semantic chunking
--------------------------------------
Rather than splitting by token count, each SOPRecord is indexed as three
semantically meaningful chunk types so vector queries return the most
useful granularity:

  overview_chunk    title + preconditions summary + escalation metadata
  step_chunk        one Chroma document per resolution step (most precise)
  escalation_chunk  escalation path text (for "who to call" queries)

This means a query like "how to restart a BGP session" will surface the
exact step rather than a large blob of unrelated procedure text.

Usage
-----
::

    kb = SOPKnowledgeBase()
    records = kb.load_directory(Path("data/sops/telco"))
    await kb.index_all(records, embedder, sop_store)

    sop   = kb.get_by_id("SOP-RF-001")
    sops  = kb.get_by_category("signal_loss")
    found = kb.search("antenna RSSI")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.matching.embedder import TicketEmbedder
from app.matching.st_embedder import SentenceTransformerEmbedder
from app.models.sop import SOPRecord
from app.sop.parser import SOPMarkdownParser, SOPParseError
from app.sop.sop_store import SOPStore

log = logging.getLogger(__name__)

# Type alias — accepts either embedder backend
AnyEmbedder = TicketEmbedder | SentenceTransformerEmbedder


# ---------------------------------------------------------------------------
# Load report
# ---------------------------------------------------------------------------

@dataclass
class SOPLoadReport:
    """Summary produced by load_directory() + index_all()."""
    loaded:      list[str]               = field(default_factory=list)   # sop_ids loaded OK
    failed:      list[tuple[str, str]]   = field(default_factory=list)   # (path, error_msg)
    indexed:     int                     = 0                             # Chroma chunks written
    categories:  dict[str, list[str]]    = field(default_factory=dict)   # {category: [sop_ids]}

    @property
    def total_loaded(self) -> int:
        return len(self.loaded)

    @property
    def total_failed(self) -> int:
        return len(self.failed)

    def summary(self) -> str:
        cats = ", ".join(
            f"{cat}({len(ids)})" for cat, ids in sorted(self.categories.items())
        )
        return (
            f"SOPKnowledgeBase: loaded={self.total_loaded} "
            f"failed={self.total_failed} "
            f"chunks_indexed={self.indexed} "
            f"categories=[{cats}]"
        )


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------

class SOPKnowledgeBase:
    """
    In-memory SOP registry backed by Chroma for semantic search.

    The knowledge base is populated in two steps:

        records = kb.load_directory(path)   # parse markdown files
        report  = await kb.index_all(records, embedder, store)  # embed + upsert

    After indexing, the in-memory indices support fast lookups without
    round-tripping to Chroma.

    Parameters
    ----------
    parser:
        ``SOPMarkdownParser`` instance.  Defaults to a new instance with
        default settings.
    """

    def __init__(self, parser: Optional[SOPMarkdownParser] = None) -> None:
        self._parser  = parser or SOPMarkdownParser()
        self._by_id:  dict[str, SOPRecord]       = {}
        self._by_cat: dict[str, list[SOPRecord]] = {}

    # ------------------------------------------------------------------
    # Load (parse markdown → SOPRecord)
    # ------------------------------------------------------------------

    def load_file(self, path: Path) -> SOPRecord:
        """
        Parse a single markdown file into a ``SOPRecord`` and register it
        in the in-memory indices.

        Raises
        ------
        SOPParseError
            If a required field is missing.
        FileNotFoundError
            If ``path`` does not exist.
        """
        record = self._parser.parse(path)
        self._register(record)
        return record

    def load_directory(self, directory: Path) -> tuple[list[SOPRecord], SOPLoadReport]:
        """
        Recursively scan ``directory`` for ``*.md`` files and parse each one.

        Files that fail to parse are added to ``report.failed`` and skipped —
        one bad file never blocks the rest.

        Returns
        -------
        records:
            List of successfully parsed ``SOPRecord`` objects.
        report:
            ``SOPLoadReport`` capturing success/failure counts.
        """
        report  = SOPLoadReport()
        records: list[SOPRecord] = []

        for path in sorted(directory.rglob("*.md")):
            try:
                record = self._parser.parse(path)
                self._register(record)
                records.append(record)
                report.loaded.append(record.sop_id)
                report.categories.setdefault(record.fault_category, []).append(record.sop_id)
                log.info(
                    "Parsed SOP %s (%s) from %s — %d steps, %d preconditions",
                    record.sop_id, record.fault_category, path.name,
                    record.step_count, record.precondition_count,
                )
            except (SOPParseError, FileNotFoundError, ValueError) as exc:
                log.warning("Skipping %s — %s", path, exc)
                report.failed.append((str(path), str(exc)))

        return records, report

    # ------------------------------------------------------------------
    # Index (embed + upsert to Chroma)
    # ------------------------------------------------------------------

    async def index_all(
        self,
        records: list[SOPRecord],
        embedder: AnyEmbedder,
        sop_store: SOPStore,
    ) -> SOPLoadReport:
        """
        Embed and upsert all ``records`` into the Chroma SOPs collection.

        Each record generates three chunk types:
          - overview chunk    (title + preconditions + escalation summary)
          - one step chunk per resolution step (most precise for retrieval)
          - escalation chunk  (who to call and when)

        Returns an ``SOPLoadReport`` populated with the total chunk count.
        """
        report = SOPLoadReport(
            loaded=[r.sop_id for r in records],
            categories={},
        )

        for record in records:
            try:
                chunks = self._build_chunks(record)
                embeddings = await embedder.embed_batch([c["text"] for c in chunks])

                for chunk, embedding in zip(chunks, embeddings):
                    await sop_store.upsert_structured_chunk(
                        chunk_id=chunk["chunk_id"],
                        embedding=embedding,
                        content=chunk["text"],
                        sop_id=record.sop_id,
                        title=record.title,
                        chunk_index=chunk["index"],
                        chunk_type=chunk["type"],
                        doc_path=record.source_path,
                        fault_category=record.fault_category,
                        escalation_path=record.escalation_path,
                        estimated_resolution_time=record.estimated_resolution_time,
                        precondition_count=record.precondition_count,
                        step_count=record.step_count,
                    )

                report.indexed += len(chunks)
                report.categories.setdefault(record.fault_category, []).append(record.sop_id)
                log.info(
                    "Indexed SOP %s — %d chunks (1 overview + %d steps + 1 escalation)",
                    record.sop_id, len(chunks), record.step_count,
                )
            except Exception as exc:
                log.error("Failed to index SOP %s: %s", record.sop_id, exc, exc_info=True)
                report.failed.append((record.sop_id, str(exc)))

        log.info(report.summary())
        return report

    # ------------------------------------------------------------------
    # In-memory lookup
    # ------------------------------------------------------------------

    def get_by_id(self, sop_id: str) -> Optional[SOPRecord]:
        """Return the SOPRecord with the given sop_id, or None."""
        return self._by_id.get(sop_id)

    def get_by_category(self, fault_category: str) -> list[SOPRecord]:
        """Return all SOPs for a given fault_category (e.g. 'signal_loss')."""
        return list(self._by_cat.get(fault_category.lower(), []))

    def all_records(self) -> list[SOPRecord]:
        """Return all loaded SOPRecords, sorted by sop_id."""
        return sorted(self._by_id.values(), key=lambda r: r.sop_id)

    def all_categories(self) -> list[str]:
        """Return the distinct fault categories present in the knowledge base."""
        return sorted(self._by_cat.keys())

    def search(self, query: str, top_k: int = 5) -> list[SOPRecord]:
        """
        Keyword search over title, fault_category, and resolution steps.

        Returns up to ``top_k`` records ordered by match count (most
        matching terms first).  Use ``SOPRetriever`` for semantic search.

        Parameters
        ----------
        query:
            Space-separated search terms (case-insensitive).
        top_k:
            Maximum number of records to return.
        """
        terms = [t.lower() for t in query.split() if t]
        if not terms:
            return []

        scored: list[tuple[int, SOPRecord]] = []
        for record in self._by_id.values():
            haystack = " ".join([
                record.title,
                record.fault_category,
                " ".join(record.resolution_steps),
                " ".join(record.preconditions),
                record.escalation_path,
            ]).lower()
            hits = sum(1 for t in terms if t in haystack)
            if hits:
                scored.append((hits, record))

        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:top_k]]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _register(self, record: SOPRecord) -> None:
        self._by_id[record.sop_id] = record
        self._by_cat.setdefault(record.fault_category, []).append(record)

    @staticmethod
    def _build_chunks(record: SOPRecord) -> list[dict]:
        """
        Build the list of text chunks for Chroma from a structured SOPRecord.

        Chunk layout:
          index 0      — overview (title + preconditions summary)
          index 1…N    — one chunk per resolution step (most precise)
          index N+1    — escalation path
        """
        chunks = []

        # Chunk 0 — overview
        preconditions_text = (
            "Preconditions:\n" + "\n".join(f"  • {p}" for p in record.preconditions)
            if record.preconditions
            else "No specific preconditions."
        )
        overview_text = (
            f"{record.title}\n"
            f"Category: {record.fault_category}\n"
            f"Estimated resolution time: {record.estimated_resolution_time}\n\n"
            f"{preconditions_text}"
        )
        chunks.append({
            "chunk_id": f"{record.sop_id}_overview",
            "index":    0,
            "type":     "overview",
            "text":     overview_text,
        })

        # Chunks 1…N — one per resolution step
        for i, step in enumerate(record.resolution_steps, start=1):
            chunks.append({
                "chunk_id": f"{record.sop_id}_step_{i}",
                "index":    i,
                "type":     "step",
                "text":     f"{record.title} — Step {i}: {step}",
            })

        # Final chunk — escalation path
        escalation_text = (
            f"{record.title} — Escalation Path\n"
            f"{record.escalation_path}\n"
            f"Estimated resolution time: {record.estimated_resolution_time}"
        )
        chunks.append({
            "chunk_id": f"{record.sop_id}_escalation",
            "index":    len(record.resolution_steps) + 1,
            "type":     "escalation",
            "text":     escalation_text,
        })

        return chunks
