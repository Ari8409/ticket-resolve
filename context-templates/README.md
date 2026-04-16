# NOC Platform — Context Templates

Reusable prompt scaffolding for the `ticket-resolve` platform. Every template contains pre-filled platform constants and clearly-marked `[FILL]` placeholders so future releases start with a complete, correctly-structured context rather than free-form text.

---

## Directory Layout

```
context-templates/
├── README.md                        ← this file
├── validate_prompt.py               ← single-file template guardrail
├── sdlc_workflow.py                 ← full SDLC gate enforcement engine
├── roles/
│   ├── solution-architect.md        ← SA responsibilities + review checklists
│   ├── tech-lead.md                 ← TL responsibilities + review checklists
│   └── testing-lead.md              ← Testing Lead responsibilities + review checklists
├── releases/                        ← per-release state (created by sdlc_workflow.py)
│   └── R-15/
│       └── state.json
├── enhancements/
│   ├── frontend.md                  ← React/UI enhancement request
│   ├── database.md                  ← SQLite schema / query change
│   └── integration.md               ← FastAPI endpoint / external API
└── deliverables/
    ├── requirements.md
    ├── hld.md                       ← High-Level Design
    ├── lld.md                       ← Low-Level Design
    ├── tdd.md                       ← Test Design Document
    ├── ut-report.md                 ← Unit Test Report
    ├── sit-report.md                ← System Integration Test Report
    ├── deployment.md
    ├── rai-compliance.md            ← Responsible AI Compliance
    └── accessibility.md
```

---

## SDLC Gate Workflow

Every release must pass through 5 sequential gates. Each gate is owned by a specific role. **No gate can be skipped. Approvals are recorded in `releases/<release-id>/state.json`.**

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  GATE 1  Requirements       Deliverable: requirements.md         │
  │          Approver:          Solution Architect                   │
  │          Unblocks:          HLD phase                            │
  ├──────────────────────────────────────────────────────────────────┤
  │  GATE 2  High-Level Design  Deliverable: hld.md                  │
  │          Approver:          Solution Architect                   │
  │          Unblocks:          Build phase (LLD + TDD + code)       │
  ├──────────────────────────────────────────────────────────────────┤
  │  GATE 3  Build Complete     Deliverables: lld.md + tdd.md        │
  │          Approver:          Tech Lead                            │
  │          Rule:              LLD and TDD must be updated to       │
  │                             reflect the actual build — not       │
  │                             the original plan                    │
  │          Unblocks:          Testing phase                        │
  ├──────────────────────────────────────────────────────────────────┤
  │  GATE 4  Testing Complete   Deliverables: ut-report.md           │
  │                                          sit-report.md           │
  │                                          rai-compliance.md       │
  │                                          accessibility.md        │
  │          Approver:          Testing Lead                         │
  │          Unblocks:          Deployment phase                     │
  ├──────────────────────────────────────────────────────────────────┤
  │  GATE 5  Deployment         Deliverable: deployment.md           │
  │          Approver:          Tech Lead                            │
  │          Unblocks:          Release complete                     │
  └──────────────────────────────────────────────────────────────────┘
```

### Role Responsibilities (summary)

| Role | Gates | What They Review |
|---|---|---|
| **Solution Architect** | 1, 2 | Business alignment, architecture soundness, tech decisions |
| **Tech Lead** | 3, 5 | Build accuracy (LLD/TDD match code), deployment runbook |
| **Testing Lead** | 4 | UT + SIT evidence, RAI compliance, accessibility standards |

Full checklists for each role: `roles/solution-architect.md` · `roles/tech-lead.md` · `roles/testing-lead.md`

### SDLC Workflow CLI

```bash
cd ticket-resolve/context-templates

# 1. Initialise a new release
python sdlc_workflow.py init R-15 "Alarm Trend Chart"

# 2. Check overall status at any time
python sdlc_workflow.py status R-15

# 3. Submit a filled deliverable (auto-validates via validate_prompt logic)
python sdlc_workflow.py submit R-15 requirements path/to/requirements.md

# 4. Approve a gate (role must match required approver)
python sdlc_workflow.py approve R-15 requirements \
  --role "Solution Architect" --name "Alice"

# 5. Check if a specific gate is cleared before proceeding
python sdlc_workflow.py check R-15 build

# 6. List all tracked releases
python sdlc_workflow.py list
```

### Complete release walkthrough

```
# ─── GATE 1: Requirements ────────────────────────────────────────
python sdlc_workflow.py submit  R-15 requirements requirements.md
python sdlc_workflow.py approve R-15 requirements --role "Solution Architect" --name "Alice"

# ─── GATE 2: HLD ─────────────────────────────────────────────────
python sdlc_workflow.py submit  R-15 hld hld.md
python sdlc_workflow.py approve R-15 hld --role "Solution Architect" --name "Alice"

# ─── BUILD PHASE (code written here) ─────────────────────────────
# Update lld.md and tdd.md to reflect what was actually built

