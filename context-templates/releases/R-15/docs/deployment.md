# Deployment Document — SLA Tracking Table & Dashboard Widget

## Document Metadata

| Field      | Value                                           |
|------------|-------------------------------------------------|
| Release    | Release 15 — SLA Tracking Table & Dashboard Widget |
| RICEF ID   | R-15                                            |
| RICEF Type | C                                               |
| Author     | NOC Platform Team                               |
| Date       | 2026-04-14                                      |
| Version    | 1.0                                             |
| Status     | Approved                                        |

## Platform Reference [PRE-FILLED]

- Backend: FastAPI 0.115 · Python 3.12 · SQLite (`data/tickets.db`) · LangChain 0.3 · ChromaDB
- Frontend: React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5
- Repository path: `ticket-resolve/`

---

## 1. Pre-Deployment Checklist

- [ ] Pull latest code: `git pull origin main`
- [ ] Confirm `data/` directory exists and `data/tickets.db` is accessible
- [ ] No new Python packages required — `aiosqlite` and `fastapi` already in `pyproject.toml`
- [ ] No new npm packages required — `recharts` and `lucide-react` already installed
- [ ] Stop existing uvicorn process if running

---

## 2. Deployment Steps

```bash
# From repo root: ticket-resolve/

# 1. Install / confirm Python dependencies (no new packages for R-15)
pip install -e .

# 2. Install / confirm frontend dependencies (no new packages for R-15)
cd frontend
npm install

# 3. Build frontend for production (optional — skip if running dev server)
npm run build
cd ..

# 4. Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Start frontend dev server (separate terminal)
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

---

## 3. Configuration Changes

No new environment variables or configuration changes. R-15 is self-contained.

| Item | Previous | New | Where |
|---|---|---|---|
| No changes | — | — | — |

---

## 4. Database Changes

| Table | Change | Applied By | Notes |
|---|---|---|---|
| `sla_targets` | **New table** (8 seed rows) | `app/api/v1/sla.py` — `ensure_sla_table()` called automatically on first `/sla/*` request | Lazy creation; no manual SQL needed |

**No changes to `telco_tickets`** — `updated_at` and `fault_type` columns already exist.

---

## 5. Rollback Procedure

```bash
# 1. Stop uvicorn and Vite
# 2. Revert the 4 changed/new files:
git checkout HEAD~1 -- app/api/v1/sla.py
git checkout HEAD~1 -- app/api/v1/router.py
git checkout HEAD~1 -- frontend/src/api/client.ts
git checkout HEAD~1 -- frontend/src/components/SLAWidget.tsx
git checkout HEAD~1 -- frontend/src/pages/DashboardPage.tsx

# 3. Restart services
```

Note: The `sla_targets` table will remain in `data/tickets.db` after rollback — it is harmless and will be ignored once the router is reverted.

---

## 6. Smoke Test After Deploy

```bash
# 1. Health check
curl http://localhost:8000/api/v1/health

# 2. SLA targets seeded
curl http://localhost:8000/api/v1/sla/targets
# Expected: HTTP 200, "targets" array with 8 rows including "node_down", "signal_loss", etc.

# 3. SLA summary
curl http://localhost:8000/api/v1/sla/summary
# Expected: HTTP 200, "total_resolved" > 0, "compliance_rate" between 0 and 100

# 4. Update a target
curl -X PUT http://localhost:8000/api/v1/sla/targets/node_down \
  -H "Content-Type: application/json" \
  -d '{"target_hours": 4}'
# Expected: HTTP 200, {"fault_type": "node_down", "target_hours": 4, ...}

# 5. Regression — existing endpoints
curl http://localhost:8000/api/v1/stats
curl http://localhost:8000/api/v1/network/graph
```

Browser checks:
- Open `http://localhost:5173`
- Confirm "SLA Compliance" widget visible on Dashboard below the Ticket Location Map
- Confirm KPI row shows compliance %, breach count, avg resolution hours
- Confirm horizontal bar chart renders with colour-coded bars (green/amber/red)
- Hover a bar — tooltip shows fault type, target hours, breach count

---

## 7. Monitoring Points

| What | Where | Normal Indicator |
|---|---|---|
| Backend startup | uvicorn terminal | `INFO: Application startup complete` — no `ERROR` lines |
| sla_targets created | First request log | No explicit log line needed — table created silently; check via `/sla/targets` |
| API endpoints live | `http://localhost:8000/docs` | `/sla/summary`, `/sla/targets`, `/sla/targets/{fault_type}` listed under **SLA** tag |
| Frontend compiled | Vite terminal | `VITE vX.X.X ready in Xms` — no TypeScript errors |
| SLAWidget loaded | Browser console | No `TypeError` or `404` errors in DevTools console |
