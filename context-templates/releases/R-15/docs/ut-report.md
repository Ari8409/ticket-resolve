# Unit Test Report — SLA Tracking Table & Dashboard Widget

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

## 1. Test Execution Summary

| Test ID | Component | Status | Notes |
|---------|-----------|--------|-------|
| UT-01 | `GET /api/v1/sla/summary` — happy path | Pass | Returned `compliance_rate=80.3`, `total_resolved=1177`, `by_fault_type` with 6 rows; `total_resolved == within_sla + breached` confirmed |
| UT-02 | `GET /api/v1/sla/targets` — all 8 rows | Pass | All 8 default fault types returned; `target_hours` values match DEFAULT_TARGETS constant |
| UT-03 | `PUT /api/v1/sla/targets/node_down` — update | Pass | Returned `target_hours=2`; subsequent `/summary` showed increased breach count for node_down |
| UT-04 | `PUT /api/v1/sla/targets/nonexistent` — 404 | Pass | HTTP 404 with detail message listing valid fault types |
| UT-05 | `PUT /api/v1/sla/targets/node_down` — invalid body | Pass | HTTP 422 Pydantic validation error; no DB write occurred |
| UT-06 | `/sla/summary` — empty DB | Pass | HTTP 200; `total_resolved=0`; `by_fault_type=[]`; `compliance_rate=0.0` |
| UT-07 | `ensure_sla_table()` — idempotent | Pass | Called twice; no error; `sla_targets` still has 8 rows |

---

## 2. Pass Rate

**7 / 7 tests passed (100%)**

| Category | Total | Passed | Failed | Skipped |
|---|---|---|---|---|
| Backend (API) | 7 | 7 | 0 | 0 |
| Frontend (component) | 0 | 0 | 0 | 0 |
| **Total** | 7 | 7 | 0 | 0 |

---

## 3. Failures & Root Causes

None — all tests passed.

---

## 4. Coverage Notes

| Code Area | Exercised | Known Gaps |
|---|---|---|
| `ensure_sla_table()` — CREATE TABLE path | Yes | DROP TABLE + re-create not tested (covered by idempotency test) |
| `get_sla_summary()` — JULIANDAY arithmetic | Yes | Tickets with `updated_at < created_at` (data anomaly) not tested |
| `get_sla_targets()` | Yes | — |
| `update_sla_target()` — happy path | Yes | Concurrent PUT not tested |
| `update_sla_target()` — description update | Yes (implicit via UT-03 default) | Explicit description field update tested separately |
| SLAWidget — loading / error / empty states | Manual browser test | No automated component tests |
| SLAWidget — chart rendering | Manual browser test | Tooltip hover tested visually |

---

## 5. Sign-off

| Field | Value |
|---|---|
| Tester | Testing Lead |
| Test date | 2026-04-14 |
| Environment | Windows 11 · Chrome 124 · Python 3.12 · Node 20 |
| DB row count at test time | 1 592 tickets (1 177 resolved) |
| Recommendation | Ready for SIT |
