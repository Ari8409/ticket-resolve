# Requirements Document — SLA Tracking Table & Dashboard Widget

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

## 1. Business Objective

NOC management currently has no visibility into whether faults are being resolved within contractual SLA windows. Missed SLAs lead to penalties, undetected patterns of underperformance, and reactive rather than proactive escalation. This release introduces a persistent `sla_targets` configuration table and a live SLA compliance dashboard widget so operators and managers can instantly see breach rates, average resolution times, and which fault categories are consistently missing their targets.

---

## 2. Stakeholders

| Role               | Name / Team       | Interest                                              |
|--------------------|-------------------|-------------------------------------------------------|
| NOC Operations Manager | Operations    | SLA breach visibility for reporting and escalation    |
| NOC Engineer       | Field Operations  | Know which tickets are approaching SLA deadline       |
| Platform Developer | NOC Platform Team | Implementation                                        |

---

## 3. Functional Requirements

| ID    | Description                                                                                   | Priority |
|-------|-----------------------------------------------------------------------------------------------|---------|
| FR-01 | System shall maintain a `sla_targets` table with configurable target resolution hours per fault type | Must |
| FR-02 | `sla_targets` shall be pre-seeded with defaults for all 8 known fault types on first startup  | Must    |
| FR-03 | A `GET /api/v1/sla/summary` endpoint shall return overall compliance rate and per-fault-type breakdown | Must |
| FR-04 | SLA breach is defined as: resolved ticket where `(updated_at − created_at)` exceeds `target_hours` | Must |
| FR-05 | A `GET /api/v1/sla/targets` endpoint shall return all configured SLA targets                  | Must    |
| FR-06 | The Dashboard shall display an SLA Compliance widget with compliance rate, breach count, and per-fault bar | Must |
| FR-07 | A `PUT /api/v1/sla/targets/{fault_type}` endpoint shall allow updating a target hours value   | Should  |

---

## 4. Non-Functional Requirements

| Category      | Requirement                                                                     |
|---------------|---------------------------------------------------------------------------------|
| Performance   | `/sla/summary` responds within 200 ms against current DB (~1 600 tickets)       |
| Reliability   | Widget degrades gracefully (shows "SLA data unavailable") if endpoint fails     |
| Security      | All queries use parameterised SQL — no string interpolation                     |
| Accessibility | WCAG 2.1 AA — widget keyboard-navigable, colour contrast ≥ 4.5:1               |
| Scalability   | Join query uses indexed `fault_type` and `status` columns — scales to 50k rows  |

---

## 5. Assumptions & Constraints

- `updated_at` on `telco_tickets` represents the resolution timestamp for `resolved` / `closed` tickets
- SQLite `JULIANDAY()` function is available for date arithmetic
- No dedicated `resolved_at` column exists; adding one is out of scope for this release
- SLA targets are configurable but static during a session (no real-time change expected)

---

## 6. Out of Scope

- Email/SMS alerts when a ticket is approaching SLA deadline (future release)
- Per-customer or per-contract SLA tiers (single company-wide target per fault type)
- Historical SLA target changes / versioning
- SLA calculation for `pending_review` or `in_progress` tickets (resolved/closed only)

---

## 7. Acceptance Criteria

| AC ID | Maps to | Criterion                                                                                          |
|-------|---------|----------------------------------------------------------------------------------------------------|
| AC-01 | FR-01   | `sla_targets` table exists in `data/tickets.db` after first backend startup — no manual SQL needed |
| AC-02 | FR-02   | All 8 fault types have a default target row on first run                                           |
| AC-03 | FR-03   | `GET /api/v1/sla/summary` returns HTTP 200 with `compliance_rate`, `breached`, `by_fault_type`     |
| AC-04 | FR-04   | A ticket resolved in 5 h against a 4 h target is counted as breached                              |
| AC-05 | FR-06   | SLA widget visible on Dashboard with compliance percentage and fault-type bar chart                |
| AC-06 | FR-07   | `PUT /api/v1/sla/targets/node_down` with `{"target_hours": 3}` updates the row and is reflected in next summary call |

---

## 8. Dependencies

| Dependency                  | Type       | Notes                                            |
|-----------------------------|------------|--------------------------------------------------|
| R-2 — FastAPI REST Layer     | Predecessor | Router pattern and `aiosqlite` DB access in place |
| R-1 — Core Dashboard         | Predecessor | `DashboardPage.tsx` widget container in place     |
| `telco_tickets.updated_at`   | DB column  | Used as resolution timestamp — must be populated for resolved tickets |
