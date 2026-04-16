from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware, TimingMiddleware
from app.storage.chroma_client import (
    close_chroma_client,
    ensure_collections,
    get_chroma_client,
)
from app.storage.repositories import create_tables, init_engine
from app.api.v1.sla import ensure_sla_table


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    # Initialize async DB
    init_engine(settings.DATABASE_URL)
    await create_tables()

    # Initialize SLA targets table (R-15) — APIRouter.on_event is not supported;
    # must be called from the main app lifespan instead.
    await ensure_sla_table()

    # Initialize Chroma
    chroma = await get_chroma_client(settings.CHROMA_HOST, settings.CHROMA_PORT)
    await ensure_collections(chroma, settings.TICKET_COLLECTION, settings.SOP_COLLECTION)
    app.state.chroma = chroma

    yield

    await close_chroma_client()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Ticket Resolution Platform",
        description="Agentic IT support ticket resolution using LangChain + Chroma",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)

    register_exception_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
