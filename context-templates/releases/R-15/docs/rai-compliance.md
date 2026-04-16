# Responsible AI Compliance Report — SLA Tracking Table & Dashboard Widget

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
- AI components: LangChain 0.3 · Claude claude-sonnet-4-6 (or local model) · ChromaDB `sop_documents` collection
- Repository path: `ticket-resolve/`

---

## 1. AI Component Inventory

This release introduces no new AI or ML components.

| Component | Model / Library | Purpose | Data Accessed |
|---|---|---|---|
| None | — | SLA tracking is purely deterministic SQL computation | — |

The SLA breach determination uses `JULIANDAY()` arithmetic in SQLite — a rule-based calculation with no model inference.

---

## 2. Data Privacy Assessment

| Question | Assessment |
|---|---|
| What ticket data is used? | `fault_type`, `status`, `created_at`, `updated_at` — operational metadata only |
| Does the data contain PII? | No — no engineer names, customer identifiers, or contact details are used |
| Is data sent to an AI model? | No — SLA computation is local SQLite query only |
| Data residency requirements met? | Yes — all computation occurs on-premise within the NOC platform host |

---

## 3. Bias & Fairness

Not applicable. SLA targets are rule-based thresholds configured per fault type. The system applies the same threshold to all tickets of the same fault type regardless of node, region, or operator. No model inference is involved.

---

## 4. Explainability

SLA breach determination is fully transparent:
- Target hours are visible in `GET /sla/targets` and displayed as tooltip content in the widget
- Breach formula is documented: `elapsed_hours = (updated_at − created_at) × 24; is_breached = elapsed_hours > target_hours`
- No opaque model decisions are involved

---

## 5. Human Oversight

Not applicable for this release. SLA metrics are read-only KPIs displayed to NOC operators for awareness and escalation decisions. No automated action is taken on the basis of SLA breach status. Operators retain full discretion over how to respond to breach information.

The `PUT /sla/targets/{fault_type}` endpoint allows authorised engineers to adjust targets, providing human control over the thresholds.

---

## 6. Failure Modes

| Failure | Behaviour | Degraded Mode |
|---|---|---|
| Backend unavailable | `/sla/summary` unreachable | SLAWidget shows "SLA data unavailable" error state; rest of Dashboard unaffected |
| Null `updated_at` on resolved tickets | Tickets excluded by WHERE clause | Summary computed from valid tickets only; count may under-report |
| `sla_targets` table missing | `ensure_sla_table()` recreates it on next call | Transparent recovery; no data loss |

---

## 7. Audit Trail

| Item | Implemented | Location |
|---|---|---|
| SLA target changes logged | Via `updated_at` column on `sla_targets` | `data/tickets.db — sla_targets.updated_at` |
| AI decisions logged | Not applicable — no AI in this release | — |
| Retention period | Indefinite — SQLite DB retained | `data/tickets.db` |

---

## 8. Responsible AI Checklist

| Principle | Status | Notes |
|---|---|---|
| Transparency | N/A | No AI model used; SLA formula is deterministic and fully visible |
| Fairness | N/A | Rule-based; same threshold applied uniformly per fault type |
| Accountability | N/A | Human operator retains full decision authority; targets are configurable |
| Privacy | Yes | No PII processed; purely operational metadata |
| Safety | Yes | Failure degrades gracefully to error state; no automated actions triggered |
| Reliability | Yes | No model inference; computation is deterministic SQL arithmetic |
