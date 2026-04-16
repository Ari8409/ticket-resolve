# Test Design Document — SLA Tracking Table & Dashboard Widget

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

## 1. Test Scope

| In Scope | Out of Scope |
|---|---|
| `GET /api/v1/sla/summary` happy path and edge cases | Automated pytest / Jest framework |
| `GET /api/v1/sla/targets` returns all 8 seed rows | Load testing |
| `PUT /api/v1/sla/targets/{fault_type}` updates correctly | Cross-browser testing (Chrome only) |
| SLA breach arithmetic (JULIANDAY) is correct | SLA alerting / notification (future release) |
| SLAWidget renders all 3 states (loading, error, data) | Mobile layout |
| React Query cache hit on second Dashboard load | |

**Approach:** Manual smoke tests via curl + browser DevTools. No automated test framework configured.

---

## 2. Test Environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Backend command | `uvicorn app.main:app --reload --port 8000` |
| Frontend command | `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173` |
| DB | `data/tickets.db` — ~1 600 tickets, mix of resolved/pending_review |
| Browser | Chrome (latest) |

---

## 3. Unit-Level Test Cases

| ID | Component Under Test | Input | Expected Output |
|---|---|---|---|
| UT-01 | `GET /api/v1/sla/summary` | No params, populated DB | HTTP 200; `compliance_rate` between 0 and 100; `by_fault_type` non-empty; `total_resolved = within_sla + breached` |
| UT-02 | `GET /api/v1/sla/targets` | No params | HTTP 200; `targets` has 8 rows; each has `fault_type`, `target_hours`, `description`, `updated_at` |
| UT-03 | `PUT /api/v1/sla/targets/node_down` | `{"target_hours": 2}` | HTTP 200; returned `target_hours == 2`; subsequent `/summary` reflects new threshold |
| UT-04 | `PUT /api/v1/sla/targets/nonexistent` | `{"target_hours": 5}` | HTTP 404; `detail` message mentions the invalid fault_type |
| UT-05 | `PUT /api/v1/sla/targets/node_down` | `{"target_hours": "fast"}` | HTTP 422; Pydantic validation error |
| UT-06 | `GET /api/v1/sla/summary` | DB with 0 resolved tickets | HTTP 200; `total_resolved == 0`; `by_fault_type == []`; `compliance_rate == 0.0` |
| UT-07 | `ensure_sla_table()` called twice | — | No error; idempotent; still 8 rows in `sla_targets` |

---

## 4. Integration Test Cases

| ID | Flow | Steps | Expected Result |
|---|---|---|---|
| IT-01 | Dashboard load renders SLAWidget | 1. Open `http://localhost:5173` 2. Scroll to SLA section | SLA widget visible with KPI row (compliance %, breach count, avg hours) and horizontal bar chart with fault-type rows |
| IT-02 | React Query cache hit | 1. Load Dashboard 2. Open DevTools Network 3. Reload page | Single `/sla/summary` call on first load; zero calls on subsequent renders within 5 min |
| IT-03 | sla_targets auto-created on cold start | 1. Delete `sla_targets` table from DB 2. Restart backend 3. Call `/sla/targets` | 8 rows returned; no manual SQL run needed |
| IT-04 | Updated target reflected in summary | 1. `PUT /sla/targets/node_down {"target_hours": 1}` 2. `GET /sla/summary` | `node_down` compliance rate changes; more tickets likely breached with 1h target |

---

## 5. Edge Cases

| Case | Description | Expected Behaviour |
|---|---|---|
| All tickets pending | No tickets with status `resolved` or `closed` | `/sla/summary` returns `total_resolved=0`, `by_fault_type=[]`, widget shows empty state |
| Null `updated_at` | Some resolved tickets have `updated_at = NULL` | Those tickets excluded from computation (WHERE clause filters them) |
| Null `fault_type` | Tickets with no fault type | Excluded by `WHERE fault_type IS NOT NULL AND fault_type != ''` |
| Resolution < 1 min | `updated_at` very close to `created_at` | Elapsed hours rounds to 0.00; within SLA; no crash |
| Fault type not in sla_targets | e.g., a ticket has `fault_type = 'custom_fault'` | LEFT JOIN returns NULL target_hours; COALESCE defaults to 24h target |

---

## 6. Performance Benchmarks

| Endpoint | Expected p50 | Expected p99 | Method |
|---|---|---|---|
| `GET /sla/summary` | < 30 ms | < 100 ms | `curl -w "%{time_total}" http://localhost:8000/api/v1/sla/summary` |
| `GET /sla/targets` | < 10 ms | < 30 ms | `curl -w "%{time_total}" http://localhost:8000/api/v1/sla/targets` |
| SLAWidget render | < 200 ms | < 400 ms | Browser DevTools Performance tab |

---

## 7. Test Data

### Verify breach arithmetic manually

```sql
-- Insert one ticket that SHOULD be within SLA (resolved in 3h, node_down target=4h)
INSERT OR IGNORE INTO telco_tickets (
    ticket_id, fault_type, status, created_at, updated_at,
    description, severity, network_type
) VALUES (
    'test-within-sla', 'node_down', 'resolved',
    datetime('now', '-3 hours'), datetime('now'),
    'Test ticket within SLA', 'major', '4G'
);

-- Insert one ticket that SHOULD be breached (resolved in 6h, node_down target=4h)
INSERT OR IGNORE INTO telco_tickets (
    ticket_id, fault_type, status, created_at, updated_at,
    description, severity, network_type
) VALUES (
    'test-breached-sla', 'node_down', 'resolved',
    datetime('now', '-6 hours'), datetime('now'),
    'Test ticket breached SLA', 'major', '4G'
);
```

After insert, verify `/sla/summary` shows `within_sla` includes `test-within-sla`
and `breached` includes `test-breached-sla` in the `node_down` row.
