# Deployment Document — [FILL: Feature/Release Name]

## Document Metadata

| Field | Value |
|---|---|
| Release | [FILL: e.g., Release 15 — Feature Name] |
| RICEF ID | [FILL: R-xx] |
| RICEF Type | [FILL: R / I / C / E / F] |
| Author | NOC Platform Team |
| Date | [FILL: YYYY-MM-DD] |
| Version | [FILL: e.g., 1.0] |
| Status | [FILL: Draft / Review / Approved] |

## Platform Reference [PRE-FILLED]

- Backend: FastAPI 0.115 · Python 3.12 · SQLite (`data/tickets.db`) · LangChain 0.3 · ChromaDB
- Frontend: React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5
- Repository path: `ticket-resolve/`

---

## 1. Pre-Deployment Checklist

- [ ] Pull latest code from branch: `git pull origin [FILL: branch-name]`
- [ ] [FILL: e.g., Install new Python dependencies: `pip install -e .`]
- [ ] [FILL: e.g., Install new npm packages: `cd frontend && npm install`]
- [ ] [FILL: e.g., Set environment variable `NOMINATIM_USER_AGENT=NOC-Dashboard/1.0`] — or confirm default in code
- [ ] Confirm `data/` directory exists and `tickets.db` is accessible
- [ ] [FILL: any other pre-conditions — e.g., ChromaDB collection populated, Chroma server running]
- [ ] Stop existing uvicorn process if running

---

## 2. Deployment Steps

Execute in order from the repository root (`ticket-resolve/`):

```bash
# 1. Install / update Python dependencies
pip install -e .

# 2. Install / update frontend dependencies
cd frontend
npm install

# 3. [FILL: Add release-specific steps here, e.g.:]
# npm install leaflet react-leaflet @types/leaflet   ← only if new npm packages added

# 4. Build frontend for production (optional — skip if running dev server)
npm run build

# 5. Return to repo root
cd ..

# 6. Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 7. Start frontend dev server (if not using built dist)
# Open a second terminal:
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

---

## 3. Configuration Changes

| Item | Previous Value | New Value | Where Changed |
|---|---|---|---|
| [FILL: e.g., New env var `GEOCACHE_DB_PATH`] | Not set | `data/tickets.db` | `app/api/v1/locations.py:12` |
| [FILL: add rows — or state "No configuration changes"] | | | |

---

## 4. Database Changes

<!-- All schema changes are applied lazily on first API call — no manual SQL needed. -->

| Table | Change | Applied By |
|---|---|---|
| [FILL: e.g., `location_geocache`] | New table created | `app/api/v1/locations.py` — `ensure_geocache_table()` called at endpoint startup |
| [FILL: e.g., `telco_tickets`] | New column `location_id TEXT` | `ALTER TABLE` in `app/api/v1/locations.py` startup hook |
| [FILL: "None" if no DB changes] | | |

**Rollback note:** SQLite `ADD COLUMN` cannot be undone. However, the new column is nullable with no DEFAULT constraints — existing rows and queries are unaffected.

---

## 5. Rollback Procedure

<!-- SQLite schema additions are not reversible, but code changes are. -->

1. Stop uvicorn: `Ctrl+C`
2. Revert code: `git checkout [FILL: previous-commit-sha] -- [FILL: changed files]`
   ```bash
   # Example:
   git checkout HEAD~1 -- app/api/v1/router.py app/api/v1/locations.py
   git checkout HEAD~1 -- frontend/src/components/[FILL]Widget.tsx
   ```
3. Restart uvicorn and frontend
4. [FILL: note any irreversible side effects — e.g., "New `location_geocache` table remains in DB but is harmless if endpoint is removed"]

---

## 6. Smoke Test After Deploy

Run these checks immediately after deployment:

```bash
# 1. Health check
curl http://localhost:8000/

# 2. New endpoint
curl "http://localhost:8000/api/v1/[FILL: path]"
# Expected: HTTP 200, JSON body with [FILL: key field]

# 3. Existing endpoint (regression)
curl "http://localhost:8000/api/v1/telco-tickets/stats"
# Expected: HTTP 200, `total` field present

# 4. [FILL: add more curl checks for this release]
```

Browser checks:
- Open `http://localhost:5173`
- [FILL: e.g., "Confirm 'High-Volume Ticket Nodes' widget visible on Dashboard"]
- [FILL: e.g., "Confirm Ticket Location Map renders with Singapore-centred view"]
- [FILL: add more]

---

## 7. Monitoring Points

| What to Watch | Where | Normal Indicator |
|---|---|---|
| Backend startup | uvicorn terminal | `INFO: Application startup complete` — no `ERROR` lines |
| New table created | uvicorn terminal | [FILL: e.g., `INFO: location_geocache table ready`] |
| Nominatim calls (first load) | uvicorn terminal | [FILL: e.g., `INFO: Geocoding address: ...` lines with ~1 s gaps] |
| Frontend compilation | Vite terminal | `VITE vX.X.X  ready in Xms` — no TypeScript errors |
| API schema | `http://localhost:8000/docs` | New endpoint listed under `/api/v1/[FILL: tag]` |
| Browser console | Chrome DevTools | No `TypeError` or `404` errors on Dashboard load |
