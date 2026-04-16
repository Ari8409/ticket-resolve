# Test Design Document — [FILL: Feature/Release Name]

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

## 1. Test Scope

| In Scope | Out of Scope |
|---|---|
| [FILL: e.g., API endpoint happy-path and edge cases] | Automated unit test framework (none configured) |
| [FILL: e.g., Frontend component rendering and interactions] | Load / stress testing |
| [FILL: e.g., SQLite schema creation on startup] | Cross-browser compatibility (Chrome only for internal tool) |
| [FILL: e.g., React Query cache sharing between widgets] | [FILL: add exclusions] |

**Test approach:** Manual smoke tests executed by developer. No pytest or Jest framework is used on this project.

---

## 2. Test Environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Backend command | `uvicorn app.main:app --reload --port 8000` |
| Frontend command | `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173` |
| DB | `data/tickets.db` — [FILL: approximate row count, e.g., ~1 600 tickets] |
| Browser | Chrome (latest) |
| Network | [FILL: e.g., Local LAN — Nominatim calls require internet access] |

---

## 2a. Data Pre-Flight

<!-- Complete this section BEFORE writing Unit/Integration test cases.
     If any computation feature relies on DB columns, verify the source data is non-trivial.
     This section is mandatory — the Tech Lead's Build gate checklist requires it. -->

### Timestamp Variance Check

Run the following query to confirm resolved tickets have non-trivial elapsed times:

```sql
-- How many resolved/closed tickets have created_at != updated_at?
SELECT
    COUNT(*)                                                         AS total_resolved,
    SUM(CASE WHEN created_at != updated_at THEN 1 ELSE 0 END)       AS has_elapsed_time,
    ROUND(
        100.0 * SUM(CASE WHEN created_at != updated_at THEN 1 ELSE 0 END) / COUNT(*),
        1
    )                                                                AS pct_with_elapsed
FROM telco_tickets
WHERE status IN ('resolved', 'closed');
```

| Result | Acceptable? | Action if not |
|---|---|---|
| `pct_with_elapsed` ≥ 50% | Yes — proceed | N/A |
| `pct_with_elapsed` < 50% | **No — BLOCK** | Re-seed `updated_at` or redesign metric |
| `pct_with_elapsed` = 0% | **No — BLOCK** | Bulk-load indicator — see R-15 post-mortem |

**Actual result:** [FILL: paste query output here]

### NULL Rate Check for Computation Columns

```sql
SELECT
    COUNT(*)                                                              AS total,
    SUM(CASE WHEN fault_type    IS NULL OR fault_type    = '' THEN 1 ELSE 0 END) AS null_fault_type,
    SUM(CASE WHEN status        IS NULL OR status        = '' THEN 1 ELSE 0 END) AS null_status,
    SUM(CASE WHEN created_at    IS NULL                       THEN 1 ELSE 0 END) AS null_created_at,
    SUM(CASE WHEN updated_at    IS NULL                       THEN 1 ELSE 0 END) AS null_updated_at
FROM telco_tickets;
```

**Actual result:** [FILL: paste query output here]

Any column with NULL rate > 30% must be noted in the Test Scope as a known limitation.

### Data Quality Pre-Flight Tool

```bash
# Run from context-templates/ directory
python data_quality_check.py --db ../data/tickets.db

# Or via workflow (records result in state.json for Gate 2 prerequisite)
python sdlc_workflow.py data-check [FILL: R-xx]
```

**Result:** [FILL: PASS / PASS with warnings / FAIL — paste summary line here]

---

## 3. Unit-Level Test Cases

<!-- "Unit" here = testing a single endpoint or function in isolation via curl or direct function call -->

| ID | Component Under Test | Input | Expected Output |
|---|---|---|---|
| UT-01 | `GET /api/v1/[FILL: path]` | No params | HTTP 200, body matches `[FILL]Response` schema |
| UT-02 | `GET /api/v1/[FILL: path]` | [FILL: edge-case param] | [FILL: expected behaviour] |
| UT-03 | [FILL: function name] | [FILL: input] | [FILL: expected return value] |
| [FILL: add rows] | | | |

---

## 4. Integration Test Cases

<!-- End-to-end flows: browser → API → DB → (external service) → API → browser -->

| ID | Flow Description | Steps | Expected Result |
|---|---|---|---|
| IT-01 | [FILL: e.g., Dashboard load triggers HotNodesWidget] | 1. Open Dashboard\n2. Observe DevTools Network | [FILL: e.g., Single call to `/network/graph`; widget renders 10 rows] |
| IT-02 | [FILL: e.g., Location map first load] | 1. Clear geocache\n2. Open Dashboard\n3. Wait for map | [FILL: e.g., Spinner shown → Nominatim calls visible in backend logs → Map renders markers] |
| IT-03 | [FILL: e.g., Location map second load (cache hit)] | Reload dashboard | [FILL: e.g., Map appears instantly; no Nominatim calls in logs] |
| [FILL: add rows] | | | |

---

## 5. Edge Cases

| Case | Description | Expected Behaviour |
|---|---|---|
| Empty DB | `telco_tickets` table has 0 rows | [FILL: e.g., Widget renders empty state message; no 500 error] |
| Null field | `location_details` is NULL for all tickets | [FILL: e.g., API returns `locations: []`; map shows "No location data found"] |
| External service timeout | Nominatim unreachable (e.g., offline) | [FILL: e.g., Endpoint returns partial results within 10 s; `pending_geocode > 0` in response] |
| Duplicate addresses | Multiple tickets share same `location_details` | [FILL: e.g., Single marker per address with aggregated counts] |
| [FILL: add more] | | |

---

## 6. Performance Benchmarks

| Endpoint / Component | Expected p50 | Expected p99 | Measurement Method |
|---|---|---|---|
| `GET /api/v1/[FILL: path]` (cached) | < 20 ms | < 50 ms | `curl -w "%{time_total}"` |
| `GET /api/v1/[FILL: path]` (cold, external call) | [FILL] | [FILL] | Observe backend logs |
| Widget render (React Query cache hit) | < 200 ms | < 500 ms | Browser DevTools Performance tab |
| [FILL: add rows] | | | |

---

## 7. Test Data

<!-- SQL seeds or mock JSON payloads needed to exercise the feature. -->

### Minimum seed for testing

```sql
-- [FILL: e.g., Insert 3 tickets with known location_details for map testing]
INSERT OR IGNORE INTO telco_tickets (id, location_details, status, fault_type, network_type)
VALUES
  ('[FILL: uuid]', '[FILL: address 1]', 'pending_review', 'node_down', '4G'),
  ('[FILL: uuid]', '[FILL: address 2]', 'resolved',       'signal_loss', '5G'),
  ('[FILL: uuid]', NULL,               'resolved',        'packet_loss', '3G');
```

### Mock API response (for frontend-only testing via Playwright or browser devtools override)

```json
{
  "[FILL: field]": [
    { "[FILL: key]": "[FILL: value]" }
  ]
}
```
