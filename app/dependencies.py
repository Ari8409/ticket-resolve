from functools import lru_cache
from typing import Annotated

import chromadb
from fastapi import Depends, Request
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.alarms.checker import AlarmChecker
from app.alarms.store import AlarmStore
from app.config import Settings, get_settings
from app.correlation.engine import CorrelationEngine
from app.maintenance.checker import MaintenanceChecker
from app.maintenance.store import MaintenanceStore
from app.matching.embedder import TicketEmbedder
from app.matching.engine import MatchingEngine
from app.matching.pipeline import TicketEmbeddingPipeline
from app.matching.st_embedder import SentenceTransformerEmbedder
from app.matching.ticket_store import TicketStore
from app.recommendation.agent import ResolutionAgent
from app.sop.retriever import SOPRetriever
from app.sop.sop_store import SOPStore
from app.storage.repositories import TicketRepository, get_session
from app.storage.telco_repositories import TelcoTicketRepository


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------
# Chroma collections
# ---------------------------------------------------------------------------

async def get_ticket_collection(request: Request, settings: SettingsDep) -> chromadb.AsyncCollection:
    client: chromadb.AsyncHttpClient = request.app.state.chroma
    return await client.get_collection(settings.TICKET_COLLECTION)


async def get_sop_collection(request: Request, settings: SettingsDep) -> chromadb.AsyncCollection:
    client: chromadb.AsyncHttpClient = request.app.state.chroma
    return await client.get_collection(settings.SOP_COLLECTION)


# ---------------------------------------------------------------------------
# Domain services
# ---------------------------------------------------------------------------

def get_embedder(settings: SettingsDep) -> TicketEmbedder | SentenceTransformerEmbedder:
    """
    Returns the configured embedding backend.

    EMBEDDING_BACKEND=sentence_transformers  → SentenceTransformerEmbedder (local, no API key)
    EMBEDDING_BACKEND=openai                 → TicketEmbedder (OpenAI API)

    Both share the same embed_text / embed_batch interface so MatchingEngine
    works with either without modification.

    NOTE: SentenceTransformerEmbedder loads the model at construction time
    (~80 MB for all-MiniLM-L6-v2).  FastAPI calls this once per request via
    Depends() — wire it as an app-level singleton in production using
    app.state or a module-level cached instance.
    """
    if settings.EMBEDDING_BACKEND == "sentence_transformers":
        return SentenceTransformerEmbedder(
            model_name=settings.ST_MODEL,
            device=settings.ST_DEVICE,
        )
    return TicketEmbedder(model=settings.EMBEDDING_MODEL, api_key=settings.OPENAI_API_KEY)


def get_st_embedder(settings: SettingsDep) -> SentenceTransformerEmbedder:
    """
    Always returns a SentenceTransformerEmbedder regardless of EMBEDDING_BACKEND.

    Used by TicketEmbeddingPipeline which is explicitly sentence-transformers based.
    """
    return SentenceTransformerEmbedder(
        model_name=settings.ST_MODEL,
        device=settings.ST_DEVICE,
    )


async def get_ticket_store(
    collection: Annotated[chromadb.AsyncCollection, Depends(get_ticket_collection)],
) -> TicketStore:
    return TicketStore(collection)


async def get_sop_store(
    collection: Annotated[chromadb.AsyncCollection, Depends(get_sop_collection)],
) -> SOPStore:
    return SOPStore(collection)


async def get_matching_engine(
    embedder: Annotated[TicketEmbedder, Depends(get_embedder)],
    ticket_store: Annotated[TicketStore, Depends(get_ticket_store)],
    settings: SettingsDep,
) -> MatchingEngine:
    return MatchingEngine(
        embedder=embedder,
        ticket_store=ticket_store,
        top_k=settings.SIMILARITY_TOP_K,
        score_threshold=settings.SIMILARITY_SCORE_THRESHOLD,
    )


async def get_sop_retriever(
    embedder: Annotated[TicketEmbedder, Depends(get_embedder)],
    sop_store: Annotated[SOPStore, Depends(get_sop_store)],
    settings: SettingsDep,
) -> SOPRetriever:
    return SOPRetriever(embedder=embedder, sop_store=sop_store, top_k=settings.SOP_TOP_K)


async def get_embedding_pipeline(
    settings: SettingsDep,
    st_embedder: Annotated[SentenceTransformerEmbedder, Depends(get_st_embedder)],
    matching_engine: Annotated[MatchingEngine, Depends(get_matching_engine)],
) -> TicketEmbeddingPipeline:
    """
    Provides a TicketEmbeddingPipeline backed by sentence-transformers.

    The pipeline embeds incoming ticket descriptions locally and queries
    the Chroma 'tickets' collection for top-k resolved similar tickets
    using cosine similarity.
    """
    return TicketEmbeddingPipeline(
        embedder=st_embedder,
        engine=matching_engine,
        top_k=settings.EMBEDDING_PIPELINE_TOP_K,
        score_threshold=settings.EMBEDDING_PIPELINE_THRESHOLD,
    )


async def get_resolution_agent(
    settings: SettingsDep,
    matching_engine: Annotated[MatchingEngine, Depends(get_matching_engine)],
    sop_retriever: Annotated[SOPRetriever, Depends(get_sop_retriever)],
) -> ResolutionAgent:
    llm = ChatOpenAI(model=settings.LLM_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0)
    return ResolutionAgent(llm=llm, sop_retriever=sop_retriever, matching_engine=matching_engine)


# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------

async def get_repo() -> TicketRepository:
    async with get_session() as session:
        yield TicketRepository(session)


async def get_telco_repo() -> TelcoTicketRepository:
    async with get_session() as session:
        yield TelcoTicketRepository(session)


# ---------------------------------------------------------------------------
# Alarm subsystem
# ---------------------------------------------------------------------------

async def get_alarm_store() -> AlarmStore:
    async with get_session() as session:
        yield AlarmStore(session)


async def get_alarm_checker(
    alarm_store: Annotated[AlarmStore, Depends(get_alarm_store)],
) -> AlarmChecker:
    return AlarmChecker(store=alarm_store)


# ---------------------------------------------------------------------------
# Maintenance subsystem
# ---------------------------------------------------------------------------

async def get_maintenance_store() -> MaintenanceStore:
    async with get_session() as session:
        yield MaintenanceStore(session)


async def get_maintenance_checker(
    maint_store: Annotated[MaintenanceStore, Depends(get_maintenance_store)],
) -> MaintenanceChecker:
    return MaintenanceChecker(store=maint_store)


# ---------------------------------------------------------------------------
# Correlation engine
# ---------------------------------------------------------------------------

async def get_correlation_engine(
    alarm_checker: Annotated[AlarmChecker, Depends(get_alarm_checker)],
    maint_checker: Annotated[MaintenanceChecker, Depends(get_maintenance_checker)],
    matching_engine: Annotated[MatchingEngine, Depends(get_matching_engine)],
    sop_retriever: Annotated[SOPRetriever, Depends(get_sop_retriever)],
    settings: SettingsDep,
) -> CorrelationEngine:
    return CorrelationEngine(
        alarm_checker=alarm_checker,
        maintenance_checker=maint_checker,
        matching_engine=matching_engine,
        sop_retriever=sop_retriever,
        similar_top_k=settings.CORRELATION_SIMILAR_K,
        sop_top_k=settings.CORRELATION_SOP_K,
    )