# ─── GATE 3: Build ───────────────────────────────────────────────
python sdlc_workflow.py submit  R-15 build lld.md
python sdlc_workflow.py submit  R-15 build tdd.md
python sdlc_workflow.py approve R-15 build --role "Tech Lead" --name "Bob"

# ─── TESTING PHASE (execute all tests here) ──────────────────────
python sdlc_workflow.py submit  R-15 testing ut-report.md
python sdlc_workflow.py submit  R-15 testing sit-report.md
python sdlc_workflow.py submit  R-15 testing rai-compliance.md
python sdlc_workflow.py submit  R-15 testing accessibility.md
python sdlc_workflow.py approve R-15 testing --role "Testing Lead" --name "Carol"

# ─── GATE 5: Deployment ──────────────────────────────────────────
python sdlc_workflow.py submit  R-15 deployment deployment.md
python sdlc_workflow.py approve R-15 deployment --role "Tech Lead" --name "Bob"
```

---

## Guardrail — Validate Before Executing

**A prompt that still contains unfilled placeholders or missing sections must not be executed.**
Run the validator on every filled prompt file before submitting it for implementation:

```bash
cd ticket-resolve/context-templates
python validate_prompt.py path/to/my-release-15-frontend.md
```

The validator checks:
- No `[FILL]` / `[FILL: hint]` placeholders remain in the document
- All required section headings for the detected template type are present
- Document Metadata fields (Release, RICEF ID, Date, Status, …) are fully filled
- RICEF ID matches the `R-<number>` format

**Exit codes:**
- `0` — PASSED, safe to execute
- `1` — FAILED, issues listed; fix and re-run before proceeding
- `2` — Usage error (wrong arguments or file not found)

Example of a failed run:

```
============================================================
NOC Platform Prompt Validator
File   : my-release-15-frontend.md
Type   : Enhancement / frontend
============================================================

FAILED — 3 error(s) must be fixed before executing:

  3 unfilled placeholder(s) found — replace every [FILL] with actual content before executing:
  Line   18: ## 2. Feature Description [FILL]
  Line   42: - RICEF ID: [FILL: R-xx]
  Line   61: - [ ] [FILL: e.g., Widget renders within 200ms of page load]

Fix the issues above, then re-run this validator before proceeding.
```

---

## How to Use

### Starting a new release

1. **Identify the change type** — Frontend UI? New database schema? New API endpoint? Use the matching enhancement template.
2. **Copy the template** into a new file (e.g. `my-release-15-frontend.md`).
3. **Fill every `[FILL]` section** — these are the only parts that change per release.
4. **Leave `[PRE-FILLED]` sections unchanged** — they contain platform constants verified against the current codebase.
5. **Run the validator** — `python validate_prompt.py my-release-15-frontend.md` — fix any reported issues.
6. **Execute the prompt** only after the validator exits with code 0.
7. **Generate deliverables** — after implementation, copy the relevant deliverable template, fill it, validate it, then produce the document.

### Template conventions

| Marker | Meaning |
|---|---|
| `[FILL: hint]` | You must supply this value — the hint describes what's expected |
| `[FILL]` | You must supply this section — no further hint needed |
| `[PRE-FILLED]` | Platform constant — do not change unless the platform itself changes |
| `<!-- comment -->` | Guidance note — delete before submitting the prompt |
| `[FILL — if applicable]` | Optional section — omit entirely if not relevant to this release |

---

## Platform Quick Reference

| Layer | Stack |
|---|---|
| Backend | FastAPI 0.115 · Python 3.12 · aiosqlite · SQLite `data/tickets.db` · LangChain 0.3 · ChromaDB |
| Frontend | React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5 · react-leaflet |
| Infra | Node 20 · uvicorn · httpx ≥ 0.27 |

**RICEF Taxonomy:** R=Report · I=Interface · C=Conversion · E=Extension/Agent · F=Form/UI

**Design palette:** slate-800 `#1e293b` · RED `#E60028` · BLUE `#0078D4` · GREEN `#22c55e` · AMBER `#f59e0b`

---

## Release History (R-1 → R-14)

| RICEF ID | Release | Type | Feature |
|---|---|---|---|
| R-1 | Release 1 | F | Core Dashboard + Ticket Ingest |
| R-2 | Release 2 | I | FastAPI REST Layer |
| R-3 | Release 3 | E | LangChain Triage Agent |
| R-4 | Release 4 | F | Triage Queue UI |
| R-5 | Release 5 | I | SOP Knowledge Base + ChromaDB |
| R-6 | Release 6 | F | Chat Assistant Widget |
| R-7 | Release 7 | R | Dispatch & Analytics Dashboard |
| R-8 | Release 8 | F | SDLC Tracking Dashboard |
| R-9 | Release 9 | F | Deliverables Dashboard |
| R-10 | Release 10 | I | Network Topology API |
| R-11 | Release 11 | F | Network Topology Widget (SVG) |
| R-12 | Release 12 | F | Hot Nodes + Location Map (Leaflet) |
| R-13 | Release 13 | R | C-Suite PowerPoint Generator |
| R-14 | Release 14 | R | Dashboard Screenshot Capture |
