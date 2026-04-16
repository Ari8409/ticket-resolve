# Role: Solution Architect

## Overview

The Solution Architect owns the **Why** and the **What** of every release. They define the business context, validate that the requirements are complete and aligned to NOC operational goals, and sign off on the architectural approach before any code is written.

No build work may commence until the Solution Architect has approved both the Requirements gate and the HLD gate.

---

## Responsibilities

### Requirements Gate (Gate 1)

- Review the filled `requirements.md` for completeness and business alignment
- Confirm that:
  - The Business Objective maps clearly to a NOC operational need
  - Functional Requirements are testable and carry correct priority (`Must / Should / Could`)
  - Non-Functional Requirements (performance, security, accessibility) are specified
  - Out-of-Scope exclusions are explicit
  - All `[FILL]` placeholders have been replaced
- **Gate decision:** Approve to unblock the HLD phase, or return with required corrections

### HLD Gate (Gate 2)

- **Run the data quality pre-flight check before reviewing the HLD document:**
  ```bash
  python sdlc_workflow.py data-check R-xx
  ```
  This checks for bulk-load indicators, high NULL rates, and missing `sla_targets` coverage.
  Gate 2 approval is **blocked** until this check passes.

- Review the filled `hld.md` for architectural soundness
- Confirm that:
  - The architecture diagram covers all components and data flows
  - API contracts are correctly specified and consistent with the platform conventions (`app/api/v1/<feature>.py`)
  - External service integrations list rate limits, auth, and fallback strategies
  - Technology choices are justified (cost, licensing, complexity)
  - Security considerations are addressed (SQL injection, CORS, input validation)
  - **Source data is non-trivial:** any computation-heavy feature (elapsed time, SLA metrics, trend charts) is verified against real or representative data before the design is locked
- **Gate decision:** Approve to unblock the Build phase (LLD + TDD), or return with required changes

---

## Approval Authority

| Gate | Document(s) | Can Approve |
|---|---|---|
| Requirements | `requirements.md` | ✅ Yes |
| High-Level Design | `hld.md` | ✅ Yes |
| Build Complete | `lld.md`, `tdd.md` | ❌ No — Tech Lead only |
| Testing Complete | All test reports | ❌ No — Testing Lead only |
| Deployment | `deployment.md` | ❌ No — Tech Lead only |

---

## How to Approve a Gate

```bash
cd ticket-resolve/context-templates

# Approve Requirements gate
python sdlc_workflow.py approve R-15 requirements \
  --role "Solution Architect" --name "Your Name"

# Approve HLD gate
python sdlc_workflow.py approve R-15 hld \
  --role "Solution Architect" --name "Your Name"
```

---

## Review Checklist

Use this checklist during gate reviews. All items must be satisfied before approving.

### Requirements Review Checklist

- [ ] Business Objective is ≤ 3 sentences and linked to a measurable NOC outcome
- [ ] Every FR has an ID (`FR-01`, `FR-02`, …) and a priority
- [ ] NFRs cover at minimum: Performance, Security, Accessibility
- [ ] Acceptance Criteria are independently verifiable and map to FR IDs
- [ ] No `[FILL]` placeholders remain in the document
- [ ] RICEF ID follows the `R-<number>` convention and is not already used
- [ ] Dependencies on prior RICEF objects are listed
- [ ] Validator passes: `python validate_prompt.py requirements.md`

### HLD Review Checklist

- [ ] **Data pre-flight check PASSED** — `python sdlc_workflow.py data-check R-xx` exits 0
  - [ ] No `TIMESTAMP-PAIR` ERROR (i.e., `created_at == updated_at` < 95% of rows)
  - [ ] No `NULL-RATE` ERROR on computation columns (< 80% NULL/empty)
  - [ ] No `ROW-COUNT` ERROR (table has ≥ 10 rows)
  - [ ] All warnings acknowledged in HLD Section 4 (Data Store Design) if any exist
- [ ] Architecture diagram includes: UI component → React Query → FastAPI → DB → (external service)
- [ ] All new API endpoints are listed with method, path, and response shape
- [ ] New/modified DB tables are described (even briefly — full DDL goes in LLD)
- [ ] If any feature computes **elapsed time** (SLA hours, resolution time, trend charts):
  - [ ] Confirmed that `created_at` ≠ `updated_at` for representative rows
  - [ ] JULIANDAY computation validated against a sample row in the live DB
- [ ] External service integrations specify rate limit and fallback
- [ ] No new runtime dependencies without justification
- [ ] Security section addresses SQL injection, CORS, and input validation
- [ ] Technology decisions explain *why*, not just *what*
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py hld.md`

---

## Escalation

If the Solution Architect is unavailable, a nominated delegate with equivalent authority may approve. The `--name` parameter in the approval command should reflect the actual approver's name, not the SA role.
