# System Integration Test Report — SLA Tracking Table & Dashboard Widget

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

## 1. Integration Scenarios Tested

1. Dashboard page load → React Query fetches `/api/v1/sla/summary` → SLAWidget renders KPI row + bar chart with compliance rate, breach count, avg resolution hours
2. SLAWidget React Query cache hit → second Dashboard page load within 5 minutes → zero `/sla/summary` calls in DevTools Network
3. `sla_targets` auto-created on cold start → `data/tickets.db` opened fresh with no `sla_targets` table → first `/sla/targets` call creates table and seeds 8 rows → widget renders correctly
4. SLA target update reflected in summary → `PUT /sla/targets/node_down {"target_hours":1}` → next `/sla/summary` call shows increased breach count for `node_down`
5. Backend offline → SLAWidget error state → widget shows "SLA data unavailable" message without crashing the page

---

## 2. Test Execution Results

| Scenario | Status | Evidence |
|---|---|---|
| 1. Dashboard load → SLAWidget renders | Pass | Browser screenshot: SLA widget visible below Ticket Location Map; KPI row shows 80.3% compliance, 232 breaches, 5.2h avg |
| 2. React Query cache hit | Pass | DevTools Network: single `/sla/summary` call on first load; no call on second load within 5 min |
| 3. sla_targets auto-seeded | Pass | Deleted table, restarted uvicorn, called `/sla/targets` → 8 rows returned; no manual SQL needed |
| 4. Target update reflected | Pass | PUT node_down to 1h → compliance rate dropped from 79% to 12% for node_down in next summary |
| 5. Backend offline error state | Pass | Stopped uvicorn; reloaded Dashboard; SLAWidget showed error message; rest of page unaffected |

---

## 3. Defects Found

No defects found during SIT.

---

## 4. Regression Check

| Feature | Release | Re-tested? | Result |
|---|---|---|---|
| KPI Stats Dashboard | R-1 | Yes | Pass — stats widget unaffected |
| Triage Queue | R-4 | Yes | Pass — pending tickets list loads correctly |
| Chat Assistant | R-6 | Yes | Pass — chat responses unaffected |
| Dispatch Dashboard | R-7 | Yes | Pass — dispatch stats unchanged |
| Network Topology Widget | R-11 | Yes | Pass — graph renders correctly |
| Hot Nodes Widget | R-12 | Yes | Pass — top-10 nodes leaderboard intact |
| Ticket Location Map | R-12 | Yes | Pass — map markers load correctly |

---

## 5. Environment Details

| Item | Value |
|---|---|
| OS | Windows 11 Enterprise |
| Browser | Chrome 124 |
| Node version | 20.11.0 |
| Python version | 3.12.3 |
| DB row count | 1 592 tickets, 1 177 resolved |
| Backend URL | `http://localhost:8000` |
| Frontend URL | `http://localhost:5173` |

---

## 6. Sign-off

| Field | Value |
|---|---|
| Tester | Testing Lead |
| Test date | 2026-04-14 |
| Defects outstanding | 0 |
| Recommendation | **Go** — all scenarios passed, no regressions, ready for deployment |
