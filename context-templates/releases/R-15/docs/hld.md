# High-Level Design — SLA Tracking Table & Dashboard Widget

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

## 1. Architecture Overview

```
Browser
  └── DashboardPage.tsx
        └── SLAWidget.tsx
              └── useQuery(['sla-summary'], api.getSLASummary, staleTime=5min)
                    │
                    │ GET /api/v1/sla/summary
                    ▼
              FastAPI — app/api/v1/sla.py
                    │
                    ├── SELECT telco_tickets (status=resolved/closed)
                    │     JOIN sla_targets ON fault_type
                    │     JULIANDAY arithmetic → breach flag
                    │
                    └── SELECT sla_targets (seed on startup)
                          └── data/tickets.db
```

---

## 2. Component Inventory

| Component            | Layer    | File Path                                        | Responsibility                                    |
|----------------------|----------|--------------------------------------------------|---------------------------------------------------|
| sla_targets table    | Database | `data/tickets.db`                                | Stores configurable target hours per fault type   |
| sla.py router        | Backend  | `app/api/v1/sla.py`                              | Exposes /summary and /targets endpoints           |
| router.py            | Backend  | `app/api/v1/router.py`                           | Registers sla.router                              |
| SLAWidget            | Frontend | `frontend/src/components/SLAWidget.tsx`          | Displays compliance rate + per-fault bar chart    |
| client.ts            | Frontend | `frontend/src/api/client.ts`                     | SLASummaryResponse interface + getSLASummary()    |
| DashboardPage        | Frontend | `frontend/src/pages/DashboardPage.tsx`           | Imports and renders SLAWidget                     |

---

## 3. API Contract Summary

| Method | Path                              | Request Body                   | Response                  | Notes                         |
|--------|-----------------------------------|--------------------------------|---------------------------|-------------------------------|
| GET    | `/api/v1/sla/summary`             | —                              | `SLASummaryResponse`      | Computed from telco_tickets JOIN sla_targets |
| GET    | `/api/v1/sla/targets`             | —                              | `SLATargetsResponse`      | Returns all rows from sla_targets |
| PUT    | `/api/v1/sla/targets/{fault_type}`| `{"target_hours": int}`        | `SLATarget`               | Updates a single target row   |

---

## 4. Data Store Design

**New table: `sla_targets`**

| Column       | Type    | Constraints        | Notes                                |
|--------------|---------|--------------------|--------------------------------------|
| fault_type   | TEXT    | PRIMARY KEY        | Matches `telco_tickets.fault_type`   |
| target_hours | INTEGER | NOT NULL           | Maximum hours to resolve this fault  |
| description  | TEXT    | NOT NULL DEFAULT '' | Human-readable label                |
| created_at   | TEXT    | NOT NULL           | ISO-8601 timestamp                   |
| updated_at   | TEXT    | NOT NULL           | ISO-8601 timestamp                   |

**Default seed rows (INSERT OR IGNORE on startup):**

| fault_type          | target_hours | description                  |
|---------------------|--------------|------------------------------|
| node_down           | 4            | Complete node outage         |
| signal_loss         | 8            | Partial signal degradation   |
| latency             | 6            | Network latency spike        |
| packet_loss         | 6            | Packet loss event            |
| congestion          | 8            | Network congestion           |
| hardware_failure    | 12           | Physical hardware fault      |
| configuration_error | 6            | Config/firmware issue        |
| unknown             | 24           | Unclassified fault           |

**Computation (no new columns on telco_tickets):**

SLA elapsed hours = `(JULIANDAY(updated_at) − JULIANDAY(created_at)) × 24`
Breach = elapsed hours > `sla_targets.target_hours`
Only applies to tickets with `status IN ('resolved', 'closed')`

---

## 5. External Integrations

None. This feature is entirely self-contained within the platform.

---

## 6. Security Considerations

- All SQL queries use `aiosqlite` parameterised statements (`?` placeholders)
- `fault_type` path parameter on PUT validated against known values before DB write
- No user-supplied data reaches the computation query — only `fault_type` keys from the seed table

---

## 7. Technology Decisions

| Decision              | Choice                         | Rationale                                                                 |
|-----------------------|-------------------------------|---------------------------------------------------------------------------|
| Date arithmetic       | SQLite `JULIANDAY()`           | Native SQLite function; avoids parsing timestamps in Python for each row  |
| No new column on tickets | Reuse `updated_at`           | Avoids a schema migration on the primary 1600-row table; `updated_at` is set on resolve |
| Computation: query-time | JOIN + GROUP BY per request  | Data volume is small (~1600 rows); caching via React Query staleTime=5min |
| Chart type            | Recharts `BarChart`            | Already used by DashboardPage; zero new dependencies                      |
