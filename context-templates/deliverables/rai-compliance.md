# Responsible AI Compliance Report — [FILL: Feature/Release Name]

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
- AI components: LangChain 0.3 · Claude claude-sonnet-4-6 (or local model) · ChromaDB `sop_documents` collection
- Repository path: `ticket-resolve/`

---

## 1. AI Component Inventory

<!-- List every AI/ML component involved in this release. -->

| Component | Model / Library | Purpose | Data Accessed |
|---|---|---|---|
| [FILL: e.g., Triage Agent] | LangChain 0.3 + Claude claude-sonnet-4-6 | [FILL: e.g., Classifies ticket fault type and recommends SOP] | [FILL: e.g., Ticket description text, SOP vector embeddings] |
| [FILL: e.g., Chat Assistant] | LangChain 0.3 + Claude claude-sonnet-4-6 | [FILL: e.g., Answers NOC operator queries about tickets] | [FILL: e.g., Ticket metadata, SOP documents] |
| [FILL: "None" if this release adds no AI components] | | | |

---

## 2. Data Privacy Assessment

| Question | Assessment |
|---|---|
| What ticket data is sent to the AI model? | [FILL: e.g., Ticket description text and fault type — no operator PII] |
| Does the data contain Personally Identifiable Information (PII)? | [FILL: Yes / No / Partial — explain] |
| Is data anonymised before sending to the model? | [FILL: Yes (describe method) / No (justify)] |
| Is data stored by the AI provider? | [FILL: e.g., No — Claude API processes in-flight only; no training on customer data per Anthropic policy] |
| Data residency requirements met? | [FILL: Yes / No / N/A] |

---

## 3. Bias & Fairness

| Question | Assessment |
|---|---|
| Could the model systematically favour certain fault types, network types, or locations? | [FILL: e.g., Risk low — model uses SOP documents as retrieval context; recommendations grounded in predefined procedures] |
| Is the training/retrieval corpus representative of all ticket categories? | [FILL: e.g., SOPs cover all 6 fault types equally — checked against SOP document count per category] |
| Mitigation in place? | [FILL: e.g., Human review required before dispatch action; confidence score displayed to operator] |

---

## 4. Explainability

| Question | Assessment |
|---|---|
| Does the UI surface the AI's reasoning? | [FILL: e.g., Yes — `reasons` array from triage agent is displayed as a bulleted list in the Triage Queue panel] |
| Is the confidence score shown to the operator? | [FILL: e.g., Yes — `confidence_score` shown as a percentage badge per ticket] |
| Can an operator trace a recommendation to a specific SOP? | [FILL: e.g., Yes — `sop_candidates_found` count shown; SOP name linkable in future release] |
| [FILL: if this release adds no explainability UI] | State: "Not applicable — this release does not introduce AI-generated recommendations" |

---

## 5. Human Oversight

| Checkpoint | Implemented |
|---|---|
| AI triage recommendation requires human review before dispatch | [FILL: Yes — tickets remain in `pending_review` status until operator approves] |
| Operator can override or reject AI recommendation | [FILL: Yes / No — describe] |
| Escalation path when AI confidence is low | [FILL: e.g., Tickets with `confidence_score < 0.6` are flagged with amber badge for manual review] |
| Audit log of human decisions after AI recommendation | [FILL: Yes (describe) / No (justify)] |

---

## 6. Failure Modes

| Failure | Behaviour | Degraded Mode |
|---|---|---|
| Claude API unavailable | [FILL: e.g., LangChain raises `httpx.ConnectError`] | [FILL: e.g., Triage endpoint returns `confidence_score: 0`, `reasons: ["AI service unavailable"]`; ticket routed to manual queue] |
| ChromaDB unavailable | [FILL: e.g., Vector search fails] | [FILL: e.g., Agent falls back to keyword-only SOP matching] |
| AI returns empty/malformed response | [FILL: e.g., Pydantic validation error] | [FILL: e.g., Endpoint returns 200 with default empty triage summary; no crash] |
| [FILL: add rows] | | |

---

## 7. Audit Trail

| Item | Implemented | Location |
|---|---|---|
| AI triage decisions logged | [FILL: Yes / No] | [FILL: e.g., `dispatch_records` table — `ai_recommendation` column] |
| Operator override/approval logged | [FILL: Yes / No] | [FILL: e.g., `dispatch_records.approved_by` + `approved_at`] |
| Log retention period | [FILL: e.g., Indefinite — SQLite DB retained] | `data/tickets.db` |
| [FILL: add rows] | | |

---

## 8. Responsible AI Checklist

| Principle | Status | Notes |
|---|---|---|
| Transparency — AI nature disclosed to users | [FILL: Yes / No / N/A] | [FILL: e.g., "AI Triage" label visible in UI] |
| Fairness — no systematic bias identified | [FILL: Yes / No / Partial] | [FILL: see section 3] |
| Accountability — human decision point before action | [FILL: Yes / No] | [FILL: see section 5] |
| Privacy — no unnecessary PII processed | [FILL: Yes / No / Partial] | [FILL: see section 2] |
| Safety — failure modes handled gracefully | [FILL: Yes / No] | [FILL: see section 6] |
| Reliability — AI output validated before display | [FILL: Yes / No] | [FILL: e.g., Pydantic model validates AI response shape] |
