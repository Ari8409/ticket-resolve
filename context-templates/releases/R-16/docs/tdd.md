# Test Design Document — NOC Dashboard Web Server

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

## 1. Test Scope

| In Scope | Out of Scope |
|---|---|
| `GET /` returns HTTP 200 with `text/html` and correct `<title>` | Automated pytest / Jest framework |
| SPA deep-link routes (`/dashboard`, `/triage`, `/chat`) return 200 | Load / performance testing |
| Static asset serving from `/assets/` returns correct MIME type | Cross-browser testing (Chrome only) |
| API routes take priority over SPA catch-all | TLS / HTTPS configuration |
| `bash startup.sh` builds frontend and starts server on port 8003 | Mobile or responsive layout testing |
| `_FALLBACK_HTML` served when `frontend/dist/index.html` not present | Automated component tests (no new React components) |
| Existing API endpoints unaffected after R-16 deployment | |

**Approach:** Manual smoke tests via curl + browser DevTools. No automated test framework configured.

---

## 2. Test Environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Start command | `bash startup.sh` (builds frontend + starts uvicorn on port 8003) |
| Unified URL | `http://localhost:8003` |
| DB | `data/tickets.db` — existing tickets unchanged |
| Browser | Chrome (latest) |

---

## 3. Unit-Level Test Cases

| ID | Component Under Test | Input | Expected Output |
|---|---|---|---|
| UT-01 | `GET /` | No params, `frontend/dist/index.html` present | HTTP 200; `Content-Type: text/html`; body contains `<title>NOC Platform</title>` |
| UT-02 | `GET /dashboard` | SPA deep link | HTTP 200; `Content-Type: text/html`; body is `index.html` (catch-all route) |
| UT-03 | `GET /triage` | SPA deep link | HTTP 200; `Content-Type: text/html` |
| UT-04 | `GET /chat` | SPA deep link | HTTP 200; `Content-Type: text/html` |
| UT-05 | `GET /assets/index-BZx_bd7Z.js` | Static asset request | HTTP 200; `Content-Type: text/javascript` |
| UT-06 | `GET /api/v1/health` | API route | HTTP 200; `{"status":"ok"}` — API takes priority |
| UT-07 | `GET /api/v1/stats` | API route | HTTP 200 JSON — API takes priority over catch-all |
| UT-08 | `GET /` | `frontend/dist/index.html` absent | HTTP 200; body contains fallback HTML with build instructions |
| UT-09 | `_dist_dir()` helper | Called with default config | Returns path ending in `frontend/dist` relative to repo root |

---

## 4. Integration Test Cases

| ID | Flow | Steps | Expected Result |
|---|---|---|---|
| IT-01 | `startup.sh` end-to-end | 1. Run `bash startup.sh` from repo root 2. Wait for uvicorn startup log | Frontend built (`dist/index.html` created); uvicorn starts on port 8003; `Application startup complete` in log |
| IT-02 | Browser loads SPA | 1. Open `http://localhost:8003` in Chrome 2. Check page title | NOC Platform loads; all existing widgets (KPI stats, triage queue, SLA widget) visible; no 404s in DevTools |
| IT-03 | SPA client-side routing | 1. Navigate to `http://localhost:8003/dashboard` directly (hard reload) 2. Open `http://localhost:8003/triage` | Both deep links return 200; React Router takes over and renders correct page |
| IT-04 | API routes unaffected | 1. `GET /api/v1/health` 2. `GET /api/v1/stats` 3. `GET /api/v1/sla/summary` | All return 200 JSON; no interference from SPA catch-all |
| IT-05 | Docker image | 1. `docker build -t noc-platform .` 2. `docker run -p 8003:8003 noc-platform` 3. `curl http://localhost:8003/` | HTTP 200 with NOC Platform HTML; frontend dist copied correctly into image |

---

## 5. Edge Cases

| Case | Description | Expected Behaviour |
|---|---|---|
| `frontend/dist/` not built | `startup.sh` not run; `frontend/dist/` absent | `GET /` returns HTTP 200 with `_FALLBACK_HTML` (build instructions); no 500 error |
| Port 8003 already in use | Another process occupies port 8003 | uvicorn exits with `[Errno 98] Address already in use`; meaningful error message |
| Unknown path under `/api/` | `GET /api/v1/nonexistent` | HTTP 404 JSON `{"detail":"Not Found"}` — API 404 not caught by SPA catch-all |
| Path with file extension | `GET /favicon.ico` | Served by SPA catch-all if not in `/assets/`; returns `index.html` with 200 |
| `SERVE_FRONTEND=False` | Config flag set to False | StaticFiles not mounted; `GET /` returns 404; API-only mode active |
| Concurrent requests | Multiple clients request `/` and `/api/` simultaneously | Both served correctly; no race condition from shared `_dist_dir()` helper |

---

## 6. Performance Benchmarks

| Endpoint | Expected p50 | Expected p99 | Method |
|---|---|---|---|
| `GET /` (index.html) | < 20 ms | < 50 ms | `curl -w "%{time_total}" http://localhost:8003/` |
| `GET /assets/*.js` | < 10 ms | < 30 ms | `curl -w "%{time_total}" http://localhost:8003/assets/index-BZx_bd7Z.js` |
| `GET /api/v1/health` | < 10 ms | < 30 ms | `curl -w "%{time_total}" http://localhost:8003/api/v1/health` |
