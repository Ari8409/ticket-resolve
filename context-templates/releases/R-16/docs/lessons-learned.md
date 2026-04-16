# Lessons Learned — NOC Dashboard Web Server

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

## 1. Lessons Learned

### Lesson 1: SPA catch-all route must be registered last to avoid shadowing API routes

**Severity:** High
**Area:** FastAPI / Routing

When FastAPI evaluates routes, it uses registration order. A `GET /{full_path:path}` catch-all registered before the API include_router calls would intercept all `/api/v1/` requests and return HTML instead of JSON, silently breaking every API client. During R-16 development, an early prototype registered the catch-all before `include_router` — all API calls returned 200 `text/html` with no error, making the bug difficult to spot without checking response bodies. The fix was to ensure all `include_router` calls remain before the SPA catch-all registration.

### Lesson 2: Fallback HTML prevents startup crash when frontend is not yet built

**Severity:** Medium
**Area:** FastAPI / Reliability

Without the `_FALLBACK_HTML` constant, `spa_root()` would raise `FileNotFoundError` on any request to `GET /` if `frontend/dist/index.html` did not exist (e.g., on a fresh clone before running `startup.sh`). This would result in a 500 Internal Server Error with no helpful message. Adding an inline fallback HTML string that instructs the developer to run `bash startup.sh` converts a confusing 500 into a clear 200 with actionable guidance. Infrastructure releases should always degrade gracefully.

### Lesson 3: Vite proxy port must match the unified server port to avoid dev-mode confusion

**Severity:** Low
**Area:** Frontend / Developer Experience

After R-16 changed the backend port from 8000 to 8003, the Vite dev server proxy in `vite.config.ts` still pointed to port 8000. This caused all `/api/` requests to fail during local frontend development (`npm run dev`) until the proxy target was updated to `http://localhost:8003`. The fix was to update `vite.config.ts` as part of the same commit. The lesson is that port changes must be propagated to all dependent configurations atomically.

---

## 2. Root Cause

| Lesson | Root Cause |
|---|---|
| Lesson 1 — catch-all shadowing API routes | FastAPI route registration order is significant; catch-all routes are greedy and will match before any later route is evaluated. No runtime warning is emitted when a catch-all shadows later routes. |
| Lesson 2 — missing dist directory causes 500 | `Path.read_text()` raises `FileNotFoundError` if the file does not exist. The error propagates as an unhandled exception in FastAPI, resulting in a 500 with an unhelpful traceback. |
| Lesson 3 — stale proxy port in vite.config.ts | Port configuration is duplicated across `startup.sh`, `Dockerfile`, and `vite.config.ts`. When a port is changed, it must be updated in all locations simultaneously — there is no single source of truth for port configuration. |

---

## 3. Fix Applied

| Lesson | Fix Applied | Guardrail Added |
|---|---|---|
| Lesson 1 | Moved SPA catch-all registration to after all `include_router` calls in `app/main.py`. Added code comment `# SPA catch-all — must be last route` to prevent future regression. | Code review checklist: verify route registration order in `app/main.py` when adding new routes |
| Lesson 2 | Added `_FALLBACK_HTML` constant and wrapped `index.html` reads in existence checks; returns fallback HTML with build instructions instead of raising exceptions | `startup.sh` is the documented single entry point; fallback HTML instructs developer if dist is absent |
| Lesson 3 | Updated `vite.config.ts` proxy target to `http://localhost:8003` in the same commit as the port change; added comment `# Keep in sync with startup.sh` adjacent to the port value | Port change checklist: grep for all port references before committing a port change |
