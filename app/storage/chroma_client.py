import logging

import chromadb
from chromadb.config import Settings as ChromaSettings

log = logging.getLogger(__name__)

_client: chromadb.AsyncHttpClient | None = None


async def get_chroma_client(host: str, port: int) -> chromadb.AsyncHttpClient:
    global _client
    if _client is None:
        _client = await chromadb.AsyncHttpClient(
            host=host,
            port=port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        log.info("Chroma client connected to %s:%s", host, port)
    return _client


async def ensure_collections(
    client: chromadb.AsyncHttpClient,
    ticket_collection: str,
    sop_collection: str,
) -> None:
    """Create collections if they don't exist."""
    existing = {c.name for c in await client.list_collections()}

    if ticket_collection not in existing:
        await client.create_collection(
            name=ticket_collection,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("Created Chroma collection: %s", ticket_collection)

    if sop_collection not in existing:
        await client.create_collection(
            name=sop_collection,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("Created Chroma collection: %s", sop_collection)


async def close_chroma_client() -> None:
    global _client
    _client = None
    log.info("Chroma client closed")
