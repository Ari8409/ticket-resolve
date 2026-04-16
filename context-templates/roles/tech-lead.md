# Role: Tech Lead

## Overview

The Tech Lead owns the **How** of every release. They are responsible for the technical quality of the implementation, the accuracy of the Low-Level Design after build, and the readiness of the deployment runbook. They hold gate approval authority over Build Complete (Gate 3) and Deployment (Gate 5).

No build is considered complete until the Tech Lead has verified that the LLD and TDD reflect what was actually built — not just what was planned.

---

## Responsibilities

### Build Gate (Gate 3)

The LLD and TDD are **living documents** that must be updated to reflect the actual implementation before this gate can be submitted.

**Before reviewing documents, run the static code scanner:**
```bash
python sdlc_workflow.py scan R-xx app/api/v1/<feature>.py frontend/src/components/<Widget>.tsx
```
Gate 3 approval is **blocked** until the scan exits 0 (all clear or warnings-only — no ERRORs).

Key rules checked by `code_scan.py` that are mandatory for this platform:

| Rule | What it catches |
|---|---|
| PY-001 | `@router.on_event()` on `APIRouter` — silently does nothing; use `app/main.py` lifespan |
| PY-002 | SQL f-string injection risk |
| PY-003 | SQL string concatenation injection risk |
| PY-004 | `ensure_*_table()` called per-request instead of at startup |
| PY-005 | `await` missing on async DB calls |
| PY-006 | New router file not registered in `app/api/v1/router.py` |
| PY-007 | `ensure_*_table()` defined but not wired into `app/main.py` lifespan |
| TS-001 | `[FILL]` placeholder left in TypeScript source |
| TS-002 | `queryKey` as string instead of array |
| TS-004 | Hardcoded absolute URL instead of `apiClient` |

**Execution proof required before approval.** The LLD and TDD documents alone are not sufficient.
Paste the following into the approval conversation or attach as a comment in `lld.md`:

1. **Backend startup log** — paste the first 10 lines of the uvicorn startup output showing `Application startup complete` and no `ERROR` lines
2. **API smoke test output** — paste actual `curl` output for each new endpoint (not expected output — run the command)
3. **Code scan output** — paste the full output of `python sdlc_workflow.py scan R-xx <files>`

- Review `lld.md` — confirm it matches the code that was written:
  - Module breakdown matches actual file/function names
  - DB schema DDL matches what is in `data/tickets.db`
  - Pydantic models match what is in the FastAPI router files
  - React component tree matches the actual component hierarchy
  - React Query keys match the actual `queryKey` values in the code
- Review `tdd.md` — confirm test design covers the built code:
  - Test environment instructions are accurate
  - Unit test cases cover all key code paths
  - Integration test cases cover all new API endpoints
  - Edge cases include null/empty DB, external service timeout
- **Gate decision:** Approve once LLD + TDD accurately describe the built system AND scan passes AND execution proof is provided

### Deployment Gate (Gate 5)

**Before reviewing documents, run the lessons-learned check:**
```bash
python sdlc_workflow.py lessons-check R-xx
```
Gate 5 approval is **blocked** until `lessons-check` exits 0. This ensures every release documents what went wrong and what guardrail was added to prevent recurrence.

- Review `deployment.md` — confirm the deployment runbook is accurate:
  - All `pip install` / `npm install` steps are included
  - DB schema changes are documented (lazy `CREATE TABLE IF NOT EXISTS` noted)
  - New environment variables are listed with their defaults
  - Smoke test commands are correct and return expected output
  - Rollback procedure is described
- Review `lessons-learned.md` — confirm the post-mortem is complete:
  - At least one entry per significant defect encountered during the release
  - Root cause section goes beyond "we missed it" — identifies the process gap
  - Fix Applied section references specific files and includes cold-start verification
  - Recurrence Prevention table lists the guardrail or checklist update introduced
  - Corresponding `LESSONS_LEARNED` entries exist in `SDLCDashboard.tsx` with correct `iteration` field
- **Gate decision:** Approve once the deployment document could be followed by someone who did not write the code AND lessons-learned is complete with no `[FILL]` placeholders

---

## Approval Authority

| Gate | Document(s) | Can Approve |
|---|---|---|
| Requirements | `requirements.md` | ❌ No — Solution Architect only |
| High-Level Design | `hld.md` | ❌ No — Solution Architect only |
| Build Complete | `lld.md`, `tdd.md` | ✅ Yes |
| Testing Complete | All test reports | ❌ No — Testing Lead only |
| Deployment | `deployment.md`, `lessons-learned.md` | ✅ Yes |

---

## How to Approve a Gate

```bash
cd ticket-resolve/context-templates

# Approve Build gate (after LLD + TDD are both submitted and valid)
python sdlc_workflow.py approve R-15 build \
  --role "Tech Lead" --name "Your Name"

# Run lessons-learned check before Deployment gate (mandatory)
python sdlc_workflow.py lessons-check R-15

# Approve Deployment gate (only after lessons-check passes)
python sdlc_workflow.py approve R-15 deployment \
  --role "Tech Lead" --name "Your Name"
```

