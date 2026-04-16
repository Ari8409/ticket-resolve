from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

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


# ── R-16: Web server helpers ──────────────────────────────────────────────────

def _dist_dir(settings) -> Path:
    """Resolve the frontend/dist/ path, honouring the FRONTEND_DIST_DIR override."""
    if settings.FRONTEND_DIST_DIR:
        return Path(settings.FRONTEND_DIST_DIR).resolve()
    # app/main.py lives at <repo>/app/main.py → parent.parent = <repo>
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


_FALLBACK_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NOC Platform</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f172a; color: #94a3b8;
           display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    h2   { color: #38bdf8; margin-bottom: 12px; }
    code { background: #1e293b; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
    a    { color: #38bdf8; }
  </style>
</head>
<body>
  <div>
    <h2>NOC Platform — API Running</h2>
    <p>The frontend build is not available yet.</p>
    <p>Run <code>npm run build</code> inside <code>frontend/</code> then restart the server.</p>
    <p>API docs: <a href="/docs">/docs</a></p>
  </div>
</body>
</html>"""


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

    # CORS: in production the SPA is same-origin so no cross-origin calls expected.
    # In development the Vite dev server runs on a different port and needs CORS.
    cors_origins = ["*"] if settings.ENVIRONMENT != "production" else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)

    register_exception_handlers(app)

    # API routes — registered FIRST so they always take priority over the SPA catch-all
    app.include_router(v1_router, prefix="/api/v1")

    # ── R-16: Serve built React SPA ───────────────────────────────────────────
    # Must be registered AFTER /api/v1 so API routes are never shadowed.
    if settings.SERVE_FRONTEND:
        dist = _dist_dir(settings)

        if dist.is_dir() and (dist / "index.html").exists():
            # Mount /assets separately so Starlette can serve them with
            # correct Content-Type headers and future Cache-Control support.
            assets = dist / "assets"
            if assets.is_dir():
                app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

            @app.get("/", include_in_schema=False)
            async def _root():  # noqa: ANN201
                return FileResponse(str(dist / "index.html"))

            @app.get("/{full_path:path}", include_in_schema=False)
            async def _spa(full_path: str):  # noqa: ANN201
                # Belt-and-suspenders: /api/* is matched by the router above and
                # never reaches here, but guard defensively anyway.
                if full_path.startswith("api/"):
                    from fastapi import HTTPException
                    raise HTTPException(status_code=404)
                return FileResponse(str(dist / "index.html"))

        else:
            # frontend/dist/ not built yet — serve a helpful landing page
            @app.get("/", include_in_schema=False)
            async def _root_fallback():  # noqa: ANN201
                return HTMLResponse(_FALLBACK_HTML)

            @app.get("/{full_path:path}", include_in_schema=False)
            async def _catch_fallback(full_path: str):  # noqa: ANN201
                if full_path.startswith("api/"):
                    from fastapi import HTTPException
                    raise HTTPException(status_code=404)
                return HTMLResponse(_FALLBACK_HTML)

    return app


app = create_app()
