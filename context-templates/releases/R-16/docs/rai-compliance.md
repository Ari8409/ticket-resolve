# Responsible AI Compliance Report — NOC Dashboard Web Server

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
- AI components: LangChain 0.3 · Claude claude-sonnet-4-6 (or local model) · ChromaDB `sop_documents` collection
- Repository path: `ticket-resolve/`

---

## 1. AI Component Inventory

R-16 is a web-serving infrastructure release with no AI model changes. No new AI or ML components are introduced. Existing RAI guardrails from R-9 (Chat Assistant / LangChain RAG) remain in force and are unmodified.

| Component | Model / Library | Purpose | Data Accessed | Changed in R-16? |
|---|---|---|---|---|
| Chat Assistant (R-9) | LangChain 0.3 · Claude claude-sonnet-4-6 · ChromaDB | RAG-based fault resolution assistant | `sop_documents` ChromaDB collection | No |
| None (new) | — | R-16 adds only web-serving infrastructure | — | N/A |

---

## 2. Data Privacy Assessment

| Question | Assessment |
|---|---|
| What data does R-16 handle? | Static frontend assets (`frontend/dist/`) and existing API responses — no new data types |
| Does R-16 process PII? | No — R-16 adds no new data processing; serves pre-built HTML/JS/CSS files |
| Is data sent to an AI model? | No — R-16 changes are infrastructure only; LangChain chat pipeline is unchanged |
| Data residency requirements met? | Yes — no new data flows introduced; all existing data remains on-premise |
| CORS change impact? | Origins restricted to `http://localhost:8003` — reduces exposure vs prior wildcard configuration |

---

## 3. Bias & Fairness

Not applicable for R-16. This release introduces no AI model changes, training data updates, or inference logic. The LangChain RAG pipeline established in R-9 is unmodified.

---

## 4. Explainability

Not applicable for R-16. No new model inference is added. The release consists entirely of:
- FastAPI `StaticFiles` mount
- SPA catch-all route handlers
- `startup.sh` build script
- Dockerfile updates

All behaviours are deterministic and fully observable via HTTP response codes and server logs.

---

## 4. Human Oversight

R-16 introduces no automated decision-making or AI-driven actions. The change is infrastructure — serving the existing React SPA through FastAPI. NOC operators retain full control over all platform interactions. The existing Chat Assistant human-oversight model (R-9) is unchanged: responses are informational and operators make all dispatch and escalation decisions.

---

## 5. Responsible AI Checklist

| Principle | Status | Notes |
|---|---|---|
| Transparency | N/A | No AI model used in R-16; all behaviour is deterministic web serving |
| Fairness | N/A | Infrastructure release; no model inference or data-driven decisions |
| Accountability | N/A | Human operator retains full decision authority; R-16 adds no automation |
| Privacy | Yes | No new data flows; CORS tightened; no PII processed by new code |
| Safety | Yes | Failure degrades to `_FALLBACK_HTML` page; no automated actions triggered |
| Reliability | Yes | Deterministic static file serving; no model inference involved |
