# Lessons Learned — [FILL: Feature/Release Name]

## Document Metadata

| Field | Value |
|---|---|
| Release | [FILL: e.g., Release 15 — SLA Tracking] |
| RICEF ID | [FILL: R-xx] |
| Author | NOC Platform Team |
| Date | [FILL: YYYY-MM-DD] |
| Version | [FILL: e.g., 1.0] |
| Status | [FILL: Draft / Final] |

## Platform Reference [PRE-FILLED]

- Backend: FastAPI 0.115 · Python 3.12 · SQLite (`data/tickets.db`) · LangChain 0.3 · ChromaDB
- Frontend: React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5
- Repository path: `ticket-resolve/`

---

## Lessons Learned

<!--
  Add one row per significant defect, near-miss, or process gap encountered during this release.
  Severity: High = caused incorrect behaviour or data; Medium = caused confusion/rework; Low = minor
  Area: e.g., 'FastAPI / Architecture', 'DB / Data Quality', 'Testing', 'Frontend', 'Process'
  Each row here MUST also have a corresponding entry in the LESSONS_LEARNED array in
  frontend/src/pages/SDLCDashboard.tsx with  iteration: '[FILL: R-xx]'
-->

| Severity | Area | Title | Problem | Fix Applied |
|---|---|---|---|---|
| [FILL: High / Medium / Low] | [FILL: e.g., FastAPI / Architecture] | [FILL: R-xx: Short title] | [FILL: What went wrong and why it wasn't caught earlier] | [FILL: What was changed + what guardrail now prevents recurrence] |
| [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |

---

## Root Cause

<!--
  For each High severity issue above, provide a deeper root cause analysis.
  Answer: What was the primary cause? What process or knowledge gap allowed it?
-->

### Issue 1: [FILL: Title from table above]

**Root cause:** [FILL: e.g., FastAPI's APIRouter does not propagate @on_event hooks to the main
app — startup logic placed on a sub-router silently never runs.]

**Why it wasn't caught at design:** [FILL: e.g., The HLD review checked document structure
but did not include a static scan for this anti-pattern.]

**Why it wasn't caught at build:** [FILL: e.g., Manual testing confirmed the endpoint responded
correctly once data was seeded, but no test verified the table creation path from a cold start.]

### Issue 2: [FILL: Title or "N/A — no additional High severity issues"]

**Root cause:** [FILL]

**Why it wasn't caught at design:** [FILL]

**Why it wasn't caught at build:** [FILL]

---

## Fix Applied

<!--
  Describe exactly what code/config/process changes were made to resolve each issue.
  Reference specific files and line numbers where relevant.
-->

### Fix for Issue 1

- **File changed:** `[FILL: e.g., app/main.py]`
- **Change:** [FILL: e.g., Moved `await ensure_sla_table()` from `app/api/v1/sla.py` router
  startup hook into the `lifespan` context manager in `app/main.py`.]
- **Verified by:** [FILL: e.g., Cold-start test — deleted `data/tickets.db`, restarted uvicorn,
  confirmed table created in startup log, then `curl /api/v1/sla/summary` returned 200.]

### Fix for Issue 2

- **File changed:** [FILL]
- **Change:** [FILL]
- **Verified by:** [FILL]

---

## Recurrence Prevention

<!--
  List the guardrails, checklist items, or process changes introduced as a result of this release
  to prevent the same class of defect recurring in future releases.
-->

| Guardrail / Change | Gate Enforced At | Tool / Document |
|---|---|---|
| [FILL: e.g., `code_scan.py` PY-001 rule — blocks Build gate if `@router.on_event` found on APIRouter] | Gate 3 (Build) | `context-templates/code_scan.py` |
| [FILL: e.g., TDD Section 2a Data Pre-Flight — timestamp variance check before HLD approval] | Gate 2 (HLD) | `context-templates/data_quality_check.py` |
| [FILL: e.g., UT report must include pasted `curl` output — not "Pass assumed"] | Gate 4 (Testing) | `roles/testing-lead.md` checklist |
| [FILL: add more] | | |

---

## SDLCDashboard.tsx Checklist

Before submitting this document, confirm the dashboard has been updated:

- [ ] LESSONS_LEARNED array in `frontend/src/pages/SDLCDashboard.tsx` contains at least one entry
      with `iteration: '[FILL: R-xx]'`
- [ ] Each entry has: `severity`, `area`, `title`, `problem`, `fix`, `iteration` fields
- [ ] `python sdlc_workflow.py lessons-check [FILL: R-xx]` exits 0 (ALL CLEAR)

