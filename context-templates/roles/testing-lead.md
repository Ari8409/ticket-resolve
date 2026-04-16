# Role: Testing Lead

## Overview

The Testing Lead owns **quality assurance** for every release. They define the testing strategy, review all test evidence, and hold gate approval authority over the Testing Complete gate (Gate 4). No release may proceed to deployment until the Testing Lead has verified that unit testing, system integration testing, Responsible AI compliance, and accessibility standards have all been satisfied.

The Testing Lead approves the **plan before execution** (TDD — submitted at Build gate) and the **outcomes after execution** (UT report, SIT report, RAI compliance, Accessibility report — submitted at Testing gate). This ensures the test approach is sound before effort is spent.

---

## Responsibilities

### Testing Gate (Gate 4)

The Testing Lead reviews four mandatory deliverables. All must be submitted and valid before approval can be given:

#### 1. Unit Test Report (`ut-report.md`)
- Every test case from the TDD has a result (Pass / Fail / Skip) with notes
- **Actual command output is required** — the report must include pasted `curl` responses or function outputs for each UT case, not just "Pass (as expected)". Evidence that the test was actually executed must be visible.
- Pass rate is explicitly stated
- Any failures have documented root cause and confirmed fix
- Coverage gaps are acknowledged
- Sign-off section is complete with tester name and date

#### 2. SIT Report (`sit-report.md`)
- All integration scenarios from the TDD were executed
- Evidence provided for each scenario (screenshot reference, curl output, or log excerpt)
- Regression check confirms no previously working features were broken
- All open defects are either resolved or formally deferred with justification
- Go / No-Go recommendation is stated

#### 3. Responsible AI Compliance (`rai-compliance.md`)
- AI component inventory is complete (all LangChain / model calls listed)
- Data privacy assessment confirms whether PII is sent to AI services
- Human oversight checkpoint is described and operational
- Failure modes are documented with graceful degradation confirmed
- Responsible AI checklist is completed for all 6 principles

#### 4. Accessibility Compliance (`accessibility.md`)
- All new components and pages are in scope
- Keyboard navigation tested for every interactive element
- Colour contrast ratios verified against WCAG 2.1 AA (minimum 4.5:1 for normal text)
- Screen reader labels (`aria-label`, `role`) are present on all landmark regions
- Any open issues have a remediation and verification status

**Gate decision:** Approve once all four reports are complete, all critical/high defects are resolved, and Responsible AI + Accessibility checklists are green.

---

## Approval Authority

| Gate | Document(s) | Can Approve |
|---|---|---|
| Requirements | `requirements.md` | ❌ No — Solution Architect only |
| High-Level Design | `hld.md` | ❌ No — Solution Architect only |
| Build Complete | `lld.md`, `tdd.md` | ❌ No — Tech Lead only |
| Testing Complete | `ut-report.md`, `sit-report.md`, `rai-compliance.md`, `accessibility.md` | ✅ Yes |
| Deployment | `deployment.md` | ❌ No — Tech Lead only |

---

## How to Approve a Gate

```bash
cd ticket-resolve/context-templates

# Submit each test deliverable as it is completed
python sdlc_workflow.py submit R-15 testing path/to/ut-report.md
python sdlc_workflow.py submit R-15 testing path/to/sit-report.md
python sdlc_workflow.py submit R-15 testing path/to/rai-compliance.md
python sdlc_workflow.py submit R-15 testing path/to/accessibility.md

# Approve Testing gate once all four pass validation
python sdlc_workflow.py approve R-15 testing \
  --role "Testing Lead" --name "Your Name"
```

---

## Review Checklist

### Unit Test Report Checklist

- [ ] Every UT-xx case from `tdd.md` appears in the execution summary
- [ ] **Actual output captured for each test case** — not "Pass (assumed)" or "Expected behaviour confirmed":
  - For API tests: pasted `curl` response body or HTTP status line
  - For DB tests: pasted SQL query result or row count
  - For startup tests: pasted uvicorn log lines showing table creation or endpoint registration
- [ ] Pass rate ≥ 100% OR all failures have root cause + fix confirmed
- [ ] No test was skipped without documented reason
  - Skipped test must state *why* (e.g., "UT-05 skipped — external service unavailable in dev")
- [ ] **Data integrity verified:** at least one test case confirms computation columns have non-trivial values (e.g., `SELECT COUNT(*) FROM telco_tickets WHERE created_at != updated_at AND status='resolved'` > 0)
- [ ] Coverage notes acknowledge any untested code paths
- [ ] Sign-off section completed with name, date, and environment
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py ut-report.md`

### SIT Report Checklist

- [ ] Every IT-xx scenario from `tdd.md` has a result row in the execution table
- [ ] Evidence column is not empty (screenshot, curl output, or log reference)
- [ ] Defects table: all Critical and High severity defects are `Fixed`
- [ ] Regression check table covers all features listed in `R-1` through current release
- [ ] Environment details section is complete (browser version, DB row count)
- [ ] Sign-off recommendation is `Go` or `No-Go` with clear rationale
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py sit-report.md`

### Responsible AI Compliance Checklist

- [ ] AI Component Inventory lists every LangChain chain, agent, or model call
- [ ] Data Privacy: explicitly states whether ticket data contains PII
- [ ] Bias & Fairness: mitigation is described (not just "risk low")
- [ ] Explainability: `reasons` array and `confidence_score` display confirmed in UI
- [ ] Human Oversight: `pending_review` status flow described and tested
- [ ] Failure Modes: each AI component has a documented graceful degradation path
- [ ] Audit Trail: AI decision logging confirmed in DB
- [ ] All 6 RAI checklist items answered (not left as `[FILL]`)
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py rai-compliance.md`

### Accessibility Compliance Checklist

- [ ] Scope table lists every new/modified component and page
- [ ] Keyboard navigation: every interactive element is Tab-reachable OR justified as non-interactive
- [ ] Screen reader: all new `<section>` elements have `aria-label`
- [ ] Colour contrast: all new palette combinations pass WCAG 2.1 AA (4.5:1 text, 3:1 UI)
- [ ] `animate-pulse` and chart transitions: `prefers-reduced-motion` compliance noted
- [ ] Issues table: all Critical/High issues have `Verified: Yes`
- [ ] No `[FILL]` placeholders remain
- [ ] Validator passes: `python validate_prompt.py accessibility.md`

---

## Escalation & Partial Approval

The Testing Lead may approve the gate with open Low/Medium defects if they are formally deferred:
- Record the deferral in the SIT report defects table with status `Deferred`
- Add a note to the approval: `--name "Jane Smith (2 low defects deferred to R-16)"`

Critical or High severity open defects block approval regardless.
