# Deployment Document — NOC Dashboard Web Server

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

## 1. Pre-Deployment Checklist

- [ ] Pull latest code: `git pull origin main`
- [ ] Confirm Node.js (≥ 18) is available: `node --version`
- [ ] Confirm Python 3.12 is available: `python --version`
- [ ] Confirm `frontend/node_modules/` is present (run `cd frontend && npm install` if absent)
- [ ] Stop any existing uvicorn process running on port 8000 or 8003
- [ ] Stop any existing Vite dev server running on port 5173
- [ ] Confirm port 8003 is free: no other process bound to it
- [ ] No new Python packages required — `fastapi` and `starlette` already in `pyproject.toml`
- [ ] No new npm packages required — Vite already installed in `frontend/node_modules/`

---

## 2. Deployment Steps

```bash
# From repo root: ticket-resolve/

# Option A: Single command (recommended for production)
bash startup.sh
# startup.sh does: (1) builds frontend, (2) starts uvicorn on port 8003

# Option B: Manual steps (for debugging)
# 1. Build frontend
cd frontend
node node_modules/vite/bin/vite.js build
cd ..

# 2. Start backend (now serves both API and SPA)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003
```

**After R-16 deployment:** access the platform at `http://localhost:8003` only.
The previous dual-URL setup (`http://localhost:8000` + `http://localhost:5173`) is retired.

---

## 3. Configuration Changes

| Item | Previous | New | Where |
|---|---|---|---|
| Server port | 8000 (API) + 5173 (frontend) | 8003 (unified) | `startup.sh`, `Dockerfile`, `vite.config.ts` proxy |
| Frontend served by | Vite dev server | FastAPI StaticFiles | `app/main.py` |
| `SERVE_FRONTEND` | Not present | `True` (default) | `app/config.py` |
| `FRONTEND_DIST_DIR` | Not present | `""` (uses default path) | `app/config.py` |

---

## 4. Database Changes

No database changes in R-16.

| Table | Change | Notes |
|---|---|---|
| No changes | — | R-16 is infrastructure only; `data/tickets.db` schema unchanged |

---

## 5. Rollback Procedure

```bash
# 1. Stop uvicorn on port 8003
# (Ctrl+C or kill the process)

# 2. Revert changed files
git checkout HEAD~1 -- app/main.py
git checkout HEAD~1 -- app/config.py
git checkout HEAD~1 -- frontend/vite.config.ts
git checkout HEAD~1 -- Dockerfile
git rm startup.sh   # startup.sh is new in R-16; remove it

# 3. Restart services in the previous dual-process setup:
# Terminal 1:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Terminal 2:
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

Note: `frontend/dist/` will remain after rollback — it is harmless and can be left in place.

---

## 6. Smoke Test After Deploy

```bash
# 1. SPA root
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://localhost:8003/
# Expected: 200 text/html

# 2. SPA deep links
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8003/dashboard
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8003/triage
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8003/chat
# Expected: 200 for each

# 3. Static asset
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" \
  http://localhost:8003/assets/index-BZx_bd7Z.js
# Expected: 200 text/javascript

# 4. API health check
curl http://localhost:8003/api/v1/health
# Expected: {"status":"ok"}

# 5. API stats (confirms API priority over catch-all)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8003/api/v1/stats
# Expected: 200

# 6. Regression — existing API endpoints
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8003/api/v1/sla/summary
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8003/api/v1/network/graph
# Expected: 200 for each
```

Browser checks:
- Open `http://localhost:8003`
- Confirm NOC Platform title in browser tab
- Confirm all dashboard widgets render (KPI stats, Triage Queue, SLA Compliance, etc.)
- Open DevTools Network — confirm zero 404 errors on assets
- Navigate to `/triage` and `/chat` directly — confirm 200 and correct page render

---

## 7. Monitoring Points

| What | Where | Normal Indicator |
|---|---|---|
| Backend startup | uvicorn terminal | `INFO: Application startup complete` — no `ERROR` lines |
| Frontend build | `startup.sh` terminal | `vite build` output: `dist/index.html` created; no TypeScript errors |
| SPA assets mount | First request log | No `RuntimeError: directory does not exist` in uvicorn stderr |
| Unified port active | `http://localhost:8003/docs` | FastAPI OpenAPI docs accessible; all existing routes listed |
