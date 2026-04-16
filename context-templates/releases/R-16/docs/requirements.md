# Requirements Document — NOC Dashboard Web Server

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

## 1. Business Objective

The NOC Platform has historically required two separate processes to run in production: the FastAPI backend and the Vite development server. This dual-process setup introduces unnecessary operational complexity, exposes development tooling in production, and requires port management for both services. This release consolidates production serving by configuring FastAPI to serve the built React SPA directly from its own process, eliminating the Vite dev server dependency in production. The result is a single command (`bash startup.sh`) that builds the frontend and starts the unified web server on port 8003.

---

## 2. Stakeholders

| Role               | Name / Team       | Interest                                              |
|--------------------|-------------------|-------------------------------------------------------|
| NOC Operations Manager | Operations    | Simplified deployment and single URL for the platform |
| Platform Developer | NOC Platform Team | Reduced operational complexity; single-process deployment |
| DevOps / Infra     | Infrastructure    | Docker image consolidation; fewer open ports          |

---

## 3. Functional Requirements

| ID    | Description                                                                                   | Priority |
|-------|-----------------------------------------------------------------------------------------------|---------|
| FR-01 | FastAPI shall serve the built React SPA static assets from `frontend/dist/` at `/assets`     | Must    |
| FR-02 | `GET /` shall return HTTP 200 with the React SPA `index.html` (`<title>NOC Platform</title>`) | Must   |
| FR-03 | SPA deep-link routes (`/dashboard`, `/triage`, `/chat`, etc.) shall return HTTP 200 with `index.html` via catch-all route | Must |
| FR-04 | API routes under `/api/v1/` shall take priority over the SPA catch-all route                 | Must    |
| FR-05 | A `startup.sh` script shall build the frontend and start uvicorn on port 8003 in one command | Must    |
| FR-06 | The Dockerfile shall copy `frontend/dist/` into the image and expose port 8003               | Must    |
| FR-07 | `SERVE_FRONTEND` config flag shall allow disabling SPA serving (e.g. for local API-only dev) | Should  |
| FR-08 | CORS configuration shall be tightened for production (no wildcard origins in production mode) | Should  |

---

## 4. Non-Functional Requirements

| Category      | Requirement                                                                     |
|---------------|---------------------------------------------------------------------------------|
| Performance   | SPA `index.html` served within 50 ms on localhost; static assets served with correct MIME types |
| Reliability   | Single process failure stops both API and frontend — acceptable for NOC workstation context |
| Security      | CORS restricted to known origins in production; Vite dev server not running in production |
| Portability   | Unified port 8003 replaces dual-port setup (8000 API + 5173 frontend)          |
| Operability   | `bash startup.sh` is the single deployment command; no manual Vite step required |
| Compatibility | Existing API clients unaffected — all `/api/v1/` routes unchanged               |

---

## 5. Assumptions & Constraints

- `frontend/dist/` is produced by `npm run build` (Vite) before the backend starts
- `startup.sh` runs in the repo root and has access to Node.js and Python environments
- The platform is deployed on a single host (no multi-node load balancing)
- API routes always take priority over the SPA catch-all (FastAPI route ordering)

---

## 6. Out of Scope

- CDN or reverse-proxy configuration (Nginx, Caddy)
- HTTPS / TLS termination
- New API endpoints (R-16 adds no new REST routes)
- New React components or UI changes
- Database schema changes

---

## 7. Acceptance Criteria

| AC ID | Maps to | Criterion                                                                                          |
|-------|---------|----------------------------------------------------------------------------------------------------|
| AC-01 | FR-02   | `GET http://localhost:8003/` returns HTTP 200 with `Content-Type: text/html` and body containing `<title>NOC Platform</title>` |
| AC-02 | FR-03   | `GET http://localhost:8003/dashboard` returns HTTP 200 with `text/html` (SPA deep link works)      |
| AC-03 | FR-01   | `GET http://localhost:8003/assets/index-BZx_bd7Z.js` returns HTTP 200 with `text/javascript`       |
| AC-04 | FR-04   | `GET http://localhost:8003/api/v1/health` returns `{"status":"ok"}` (API takes priority)           |
| AC-05 | FR-04   | `GET http://localhost:8003/api/v1/stats` returns HTTP 200 JSON (API takes priority over catch-all) |
| AC-06 | FR-05   | `bash startup.sh` builds frontend and starts uvicorn on port 8003 without manual steps             |
| AC-07 | —       | SDLC Gate 3 code scan passes with 0 errors and 0 warnings on `app/main.py` and `app/config.py`    |

---

## 8. Dependencies

| Dependency                  | Type       | Notes                                            |
|-----------------------------|------------|--------------------------------------------------|
| R-2 — FastAPI REST Layer     | Predecessor | FastAPI application instance (`app/main.py`) in place |
| R-1 — Core Dashboard         | Predecessor | React SPA built with Vite; `frontend/dist/` produced by `npm run build` |
| Node.js (≥ 18)               | Runtime    | Required by `startup.sh` to run Vite build       |
| Python 3.12                  | Runtime    | Required to run uvicorn                           |
