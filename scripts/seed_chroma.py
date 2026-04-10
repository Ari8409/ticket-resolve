"""
One-shot script: populates Chroma with SOPs and historical tickets.

Usage:
    python scripts/seed_chroma.py
"""
import asyncio
import csv
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.matching.embedder import TicketEmbedder
from app.matching.ticket_store import TicketStore
from app.models.ticket import TicketIn, TicketPriority
from app.sop.loader import SOPLoader
from app.sop.sop_store import SOPStore
from app.storage.chroma_client import ensure_collections


async def main() -> None:
    settings = get_settings()

    print(f"Connecting to Chroma at {settings.CHROMA_HOST}:{settings.CHROMA_PORT} ...")
    client = await chromadb.AsyncHttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    await ensure_collections(client, settings.TICKET_COLLECTION, settings.SOP_COLLECTION)

    embedder = TicketEmbedder(model=settings.EMBEDDING_MODEL, api_key=settings.OPENAI_API_KEY)

    # --- Load SOPs ---
    sop_collection = await client.get_collection(settings.SOP_COLLECTION)
    sop_store = SOPStore(sop_collection)
    loader = SOPLoader(embedder=embedder, sop_store=sop_store)

    sop_dir = Path("data/sops")
    if sop_dir.exists():
        total_chunks = await loader.load_directory(sop_dir)
        print(f"SOPs loaded: {total_chunks} chunks indexed")
    else:
        print(f"No SOP directory found at {sop_dir} — skipping")

    # --- Load historical tickets ---
    ticket_collection = await client.get_collection(settings.TICKET_COLLECTION)
    ticket_store = TicketStore(ticket_collection)

    seed_dir = Path("data/seed_tickets")
    total_tickets = 0
    for csv_path in sorted(seed_dir.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticket_id = row.get("ticket_id", f"seed-{total_tickets}")
                ticket = TicketIn(
                    source="seed",
                    title=row.get("title", "Untitled"),
                    description=row.get("description", row.get("title", "")),
                    priority=TicketPriority(row.get("priority", "medium")),
                    category=row.get("category"),
                )
                doc = f"{ticket.title}\n{ticket.description}"
                embedding = await embedder.embed_text(doc)
                await ticket_store.upsert_ticket(
                    ticket_id=ticket_id,
                    embedding=embedding,
                    document=doc,
                    title=ticket.title,
                    priority=ticket.priority.value,
                    category=ticket.category,
                    resolution_summary=row.get("resolution_summary"),
                )
                total_tickets += 1

    print(f"Historical tickets indexed: {total_tickets}")
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())
