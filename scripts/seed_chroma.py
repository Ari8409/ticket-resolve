"""
One-shot script: populates Chroma with SOPs and historical tickets.

SOP loading strategy
---------------------
  data/sops/ran/    → SOPKnowledgeBase  (structured semantic chunking:
  data/sops/telco/     overview + one chunk per step + escalation chunk)
  data/sops/*.md    → SOPLoader         (generic RecursiveCharacterTextSplitter)
  data/sops/*.txt      for unstructured SOPs that don't follow the
  data/sops/*.pdf      structured markdown format

Ticket seeding
--------------
  tests/fixtures/sample_tickets.json → index_telco_ticket() with full CTTS
  data/seed_tickets/*.csv            → legacy CSV fallback (generic TicketIn)

Usage:
    python scripts/seed_chroma.py

Environment:
    Reads settings from .env (EMBEDDING_BACKEND, CHROMA_HOST, etc.).
    Works with both sentence_transformers and openai embedding backends.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.matching.engine import MatchingEngine
from app.matching.ticket_store import TicketStore
from app.models.telco_ticket import TelcoTicketCreate
from app.sop.knowledge_base import SOPKnowledgeBase
from app.sop.loader import SOPLoader
from app.sop.sop_store import SOPStore
from app.storage.chroma_client import ensure_collections

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("seed_chroma")


def _build_embedder(settings):
    """Return the configured embedding backend."""
    if settings.EMBEDDING_BACKEND == "sentence_transformers":
        from app.matching.st_embedder import SentenceTransformerEmbedder
        log.info(
            "Using sentence-transformers backend (%s, device=%s)",
            settings.ST_MODEL, settings.ST_DEVICE,
        )
        return SentenceTransformerEmbedder(
            model_name=settings.ST_MODEL,
            device=settings.ST_DEVICE,
        )

    from app.matching.embedder import TicketEmbedder
    log.info("Using OpenAI embedding backend (%s)", settings.EMBEDDING_MODEL)
    return TicketEmbedder(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )


async def seed_sops(embedder, sop_store: SOPStore) -> None:
    """
    Load SOPs into Chroma using the appropriate loader for each directory.

    Structured directories (ran/, telco/) → SOPKnowledgeBase (semantic chunking).
    Remaining *.md / *.txt / *.pdf files → SOPLoader (generic splitter).
    """
    sop_dir = Path("data/sops")
    if not sop_dir.exists():
        log.warning("No SOP directory found at %s — skipping SOP seeding", sop_dir)
        return

    total_chunks = 0
    kb = SOPKnowledgeBase()

    # ----------------------------------------------------------------
    # 1. Structured directories — SOPKnowledgeBase
    # ----------------------------------------------------------------
    structured_dirs = [sop_dir / "ran", sop_dir / "telco"]

    for structured_dir in structured_dirs:
        if not structured_dir.exists():
            log.info("Structured SOP directory %s not found — skipping", structured_dir)
            continue

        log.info("Loading structured SOPs from %s ...", structured_dir)
        records, load_report = kb.load_directory(structured_dir)

        if load_report.total_failed:
            for path, err in load_report.failed:
                log.warning("  Failed to parse %s: %s", path, err)

        if not records:
            log.info("  No parseable SOPs found in %s", structured_dir)
            continue

        index_report = await kb.index_all(records, embedder, sop_store)
        total_chunks += index_report.indexed

        log.info(
            "  %s: %d SOPs parsed, %d failed, %d chunks indexed",
            structured_dir.name,
            load_report.total_loaded,
            load_report.total_failed,
            index_report.indexed,
        )

    # ----------------------------------------------------------------
    # 2. Top-level generic files — SOPLoader (skip ran/ and telco/)
    # ----------------------------------------------------------------
    generic_loader = SOPLoader(embedder=embedder, sop_store=sop_store)
    generic_exts = {".md", ".txt", ".pdf"}
    structured_names = {d.name for d in structured_dirs}

    generic_files = [
        p for p in sorted(sop_dir.iterdir())
        if p.is_file() and p.suffix.lower() in generic_exts
    ]

    if generic_files:
        log.info("Loading %d generic SOP file(s) from %s ...", len(generic_files), sop_dir)
        for path in generic_files:
            try:
                n = await generic_loader.load_file(path)
                total_chunks += n
                log.info("  Loaded generic SOP '%s' (%d chunks)", path.name, n)
            except Exception as exc:
                log.warning("  Failed to load %s: %s", path.name, exc)
    else:
        log.info("No generic SOP files found at top level of %s", sop_dir)

    log.info("SOP seeding complete — total chunks indexed: %d", total_chunks)


async def seed_tickets_from_json(
    matching_engine: MatchingEngine,
    fixtures_path: Path,
) -> int:
    """
    Seed historical tickets from sample_tickets.json using index_telco_ticket()
    so all CTTS fields are preserved in the Chroma document.
    """
    if not fixtures_path.exists():
        log.warning("Fixtures file not found at %s — skipping ticket seeding", fixtures_path)
        return 0

    data = json.loads(fixtures_path.read_text(encoding="utf-8"))
    tickets_raw = data if isinstance(data, list) else data.get("tickets", [])

    count = 0
    for raw in tickets_raw:
        try:
            ticket = TelcoTicketCreate(**raw)
            # Use ticket_id from the fixture if present, otherwise auto-generated
            ticket_id = ticket.ticket_id
            await matching_engine.index_telco_ticket(
                ticket_id=ticket_id,
                ticket=ticket,
                resolution_summary=_build_summary(ticket),
                resolved=bool(ticket.resolution or ticket.resolution_code),
            )
            count += 1
        except Exception as exc:
            log.warning("  Skipped fixture ticket: %s", exc)

    log.info("Seeded %d historical tickets from %s", count, fixtures_path.name)
    return count


async def seed_tickets_from_csv(matching_engine: MatchingEngine, seed_dir: Path) -> int:
    """Legacy CSV fallback — kept for backwards compatibility with data/seed_tickets/*.csv."""
    import csv

    count = 0
    for csv_path in sorted(seed_dir.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Build a minimal TelcoTicketCreate from CSV columns
                    from app.models.telco_ticket import FaultType, Severity
                    ticket = TelcoTicketCreate(
                        ticket_id=row.get("ticket_id") or TelcoTicketCreate.__fields__["ticket_id"].default_factory(),
                        affected_node=row.get("affected_node") or row.get("node", "UNKNOWN"),
                        description=row.get("description") or row.get("title", "No description"),
                        severity=Severity(row.get("severity", "major")),
                        fault_type=FaultType(row.get("fault_type", "unknown")),
                    )
                    await matching_engine.index_telco_ticket(
                        ticket_id=ticket.ticket_id,
                        ticket=ticket,
                        resolution_summary=row.get("resolution_summary"),
                        resolved=bool(row.get("resolution_summary")),
                    )
                    count += 1
                except Exception as exc:
                    log.warning("  Skipped CSV row from %s: %s", csv_path.name, exc)

    if count:
        log.info("Seeded %d historical tickets from CSV files in %s", count, seed_dir)
    return count


def _build_summary(ticket: TelcoTicketCreate) -> str | None:
    """Compact one-liner for Chroma metadata preview."""
    parts = []
    if ticket.resolution_code:
        parts.append(ticket.resolution_code)
    if ticket.primary_cause:
        parts.append(ticket.primary_cause)
    if ticket.resolution:
        parts.append(ticket.resolution[:80])
    return " — ".join(parts) if parts else None


async def main() -> None:
    settings = get_settings()

    log.info(
        "Connecting to Chroma at %s:%s ...",
        settings.CHROMA_HOST, settings.CHROMA_PORT,
    )
    client = await chromadb.AsyncHttpClient(
        host=settings.CHROMA_HOST,
        port=int(settings.CHROMA_PORT),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    await ensure_collections(client, settings.TICKET_COLLECTION, settings.SOP_COLLECTION)
    log.info(
        "Collections ready: '%s' (tickets), '%s' (SOPs)",
        settings.TICKET_COLLECTION, settings.SOP_COLLECTION,
    )

    embedder = _build_embedder(settings)

    # ----------------------------------------------------------------
    # SOPs
    # ----------------------------------------------------------------
    sop_collection = await client.get_collection(settings.SOP_COLLECTION)
    sop_store = SOPStore(sop_collection)
    await seed_sops(embedder, sop_store)

    # ----------------------------------------------------------------
    # Historical tickets — primary source: fixtures JSON
    # ----------------------------------------------------------------
    ticket_collection = await client.get_collection(settings.TICKET_COLLECTION)
    ticket_store = TicketStore(ticket_collection)

    matching_engine = MatchingEngine(
        embedder=embedder,
        ticket_store=ticket_store,
        top_k=settings.SIMILARITY_TOP_K,
        score_threshold=settings.SIMILARITY_SCORE_THRESHOLD,
    )

    total_tickets = 0

    fixtures_json = Path("tests/fixtures/sample_tickets.json")
    total_tickets += await seed_tickets_from_json(matching_engine, fixtures_json)

    seed_dir = Path("data/seed_tickets")
    if seed_dir.exists():
        total_tickets += await seed_tickets_from_csv(matching_engine, seed_dir)

    log.info("Ticket seeding complete — total indexed: %d", total_tickets)
    log.info("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())
