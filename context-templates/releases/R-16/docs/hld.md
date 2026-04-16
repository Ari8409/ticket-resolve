# High-Level Design — NOC Dashboard Web Server

## Document Metadata

| Field      | Value                                           |
|------------|-------------------------------------------------|
| Release    | Release 16 — NOC Dashboard Web Server           |
| RICEF ID   | R-16                                            |
| RICEF Type | I (Interface)                                   |
| Author     | NOC Platform Team                               |
| Date       | 2026-04-16                                      |
| Version    | 1.0                                             |
| Status     | Approved                                        |

## Platform Reference

- Backend: FastAPI 0.115 · Python 3.12 · SQLite (`data/tickets.db`) · LangChain 0.3 · ChromaDB
- Frontend: React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5
- Repository path: `ticket-resolve/`

---

## 1. Architecture Overview

```
                    Before R-16                       After R-16
                    ───────────                       ──────────

Browser ──────── http://localhost:5173            Browser ──── http://localhost:8003
                  │                                              │
                  │ (Vite dev server)              FastAPI (uvicorn :8003)
                  └── proxy /api/* ──────────────────── /assets/*  → StaticFiles(frontend/dist/assets)
                                    │                   GET /        → index.html (fallback HTML)
                                HTTP :8000             GET /{path}  → index.html (SPA catch-all)
                          FastAPI (uvicorn)             /api/v1/*   → existing API routers
                              /api/v1/*
```

**Key change:** FastAPI mounts `frontend/dist/assets/` as a `StaticFiles` directory and adds two catch-all routes that serve `frontend/dist/index.html` for all non-API paths. The Vite dev server is no longer used in production.

---

## 2. Component Inventory

| Component            | Layer    | File Path                                        | Responsibility                                          |
|----------------------|----------|--------------------------------------------------|---------------------------------------------------------|
| `_dist_dir()` helper  | Backend  | `app/main.py`                                    | Resolves `frontend/dist/` path relative to repo root    |
| `_FALLBACK_HTML`      | Backend  | `app/main.py`                                    | Inline fallback HTML served if `index.html` not found   |
| StaticFiles mount     | Backend  | `app/main.py`                                    | Mounts `frontend/dist/assets/` at `/assets`             |
| `GET /`               | Backend  | `app/main.py`                                    | Serves `frontend/dist/index.html` (SPA root)            |
| `GET /{full_path}`    | Backend  | `app/main.py`                                    | SPA catch-all; serves `index.html` for deep links       |
| `SERVE_FRONTEND`      | Config   | `app/config.py`                                  | Feature flag to enable/disable SPA serving              |
| `FRONTEND_DIST_DIR`   | Config   | `app/config.py`                                  | Override path to frontend dist directory                |
| `vite.config.ts`      | Frontend | `frontend/vite.config.ts`                        | Explicit `outDir: 'dist'`; proxy target updated to 8003 |
| `Dockerfile`          | Infra    | `Dockerfile`                                     | Copies `frontend/dist/` into image; exposes port 8003   |
| `startup.sh`          | Infra    | `startup.sh`                                     | Builds frontend then starts uvicorn on port 8003        |

---

## 3. API Contract Summary

No new API endpoints are introduced in R-16. All existing `/api/v1/` routes are unchanged.

| Method | Path                      | Request Body | Response                    | Notes                                        |
|--------|---------------------------|--------------|-----------------------------|----------------------------------------------|
| GET    | `/`                       | —            | `text/html` (index.html)    | New: serves React SPA root                   |
| GET    | `/{full_path:path}`       | —            | `text/html` (index.html)    | New: SPA catch-all for deep links            |
| GET    | `/assets/{file}`          | —            | Static file (JS/CSS/assets) | New: StaticFiles mount from `frontend/dist/assets/` |
| GET    | `/api/v1/*`               | —            | JSON                        | Unchanged: existing API routes take priority  |

---

## 4. Data Store Design

No new database tables, columns, or schema changes in R-16. The existing `data/tickets.db` schema is unmodified.

---

## 5. External Integrations

None. R-16 is an infrastructure consolidation release. No external services, webhooks, or third-party APIs are added.

---

## 6. Security Considerations

- CORS configuration tightened for production — wildcard origin removed; origins restricted to `http://localhost:8003` in production mode
- Vite dev server (`--host 0.0.0.0 --port 5173`) no longer runs in production, reducing attack surface
- StaticFiles serves only the contents of `frontend/dist/assets/` — no directory listing
- SPA catch-all route only serves `index.html` — no path traversal risk

---

## 7. Technology Decisions

| Decision              | Choice                              | Rationale                                                                 |
|-----------------------|-------------------------------------|---------------------------------------------------------------------------|
| SPA serving           | FastAPI `StaticFiles` + catch-all   | Zero new dependencies; Starlette `StaticFiles` is built into FastAPI      |
| Port                  | 8003 (single unified port)          | Replaces dual-port setup; avoids conflict with common ports 8000/5173     |
| Fallback HTML         | Inline `_FALLBACK_HTML` constant    | Avoids FileNotFoundError crash when `frontend/dist/` not yet built        |
| Build orchestration   | `startup.sh` shell script           | Simple, portable; no additional build tooling (Make, Docker Compose) required |
| Vite `outDir`         | Explicit `dist` in `vite.config.ts` | Prevents accidental output to a non-standard directory during CI builds   |