---

## Review Checklist

### Build (LLD + TDD) Review Checklist

**Code scan (mandatory — Gate 3 will not approve without this):**
- [ ] `python sdlc_workflow.py scan R-xx <all changed .py and .tsx files>` exits 0
- [ ] No PY-001 violations (no `@router.on_event` on APIRouter instances)
- [ ] No PY-007 violations (`ensure_*_table()` correctly wired in `app/main.py` lifespan)
- [ ] No PY-002 / PY-003 violations (no SQL injection risk)
- [ ] No PY-006 violations (router registered in `router.py`)
- [ ] No TS-001 violations (no `[FILL]` placeholders in TypeScript)
- [ ] No TS-004 violations (no hardcoded absolute URLs)

**Execution proof (required before approval):**
- [ ] Uvicorn startup log pasted — shows `Application startup complete`, zero ERROR lines
- [ ] `curl` output for each new endpoint pasted — actual response, not expected
- [ ] Data confirmed as non-trivial: verified spot-check of `created_at` ≠ `updated_at` for resolved tickets (run `SELECT created_at, updated_at FROM telco_tickets WHERE status='resolved' LIMIT 5`)

**LLD checks:**
- [ ] Every new file is listed in the Module Breakdown with correct file path
- [ ] Function signatures match the implementation (not the plan)
- [ ] DB DDL is identical to the `CREATE TABLE IF NOT EXISTS` statement in the code
- [ ] Pydantic model fields match the FastAPI router file
- [ ] React Query `queryKey` values match what is in the component source
- [ ] Error Handling Matrix covers at least: DB unavailable, empty result, external timeout
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py lld.md`

**TDD checks:**
- [ ] Test environment section gives exact `uvicorn` and Vite commands
- [ ] Unit test cases reference real function names and file paths
- [ ] Integration test cases include actual `curl` commands with expected response fields
- [ ] Edge cases include: null `location_details`, zero rows in DB, external service timeout
- [ ] **Data Pre-Flight section is complete** — `created_at` / `updated_at` variance verified, NULL rates for computation columns documented
- [ ] Test data SQL seeds are correct and runnable
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py tdd.md`

### Deployment Review Checklist

**Lessons-learned check (mandatory — Gate 5 will not approve without this):**
- [ ] `python sdlc_workflow.py lessons-check R-xx` exits 0
- [ ] `SDLCDashboard.tsx` has at least one `LESSONS_LEARNED` entry with `iteration: 'R-xx'`
- [ ] Each entry covers a real defect or process gap from the release (not a placeholder)

**`lessons-learned.md` content checks:**
- [ ] Every High/Medium severity issue has a row in the Lessons Learned table
- [ ] Root Cause section identifies the *process gap*, not just the symptom
- [ ] Fix Applied section references specific files — not "code was updated"
- [ ] Cold-start or equivalent verification is described for each fix
- [ ] Recurrence Prevention table lists the guardrail / checklist change introduced
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py lessons-learned.md`

**`deployment.md` content checks:**
- [ ] Pre-deployment checklist covers all new Python and npm dependencies
- [ ] Deployment steps are in correct execution order with no gaps
- [ ] New environment variables are listed with example values
- [ ] DB changes section lists all tables created/modified
- [ ] Rollback procedure is practical (not just "git revert")
- [ ] Smoke test commands include the new endpoint(s)
- [ ] Monitoring points list what to watch in uvicorn logs and browser console
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py deployment.md`

---

## Code Quality Standards

Before approving the Build gate, verify the implementation meets platform conventions.
**The `code_scan.py` rules enforce a subset of these automatically** — the table below marks which are scanner-enforced vs manual review.

| Standard | Expectation | Enforced by |
|---|---|---|
| API router location | `app/api/v1/<feature>.py` registered in `app/api/v1/router.py` | PY-006 (auto) |
| Startup hooks | `ensure_*_table()` in `app/main.py` lifespan — never `@router.on_event` | PY-001, PY-007 (auto) |
| DB access | `aiosqlite` + parameterised SQL — no string interpolation or f-strings | PY-002, PY-003 (auto) |
| Async DB calls | All `db.execute()` / `cursor.fetchone()` calls must use `await` | PY-005 (auto) |
| Response models | Pydantic v2 `BaseModel` — all fields typed | Manual |
| React Query key | `queryKey` must be an array `['key']` not a string | TS-002 (auto) |
| React Query staleTime | `staleTime: 5 * 60_000` on all `useQuery` calls | Manual |
| API client | All fetch calls use `apiClient` from `frontend/src/api/client.ts` | TS-004 (auto) |
| Tailwind classes | Follows slate-800/700/600 palette; no hardcoded hex in JSX | Manual |
| Path ordering | Literal paths declared before `/{id}` param routes in same router | Manual |
| Error states | Loading skeleton, error message, and empty state in every widget | Manual |
| Console logging | No `console.log` in production TypeScript | TS-003 (auto, warning) |

---

## Escalation

If the Tech Lead is unavailable for the Build gate, a senior developer with full knowledge of the implementation may approve. Their name must be recorded in `--name`.
