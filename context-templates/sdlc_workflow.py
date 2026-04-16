#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdlc_workflow.py - NOC Platform SDLC gate enforcement

Manages the full release lifecycle with role-based approval gates.
State is persisted in context-templates/releases/<release-id>/state.json

SDLC Gate Order
───────────────
  GATE 1  requirements   ← Solution Architect approves
            Deliverables : requirements.md
  GATE 2  hld            ← Solution Architect approves
            Deliverables : hld.md
            Prerequisite : data-check must PASS before HLD can be approved
  GATE 3  build          ← Tech Lead approves
            Deliverables : lld.md + tdd.md  (must be updated post-build)
            Prerequisite : scan must PASS on all changed source files
            Prerequisite : dashboard-check must PASS (SDLCDashboard.tsx updated with new release)
  GATE 4  testing        ← Testing Lead approves
            Deliverables : ut-report.md + sit-report.md + rai-compliance.md + accessibility.md
  GATE 5  deployment     ← Tech Lead approves
            Deliverables : deployment.md + lessons-learned.md
            Prerequisite : lessons-check must PASS before Deployment can be approved
            Prerequisite : framework-sync must PASS (release registered in sdlc-framework)

Usage
─────
  python sdlc_workflow.py init            R-15 "Alarm Trend Chart"
  python sdlc_workflow.py status          R-15
  python sdlc_workflow.py submit          R-15 requirements  path/to/requirements.md
  python sdlc_workflow.py approve         R-15 requirements  --role "Solution Architect" --name "Alice"
  python sdlc_workflow.py check           R-15 build
  python sdlc_workflow.py list
  python sdlc_workflow.py data-check      R-15 [--db data/tickets.db] [--table telco_tickets]
  python sdlc_workflow.py scan            R-15 app/api/v1/sla.py frontend/src/components/SLAWidget.tsx
  python sdlc_workflow.py lessons-check   R-15 [--dashboard path/to/SDLCDashboard.tsx] [--md path/to/lessons-learned.md]
  python sdlc_workflow.py dashboard-check R-16 [--dashboard path/to/SDLCDashboard.tsx]
  python sdlc_workflow.py framework-sync  R-16 [--url http://localhost:8002]

Exit codes:  0 = success/passed   1 = gate blocked / validation failed   2 = usage error
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows terminals that default to cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
RELEASES_DIR = SCRIPT_DIR / "releases"

# ---------------------------------------------------------------------------
# Gate definitions
# ---------------------------------------------------------------------------

GATES: list[str] = ["requirements", "hld", "build", "testing", "deployment"]

GATE_META: dict[str, dict] = {
    "requirements": {
        "label": "Requirements",
        "approver_role": "Solution Architect",
        "deliverables": ["requirements"],
        "description": "Requirements document reviewed and approved before build begins.",
        # No pre-flight prerequisite for Gate 1
        "requires_data_check": False,
        "requires_scan": False,
    },
    "hld": {
        "label": "High-Level Design",
        "approver_role": "Solution Architect",
        "deliverables": ["hld"],
        "description": "HLD approved by Solution Architect before LLD / build starts.",
        # Gate 2 requires a passing data-check before approval
        "requires_data_check": True,
        "requires_scan": False,
    },
    "build": {
        "label": "Build Complete",
        "approver_role": "Tech Lead",
        "deliverables": ["lld", "tdd"],
        "description": "LLD and TDD updated post-build and approved by Tech Lead.",
        # Gate 3 requires a passing code scan before approval
        "requires_data_check":      False,
        "requires_scan":            True,
        # Gate 3 also requires SDLCDashboard.tsx to be updated with the new release
        "requires_dashboard_check": True,
    },
    "testing": {
        "label": "Testing Complete",
        "approver_role": "Testing Lead",
        "deliverables": ["ut-report", "sit-report", "rai-compliance", "accessibility"],
        "description": "All test reports approved by Testing Lead before deployment.",
        "requires_data_check": False,
        "requires_scan": False,
    },
    "deployment": {
        "label": "Deployment",
        "approver_role": "Tech Lead",
        "deliverables": ["deployment", "lessons-learned"],
        "description": "Deployment document + Lessons Learned reviewed and approved by Tech Lead.",
        "requires_data_check":    False,
        "requires_scan":          False,
        # Gate 5 requires a passing lessons-check before approval
        "requires_lessons_check": True,
        # Gate 5 also requires the release to be registered in the sdlc-framework
        "requires_framework_sync": True,
    },
}

VALID_ROLES = {"Solution Architect", "Tech Lead", "Testing Lead"}

DELIVERABLE_TEMPLATE_NAMES = {
    "requirements":    "Requirements Document",
    "hld":             "High-Level Design",
    "lld":             "Low-Level Design",
    "tdd":             "Test Design Document",
    "ut-report":       "Unit Test Report",
    "sit-report":      "SIT Report",
    "rai-compliance":  "Responsible AI Compliance Report",
    "accessibility":   "Accessibility Compliance Report",
    "deployment":      "Deployment Document",
    "lessons-learned": "Lessons Learned",
}

# ---------------------------------------------------------------------------
# Gate status values
# ---------------------------------------------------------------------------

STATUS_PENDING   = "pending"     # not started
STATUS_SUBMITTED = "submitted"   # deliverables validated, awaiting approval
STATUS_APPROVED  = "approved"    # gate cleared
STATUS_BLOCKED   = "blocked"     # prerequisite gate not cleared


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _release_dir(release_id: str) -> Path:
    return RELEASES_DIR / release_id.upper()


def _state_path(release_id: str) -> Path:
    return _release_dir(release_id) / "state.json"


def _load_state(release_id: str) -> dict:
    p = _state_path(release_id)
    if not p.exists():
        _die(f"Release '{release_id}' not found. Run: python sdlc_workflow.py init {release_id} \"Release Name\"")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_state(state: dict) -> None:
    p = _state_path(state["release_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gate_index(gate: str) -> int:
    return GATES.index(gate)


def _current_phase(state: dict) -> str:
    """Return the earliest gate that is not yet approved."""
    for g in GATES:
        if state["gates"][g]["status"] != STATUS_APPROVED:
            return g
    return "complete"


# ---------------------------------------------------------------------------
# Prompt validation (reuses validate_prompt logic inline)
# ---------------------------------------------------------------------------

FILL_PATTERN   = re.compile(r"\[FILL(?::[^\]]*)?\]")
HEADING_PATTERN = re.compile(r"^#{1,4}\s+(.+)$", re.MULTILINE)

DELIVERABLE_REQUIRED_SECTIONS: dict[str, list[str]] = {
    "requirements":   ["Document Metadata", "Business Objective", "Functional Requirements",
                        "Non-Functional Requirements", "Acceptance Criteria"],
    "hld":            ["Document Metadata", "Architecture Overview", "Component Inventory",
                        "API Contract Summary", "Technology Decisions"],
    "lld":            ["Document Metadata", "Module Breakdown", "Database Schema DDL",
                        "Pydantic Models", "React Component Tree", "Error Handling Matrix"],
    "tdd":            ["Document Metadata", "Test Scope", "Unit-Level Test Cases",
                        "Integration Test Cases", "Edge Cases"],
    "ut-report":      ["Document Metadata", "Test Execution Summary", "Pass Rate", "Sign-off"],
    "sit-report":     ["Document Metadata", "Integration Scenarios Tested",
                        "Test Execution Results", "Regression Check", "Sign-off"],
    "rai-compliance": ["Document Metadata", "AI Component Inventory", "Data Privacy Assessment",
                        "Human Oversight", "Responsible AI Checklist"],
    "accessibility":  ["Document Metadata", "Scope", "Keyboard Navigation",
                        "Colour Contrast", "Issues & Remediation"],
    "deployment":      ["Document Metadata", "Pre-Deployment Checklist", "Deployment Steps",
                         "Rollback Procedure", "Smoke Test After Deploy"],
    "lessons-learned": ["Document Metadata", "Lessons Learned", "Root Cause", "Fix Applied"],
}


def _validate_deliverable_file(deliverable_key: str, path: Path) -> list[str]:
    """Return list of error strings; empty = valid."""
    errors: list[str] = []
    if not path.exists():
        return [f"File not found: {path}"]

    text = path.read_text(encoding="utf-8")

    # 1. Unfilled placeholders
    unfilled = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("<!--") or stripped.endswith("-->"):
            continue
        if FILL_PATTERN.search(line):
            unfilled.append((i, line.rstrip()))

    if unfilled:
        errors.append(f"{len(unfilled)} unfilled [FILL] placeholder(s) remain:")
        for lineno, line in unfilled[:10]:
            errors.append(f"  Line {lineno:4d}: {line[:100]}")
        if len(unfilled) > 10:
            errors.append(f"  ... and {len(unfilled)-10} more")

    # 2. Required sections
    headings = {m.group(1).strip() for m in HEADING_PATTERN.finditer(text)}
    required = DELIVERABLE_REQUIRED_SECTIONS.get(deliverable_key, [])
    missing = [s for s in required if not any(s.lower() in h.lower() for h in headings)]
    if missing:
        errors.append(f"{len(missing)} required section(s) missing:")
        for s in missing:
            errors.append(f"  - {s}")

    return errors


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------

def _die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _divider(char: str = "─", width: int = 62) -> str:
    return char * width


def _phase_badge(status: str) -> str:
    icons = {
        STATUS_PENDING:   "○  pending",
        STATUS_SUBMITTED: "◑  submitted — awaiting approval",
        STATUS_APPROVED:  "●  APPROVED",
        STATUS_BLOCKED:   "✕  blocked (prior gate not approved)",
    }
    return icons.get(status, status)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    release_id   = args.release_id.upper()
    release_name = args.release_name

    state_path = _state_path(release_id)
    if state_path.exists():
        _die(f"Release {release_id} already exists. Use 'status {release_id}' to view it.")

    state: dict = {
        "release_id":   release_id,
        "release_name": release_name,
        "created_at":   _now(),
        "gates": {
            gate: {
                "status":      STATUS_PENDING if gate == GATES[0] else STATUS_BLOCKED,
                "deliverables": {},
                "approval":    None,
            }
            for gate in GATES
        },
    }
    # First gate is always open
    state["gates"][GATES[0]]["status"] = STATUS_PENDING
    _save_state(state)

    print(_divider("═"))
    print(f"  NOC Platform SDLC — Release Initialised")
    print(_divider("═"))
    print(f"  Release ID  : {release_id}")
    print(f"  Name        : {release_name}")
    print(f"  Created     : {_now()[:10]}")
    print()
    print("  SDLC Gate Sequence:")
    for i, g in enumerate(GATES, 1):
        meta = GATE_META[g]
        print(f"  {i}. {meta['label']:<22} → approver: {meta['approver_role']}")
    print()
    print(f"  Next action:")
    print(f"    1. Fill enhancements/frontend.md (or database.md / integration.md)")
    print(f"    2. Fill deliverables/requirements.md")
    print(f"    3. python sdlc_workflow.py submit {release_id} requirements <path>")
    print(_divider("═"))


def cmd_status(args: argparse.Namespace) -> None:
    state      = _load_state(args.release_id)
    release_id = state["release_id"]
    phase      = _current_phase(state)

    print(_divider("═"))
    print(f"  NOC Platform SDLC Status — {release_id}: {state['release_name']}")
    print(_divider("═"))
    print(f"  Created     : {state['created_at'][:10]}")
    print(f"  Phase       : {'COMPLETE' if phase == 'complete' else GATE_META[phase]['label']}")
    print()

    for g in GATES:
        meta  = GATE_META[g]
        gdata = state["gates"][g]
        status_label = _phase_badge(gdata["status"])

        print(f"  ┌─ Gate: {meta['label']}")
        print(f"  │  Status   : {status_label}")
        print(f"  │  Approver : {meta['approver_role']}")

        # Deliverables
        for d in meta["deliverables"]:
            dname = DELIVERABLE_TEMPLATE_NAMES.get(d, d)
            ddata = gdata["deliverables"].get(d)
            if ddata:
                tick = "✓" if ddata.get("valid") else "✗"
                sub_date = ddata.get("submitted_at", "")[:10]
                print(f"  │  [{tick}] {dname:<36} submitted {sub_date}")
            else:
                print(f"  │  [ ] {dname}")

        # Approval
        if gdata["approval"]:
            a = gdata["approval"]
            print(f"  │  Approved  : {a['name']} ({a['role']}) on {a['approved_at'][:10]}")
        elif gdata["status"] == STATUS_SUBMITTED:
            print(f"  │  Approval  : Pending — {meta['approver_role']} must run:")
            print(f"  │    python sdlc_workflow.py approve {release_id} {g} --role \"{meta['approver_role']}\" --name \"<name>\"")

        print(f"  └{'─'*52}")
        print()

    # ── Guardrail summary ──────────────────────────────────────────────────
    guardrails = state.get("guardrails", {})
    if guardrails:
        print(f"  ┌─ Guardrail Results")
        dc = guardrails.get("data_check")
        if dc:
            dc_mark = "✓" if dc["passed"] else "✗"
            print(f"  │  [{dc_mark}] Data Quality Check  ({dc['ran_at'][:10]})  "
                  f"DB: {dc.get('db','')}  Table: {dc.get('table','')}")
        sc = guardrails.get("scan")
        if sc:
            sc_mark = "✓" if sc["passed"] else "✗"
            files_summary = f"{len(sc.get('files',[]))} file(s)"
            print(f"  │  [{sc_mark}] Static Code Scan    ({sc['ran_at'][:10]})  {files_summary}")
        lc = guardrails.get("lessons_check")
        if lc:
            lc_mark = "✓" if lc["passed"] else "✗"
            print(f"  │  [{lc_mark}] Lessons Check       ({lc['ran_at'][:10]})")
        dbc = guardrails.get("dashboard_check")
        if dbc:
            dbc_mark = "✓" if dbc["passed"] else "✗"
            print(f"  │  [{dbc_mark}] Dashboard Check     ({dbc['ran_at'][:10]})")
        fs = guardrails.get("framework_sync")
        if fs:
            fs_mark = "✓" if fs["passed"] else "✗"
            sync_id = fs.get("synced_id","?")
            print(f"  │  [{fs_mark}] Framework Sync      ({fs['ran_at'][:10]})  id={sync_id}")
        print(f"  └{'─'*52}")
        print()

    if phase == "complete":
        print("  ✓ All gates cleared — release is complete.")
    else:
        next_steps(state, phase)

    print(_divider("═"))


def next_steps(state: dict, phase: str) -> None:
    meta       = GATE_META[phase]
    gdata      = state["gates"][phase]
    rid        = state["release_id"]
    guardrails = state.get("guardrails", {})

    print("  Next steps:")
    if gdata["status"] in (STATUS_PENDING, STATUS_BLOCKED):
        for d in meta["deliverables"]:
            if d not in gdata["deliverables"] or not gdata["deliverables"][d].get("valid"):
                print(f"    • Fill and validate deliverables/{d}.md")
                print(f"      python sdlc_workflow.py submit {rid} {phase} path/to/{d}.md")
    elif gdata["status"] == STATUS_SUBMITTED:
        # Show guardrail prerequisites if not yet satisfied
        if meta.get("requires_data_check"):
            dc = guardrails.get("data_check")
            if not dc or not dc.get("passed"):
                print(f"    • Run data quality pre-flight check (required before HLD approval):")
                print(f"      python sdlc_workflow.py data-check {rid}")
        if meta.get("requires_scan"):
            sc = guardrails.get("scan")
            if not sc or not sc.get("passed"):
                print(f"    • Run static code scan (required before Build approval):")
                print(f"      python sdlc_workflow.py scan {rid} <changed_files>")
        if meta.get("requires_lessons_check"):
            lc = guardrails.get("lessons_check")
            if not lc or not lc.get("passed"):
                print(f"    • Run lessons-learned check (required before Deployment approval):")
                print(f"      python sdlc_workflow.py lessons-check {rid}")
        if meta.get("requires_dashboard_check"):
            dbc = guardrails.get("dashboard_check")
            if not dbc or not dbc.get("passed"):
                print(f"    • Update SDLCDashboard.tsx with {rid} entries, then run dashboard check:")
                print(f"      python sdlc_workflow.py dashboard-check {rid}")
        if meta.get("requires_framework_sync"):
            fs = guardrails.get("framework_sync")
            if not fs or not fs.get("passed"):
                print(f"    • Register {rid} in sdlc-framework (ensure backend on :8002):")
                print(f"      python sdlc_workflow.py framework-sync {rid}")
        print(f"    • {meta['approver_role']} must approve gate '{phase}':")
        print(f"      python sdlc_workflow.py approve {rid} {phase} --role \"{meta['approver_role']}\" --name \"<name>\"")


def cmd_submit(args: argparse.Namespace) -> None:
    state      = _load_state(args.release_id)
    release_id = state["release_id"]
    gate       = args.gate
    path       = Path(args.deliverable_path)

    if gate not in GATES:
        _die(f"Unknown gate '{gate}'. Valid gates: {', '.join(GATES)}")

    gdata = state["gates"][gate]

    # Gate must not be blocked
    if gdata["status"] == STATUS_BLOCKED:
        prior = GATES[_gate_index(gate) - 1]
        _die(
            f"Gate '{gate}' is BLOCKED — the preceding gate '{prior}' must be approved first.\n"
            f"  Check status: python sdlc_workflow.py status {release_id}",
            code=1,
        )

    # Infer deliverable key from filename
    # Strategy: find the first expected deliverable key that is a substring of the filename stem
    stem = path.stem.lower().replace("_", "-")
    expected = GATE_META[gate]["deliverables"]

    # Exact match first, then substring match
    deliverable_key: str | None = None
    if stem in expected:
        deliverable_key = stem
    else:
        for candidate in expected:
            # normalise candidate for comparison (replace - with optional separator)
            if candidate.replace("-", "") in stem.replace("-", ""):
                deliverable_key = candidate
                break

    if deliverable_key is None:
        _die(
            f"Cannot determine deliverable type from filename '{path.name}'.\n"
            f"  Expected deliverable(s) for gate '{gate}': {', '.join(expected)}\n"
            f"  Tip: name your file to include one of: {', '.join(expected)}",
            code=1,
        )

    print(_divider("═"))
    print(f"  Submitting deliverable: {DELIVERABLE_TEMPLATE_NAMES.get(deliverable_key, deliverable_key)}")
    print(f"  Gate    : {GATE_META[gate]['label']}")
    print(f"  Release : {release_id}")
    print(f"  File    : {path}")
    print(_divider())

    errors = _validate_deliverable_file(deliverable_key, path)

    if errors:
        print("  FAILED — deliverable has errors that must be fixed:\n")
        for e in errors:
            print(f"  {e}")
        print()
        print("  Fix the issues above, then re-submit.")
        print(_divider("═"))
        sys.exit(1)

    # Record submission
    gdata["deliverables"][deliverable_key] = {
        "path":         str(path.resolve()),
        "valid":        True,
        "submitted_at": _now(),
    }

    # Check if all deliverables for this gate are now submitted
    all_submitted = all(
        d in gdata["deliverables"] and gdata["deliverables"][d].get("valid")
        for d in GATE_META[gate]["deliverables"]
    )

    if all_submitted:
        gdata["status"] = STATUS_SUBMITTED
        print(f"  PASSED — deliverable validated and recorded.")
        print()
        print(f"  All deliverables for gate '{gate}' are now submitted.")
        print(f"  Awaiting approval from: {GATE_META[gate]['approver_role']}")
        print()
        print(f"  Approve with:")
        print(f"    python sdlc_workflow.py approve {release_id} {gate} \\")
        print(f"      --role \"{GATE_META[gate]['approver_role']}\" --name \"<your name>\"")
    else:
        remaining = [
            d for d in GATE_META[gate]["deliverables"]
            if d not in gdata["deliverables"] or not gdata["deliverables"][d].get("valid")
        ]
        print(f"  PASSED — deliverable validated and recorded.")
        print(f"  Remaining for this gate: {', '.join(remaining)}")

    _save_state(state)
    print(_divider("═"))


def cmd_approve(args: argparse.Namespace) -> None:
    state      = _load_state(args.release_id)
    release_id = state["release_id"]
    gate       = args.gate
    role       = args.role
    name       = args.name

    if gate not in GATES:
        _die(f"Unknown gate '{gate}'. Valid gates: {', '.join(GATES)}")

    # Role validation
    if role not in VALID_ROLES:
        _die(
            f"Unknown role '{role}'.\n"
            f"  Valid roles: {', '.join(sorted(VALID_ROLES))}",
            code=1,
        )

    required_role = GATE_META[gate]["approver_role"]
    if role != required_role:
        _die(
            f"Gate '{gate}' requires approval from '{required_role}', "
            f"but role '{role}' was provided.\n"
            f"  Only the '{required_role}' can approve this gate.",
            code=1,
        )

    gdata    = state["gates"][gate]
    meta     = GATE_META[gate]
    guardrails = state.get("guardrails", {})

    # ── Prerequisite: data-check required before HLD (Gate 2) ────────────────
    if meta.get("requires_data_check"):
        dc = guardrails.get("data_check")
        if not dc:
            _die(
                f"Gate '{gate}' requires a passing data quality check before approval.\n"
                f"  Run: python sdlc_workflow.py data-check {release_id}\n"
                f"  Then re-run this approve command once it passes.",
                code=1,
            )
        if not dc.get("passed"):
            _die(
                f"Gate '{gate}' is BLOCKED — data quality check failed on {dc.get('ran_at','?')[:10]}.\n"
                f"  Re-run: python sdlc_workflow.py data-check {release_id}\n"
                f"  The check must exit 0 (ALL CLEAR or warnings-only) before HLD can be approved.",
                code=1,
            )

    # ── Prerequisite: code scan required before Build (Gate 3) ───────────────
    if meta.get("requires_scan"):
        sc = guardrails.get("scan")
        if not sc:
            _die(
                f"Gate '{gate}' requires a passing code scan before approval.\n"
                f"  Run: python sdlc_workflow.py scan {release_id} <changed files>\n"
                f"  Then re-run this approve command once it passes.",
                code=1,
            )
        if not sc.get("passed"):
            _die(
                f"Gate '{gate}' is BLOCKED — static code scan failed on {sc.get('ran_at','?')[:10]}.\n"
                f"  Re-run: python sdlc_workflow.py scan {release_id} <changed files>\n"
                f"  All ERROR-level rules must pass before Build gate can be approved.",
                code=1,
            )

    # ── Prerequisite: lessons-check required before Deployment (Gate 5) ──────
    if meta.get("requires_lessons_check"):
        lc = guardrails.get("lessons_check")
        if not lc:
            _die(
                f"Gate '{gate}' requires a passing lessons-learned check before approval.\n"
                f"  Run: python sdlc_workflow.py lessons-check {release_id}\n"
                f"  Then re-run this approve command once it passes.",
                code=1,
            )
        if not lc.get("passed"):
            _die(
                f"Gate '{gate}' is BLOCKED — lessons-learned check failed on {lc.get('ran_at','?')[:10]}.\n"
                f"  1. Add at least one LESSONS_LEARNED entry with  iteration: '{release_id}'\n"
                f"     to frontend/src/pages/SDLCDashboard.tsx\n"
                f"  2. Fill in context-templates/deliverables/lessons-learned.md\n"
                f"  3. Re-run: python sdlc_workflow.py lessons-check {release_id}",
                code=1,
            )

    # ── Prerequisite: dashboard-check required before Build (Gate 3) ─────────
    if meta.get("requires_dashboard_check"):
        dc = guardrails.get("dashboard_check")
        if not dc:
            _die(
                f"Gate '{gate}' requires a passing dashboard check before approval.\n"
                f"  Run: python sdlc_workflow.py dashboard-check {release_id}\n"
                f"  Then re-run this approve command once it passes.",
                code=1,
            )
        if not dc.get("passed"):
            _die(
                f"Gate '{gate}' is BLOCKED — dashboard check failed on {dc.get('ran_at','?')[:10]}.\n"
                f"  Update frontend/src/pages/SDLCDashboard.tsx with R-{release_id} entries:\n"
                f"  • Add '{release_id}' to ReleaseKey type\n"
                f"  • Add entry to RELEASES array\n"
                f"  • Add entry to ITERATIONS array\n"
                f"  • Add at least one item to RICEF array with  iteration: '{release_id}'\n"
                f"  Re-run: python sdlc_workflow.py dashboard-check {release_id}",
                code=1,
            )

    # ── Prerequisite: framework-sync required before Deployment (Gate 5) ─────
    if meta.get("requires_framework_sync"):
        fs = guardrails.get("framework_sync")
        if not fs:
            _die(
                f"Gate '{gate}' requires a passing framework sync check before approval.\n"
                f"  Run: python sdlc_workflow.py framework-sync {release_id}\n"
                f"  Then re-run this approve command once it passes.",
                code=1,
            )
        if not fs.get("passed"):
            _die(
                f"Gate '{gate}' is BLOCKED — framework sync failed on {fs.get('ran_at','?')[:10]}.\n"
                f"  Register {release_id} in the sdlc-framework:\n"
                f"  python sdlc_workflow.py framework-sync {release_id}\n"
                f"  Ensure sdlc-framework backend is running on port 8002.",
                code=1,
            )

    # Gate must be in submitted state
    if gdata["status"] == STATUS_BLOCKED:
        prior = GATES[_gate_index(gate) - 1]
        _die(
            f"Gate '{gate}' is BLOCKED — approve gate '{prior}' first.",
            code=1,
        )
    if gdata["status"] == STATUS_PENDING:
        missing = [
            d for d in GATE_META[gate]["deliverables"]
            if d not in gdata["deliverables"] or not gdata["deliverables"][d].get("valid")
        ]
        _die(
            f"Gate '{gate}' has unsubmitted deliverables: {', '.join(missing)}\n"
            f"  Submit all deliverables before approving.",
            code=1,
        )
    if gdata["status"] == STATUS_APPROVED:
        a = gdata["approval"]
        _die(
            f"Gate '{gate}' is already approved by {a['name']} ({a['role']}) "
            f"on {a['approved_at'][:10]}.",
            code=1,
        )

    # Record approval
    gdata["status"]   = STATUS_APPROVED
    gdata["approval"] = {
        "role":        role,
        "name":        name,
        "approved_at": _now(),
    }

    # Unblock next gate
    idx = _gate_index(gate)
    if idx + 1 < len(GATES):
        next_gate = GATES[idx + 1]
        if state["gates"][next_gate]["status"] == STATUS_BLOCKED:
            state["gates"][next_gate]["status"] = STATUS_PENDING

    _save_state(state)

    phase = _current_phase(state)

    print(_divider("═"))
    print(f"  ✓ Gate APPROVED")
    print(_divider())
    print(f"  Release : {release_id} — {state['release_name']}")
    print(f"  Gate    : {GATE_META[gate]['label']}")
    print(f"  By      : {name} ({role})")
    print(f"  At      : {_now()[:10]}")
    print()

    if phase == "complete":
        print("  ✓ All gates cleared — release is COMPLETE.")
    else:
        print(f"  Next gate UNLOCKED: {GATE_META[phase]['label']}")
        print(f"  Approver required : {GATE_META[phase]['approver_role']}")
        print()
        next_steps(state, phase)

    print(_divider("═"))


def cmd_check(args: argparse.Namespace) -> None:
    state      = _load_state(args.release_id)
    release_id = state["release_id"]
    gate       = args.gate

    if gate not in GATES:
        _die(f"Unknown gate '{gate}'. Valid gates: {', '.join(GATES)}")

    gdata = state["gates"][gate]

    print(_divider("═"))
    print(f"  Gate Check: {GATE_META[gate]['label']}  [{release_id}]")
    print(_divider())

    if gdata["status"] == STATUS_APPROVED:
        print(f"  ✓ Gate is APPROVED — proceed to next phase.")
        sys.exit(0)
    elif gdata["status"] == STATUS_BLOCKED:
        prior = GATES[_gate_index(gate) - 1]
        print(f"  ✗ Gate is BLOCKED — '{prior}' gate must be approved first.")
        print(_divider("═"))
        sys.exit(1)
    elif gdata["status"] == STATUS_SUBMITTED:
        print(f"  ◑ Gate is SUBMITTED — awaiting approval from {GATE_META[gate]['approver_role']}.")
        print()
        print(f"  Approve:")
        print(f"    python sdlc_workflow.py approve {release_id} {gate} \\")
        print(f"      --role \"{GATE_META[gate]['approver_role']}\" --name \"<name>\"")
        print(_divider("═"))
        sys.exit(1)
    else:
        missing = [
            d for d in GATE_META[gate]["deliverables"]
            if d not in gdata["deliverables"] or not gdata["deliverables"][d].get("valid")
        ]
        print(f"  ✗ Gate is PENDING — missing deliverable(s):")
        for d in missing:
            print(f"    • {DELIVERABLE_TEMPLATE_NAMES.get(d, d)}")
        print()
        print(f"  Submit each deliverable:")
        for d in missing:
            print(f"    python sdlc_workflow.py submit {release_id} {gate} path/to/{d}.md")
        print(_divider("═"))
        sys.exit(1)


def cmd_data_check(args: argparse.Namespace) -> None:
    """
    Run data_quality_check.py against the project DB and record the result in state.json.
    Required before Gate 2 (HLD) can be approved.
    """
    state      = _load_state(args.release_id)
    release_id = state["release_id"]

    checker = SCRIPT_DIR / "data_quality_check.py"
    if not checker.exists():
        _die(
            f"data_quality_check.py not found at {checker}.\n"
            f"  Ensure the guardrail scripts are present in context-templates/.",
            code=2,
        )

    # Resolve DB path relative to repo root (two levels up from context-templates/)
    db_path = Path(args.db) if args.db else SCRIPT_DIR.parent / "data" / "tickets.db"
    table   = args.table or "telco_tickets"

    cmd = [sys.executable, str(checker), "--db", str(db_path), "--table", table]
    if args.columns:
        cmd += ["--columns"] + args.columns

    print(_divider("═"))
    print(f"  NOC Platform — Data Quality Pre-Flight Check  [{release_id}]")
    print(f"  DB    : {db_path}")
    print(f"  Table : {table}")
    print(_divider())

    result = subprocess.run(cmd, capture_output=False)
    passed = result.returncode == 0

    # Record in state
    state.setdefault("guardrails", {})
    state["guardrails"]["data_check"] = {
        "passed":      passed,
        "db":          str(db_path),
        "table":       table,
        "ran_at":      _now(),
        "exit_code":   result.returncode,
    }
    _save_state(state)

    print(_divider())
    if passed:
        print(f"  Result recorded: PASS — Gate 2 (HLD) pre-flight satisfied.")
    else:
        print(f"  Result recorded: FAIL — Gate 2 (HLD) approval is BLOCKED until this passes.")
        print(f"  Fix the issues above and re-run: python sdlc_workflow.py data-check {release_id}")
    print(_divider("═"))

    sys.exit(result.returncode if result.returncode in (0, 1) else 0)


def cmd_scan(args: argparse.Namespace) -> None:
    """
    Run code_scan.py against specified source files and record the result in state.json.
    Required before Gate 3 (Build) can be approved.
    """
    state      = _load_state(args.release_id)
    release_id = state["release_id"]

    scanner = SCRIPT_DIR / "code_scan.py"
    if not scanner.exists():
        _die(
            f"code_scan.py not found at {scanner}.\n"
            f"  Ensure the guardrail scripts are present in context-templates/.",
            code=2,
        )

    if not args.files:
        _die(
            "No source files specified.\n"
            f"  Usage: python sdlc_workflow.py scan {release_id} <file1> [file2 ...]",
            code=2,
        )

    # Resolve file paths relative to repo root
    repo_root = SCRIPT_DIR.parent
    resolved  = []
    for f in args.files:
        fp = Path(f)
        if not fp.is_absolute():
            fp = repo_root / fp
        resolved.append(str(fp))

    cmd = [sys.executable, str(scanner)] + resolved

    print(_divider("═"))
    print(f"  NOC Platform — Static Code Scan  [{release_id}]")
    print(f"  Files : {len(resolved)}")
    for f in resolved:
        print(f"    {f}")
    print(_divider())

    result = subprocess.run(cmd, capture_output=False)
    passed = result.returncode == 0

    # Record in state
    state.setdefault("guardrails", {})
    state["guardrails"]["scan"] = {
        "passed":    passed,
        "files":     resolved,
        "ran_at":    _now(),
        "exit_code": result.returncode,
    }
    _save_state(state)

    print(_divider())
    if passed:
        print(f"  Result recorded: PASS — Gate 3 (Build) scan prerequisite satisfied.")
    else:
        print(f"  Result recorded: FAIL — Gate 3 (Build) approval is BLOCKED until this passes.")
        print(f"  Fix the errors above and re-run: python sdlc_workflow.py scan {release_id} <files>")
    print(_divider("═"))

    sys.exit(result.returncode if result.returncode in (0, 1) else 0)


def cmd_lessons_check(args: argparse.Namespace) -> None:
    """
    Run lessons_check.py for the release and record the result in state.json.
    Required before Gate 5 (Deployment) can be approved.
    """
    state      = _load_state(args.release_id)
    release_id = state["release_id"]

    checker = SCRIPT_DIR / "lessons_check.py"
    if not checker.exists():
        _die(
            f"lessons_check.py not found at {checker}.\n"
            f"  Ensure the guardrail scripts are present in context-templates/.",
            code=2,
        )

    cmd = [sys.executable, str(checker), release_id]
    if args.dashboard:
        cmd += ["--dashboard", args.dashboard]
    if args.md:
        cmd += ["--md", args.md]
    if args.min_entries:
        cmd += ["--min-entries", str(args.min_entries)]

    print(_divider("═"))
    print(f"  NOC Platform — Lessons Learned Check  [{release_id}]")
    if args.dashboard:
        print(f"  Dashboard : {args.dashboard}")
    if args.md:
        print(f"  MD file   : {args.md}")
    print(_divider())

    result = subprocess.run(cmd, capture_output=False)
    passed = result.returncode == 0

    # Record in state
    state.setdefault("guardrails", {})
    state["guardrails"]["lessons_check"] = {
        "passed":    passed,
        "ran_at":    _now(),
        "exit_code": result.returncode,
    }
    _save_state(state)

    print(_divider())
    if passed:
        print(f"  Result recorded: PASS — Gate 5 (Deployment) lessons-check prerequisite satisfied.")
    else:
        print(f"  Result recorded: FAIL — Gate 5 (Deployment) approval is BLOCKED until this passes.")
        print(f"  1. Add LESSONS_LEARNED entries with  iteration: '{release_id}'  to SDLCDashboard.tsx")
        print(f"  2. Fill in the lessons-learned.md deliverable")
        print(f"  3. Re-run: python sdlc_workflow.py lessons-check {release_id}")
    print(_divider("═"))

    sys.exit(result.returncode if result.returncode in (0, 1) else 0)


def cmd_dashboard_check(args: argparse.Namespace) -> None:
    """
    Verify that SDLCDashboard.tsx contains entries for the release.
    Required before Gate 3 (Build) can be approved.

    Checks:
      1. ReleaseKey type union includes the release key (e.g. 'R-16')
      2. RELEASES array has an entry with key: 'R-16'
      3. ITERATIONS array has at least one block with releaseKey: 'R-16'
      4. RICEF array has at least one item with iteration: 'R-16'
    """
    state      = _load_state(args.release_id)
    release_id = state["release_id"]         # e.g. "R-16"

    # Resolve dashboard path
    dashboard_path = (
        Path(args.dashboard)
        if args.dashboard
        else SCRIPT_DIR.parent / "frontend" / "src" / "pages" / "SDLCDashboard.tsx"
    )

    print(_divider("═"))
    print(f"  NOC Platform — Dashboard Check  [{release_id}]")
    print(f"  File : {dashboard_path}")
    print(_divider())

    errors: list[str] = []

    if not dashboard_path.exists():
        errors.append(f"Dashboard file not found: {dashboard_path}")
    else:
        text = dashboard_path.read_text(encoding="utf-8")
        key  = f"'{release_id}'"   # e.g. 'R-16'

        # 1. ReleaseKey type
        if key not in text or "ReleaseKey" not in text:
            errors.append(f"ReleaseKey type does not include {key}")
        else:
            # Check it appears in the type definition line
            for line in text.splitlines():
                if "ReleaseKey" in line and "type" in line and key in line:
                    break
            else:
                errors.append(f"{key} not found in ReleaseKey type union")

        # 2. RELEASES array entry
        releases_ok = False
        for line in text.splitlines():
            if f"key: {key}" in line:
                releases_ok = True
                break
        if not releases_ok:
            errors.append(f"RELEASES array has no entry with  key: {key}")

        # 3. ITERATIONS array entry
        iterations_ok = False
        for line in text.splitlines():
            if f"releaseKey: {key}" in line:
                iterations_ok = True
                break
        if not iterations_ok:
            errors.append(f"ITERATIONS array has no block with  releaseKey: {key}")

        # 4. RICEF item
        ricef_ok = False
        for line in text.splitlines():
            if f"iteration: {key}" in line:
                ricef_ok = True
                break
        if not ricef_ok:
            errors.append(f"RICEF array has no item with  iteration: {key}")

    passed = len(errors) == 0

    for e in errors:
        print(f"  ✗ {e}")
    if passed:
        print(f"  ✓ All checks passed — SDLCDashboard.tsx is up to date for {release_id}")

    # Record in state
    state.setdefault("guardrails", {})
    state["guardrails"]["dashboard_check"] = {
        "passed":    passed,
        "dashboard": str(dashboard_path),
        "errors":    errors,
        "ran_at":    _now(),
    }
    _save_state(state)

    print(_divider())
    if passed:
        print(f"  Result recorded: PASS — Gate 3 (Build) dashboard-check prerequisite satisfied.")
    else:
        print(f"  Result recorded: FAIL — Gate 3 (Build) approval is BLOCKED until this passes.")
        print(f"  Fix the issues above then re-run: python sdlc_workflow.py dashboard-check {release_id}")
    print(_divider("═"))

    sys.exit(0 if passed else 1)


def cmd_framework_sync(args: argparse.Namespace) -> None:
    """
    Register the release in the sdlc-framework and verify the sync.
    Required before Gate 5 (Deployment) can be approved.

    Steps:
      1. GET /api/v1/releases — look for a release with release_ref == release_id
      2. If absent, GET /api/v1/projects — pick first project (or create one)
      3. POST /api/v1/releases to create the release entry
      4. Re-check and confirm it exists
    """
    import urllib.request
    import urllib.error

    state      = _load_state(args.release_id)
    release_id = state["release_id"]
    base_url   = (args.url or "http://localhost:8002").rstrip("/")

    print(_divider("═"))
    print(f"  NOC Platform — Framework Sync  [{release_id}]")
    print(f"  Target : {base_url}")
    print(_divider())

    errors: list[str] = []
    synced_id: str | None = None

    def _api_get(path: str):
        url = f"{base_url}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())

    def _api_post(path: str, payload: dict):
        url  = f"{base_url}{path}"
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())

    try:
        # Step 1 — check if release already exists
        releases = _api_get("/api/v1/releases")
        existing = next(
            (r for r in releases if r.get("release_ref") == release_id),
            None
        )

        if existing:
            synced_id = existing.get("id") or existing.get("release_ref")
            print(f"  ✓ Release {release_id} already registered (id={synced_id})")
        else:
            print(f"  Release {release_id} not found — registering now...")

            # Step 2 — find or create project
            projects = _api_get("/api/v1/projects")
            if projects:
                project_id = projects[0]["id"]
                print(f"  Using project: {projects[0].get('name','?')} (id={project_id})")
            else:
                proj = _api_post("/api/v1/projects", {
                    "name":        "NOC Platform",
                    "description": "Agentic NOC ticket resolution platform",
                    "methodology": "agile",
                })
                project_id = proj["id"]
                print(f"  Created project: NOC Platform (id={project_id})")

            # Step 3 — create the release
            rel = _api_post("/api/v1/releases", {
                "project_id":   project_id,
                "release_ref":  release_id,
                "name":         state.get("release_name", release_id),
            })
            synced_id = rel.get("id") or rel.get("release_ref")
            print(f"  ✓ Release {release_id} registered (id={synced_id})")

        # Step 4 — re-verify
        releases2 = _api_get("/api/v1/releases")
        confirmed = any(r.get("release_ref") == release_id for r in releases2)
        if not confirmed:
            errors.append(f"POST succeeded but {release_id} not visible in GET /api/v1/releases")

    except urllib.error.URLError as exc:
        errors.append(
            f"Could not reach sdlc-framework at {base_url}: {exc}\n"
            f"  Ensure the sdlc-framework backend is running:  python -m uvicorn app.main:app --port 8002"
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Unexpected error: {exc}")

    passed = len(errors) == 0

    for e in errors:
        print(f"  ✗ {e}")

    # Record in state
    state.setdefault("guardrails", {})
    state["guardrails"]["framework_sync"] = {
        "passed":      passed,
        "base_url":    base_url,
        "synced_id":   synced_id,
        "errors":      errors,
        "ran_at":      _now(),
    }
    _save_state(state)

    print(_divider())
    if passed:
        print(f"  Result recorded: PASS — Gate 5 (Deployment) framework-sync prerequisite satisfied.")
    else:
        print(f"  Result recorded: FAIL — Gate 5 (Deployment) approval is BLOCKED until this passes.")
        print(f"  Fix the issues above then re-run: python sdlc_workflow.py framework-sync {release_id}")
    print(_divider("═"))

    sys.exit(0 if passed else 1)


def cmd_list(args: argparse.Namespace) -> None:
    if not RELEASES_DIR.exists() or not any(RELEASES_DIR.iterdir()):
        print("No releases initialised yet.")
        print(f"  python sdlc_workflow.py init R-15 \"My Feature\"")
        return

    print(_divider("═"))
    print("  NOC Platform — All Releases")
    print(_divider())
    print(f"  {'ID':<8} {'Name':<30} {'Phase':<28} {'Created'}")
    print(_divider())

    for release_dir in sorted(RELEASES_DIR.iterdir()):
        sp = release_dir / "state.json"
        if not sp.exists():
            continue
        state  = json.loads(sp.read_text(encoding="utf-8"))
        phase  = _current_phase(state)
        phase_label = "COMPLETE" if phase == "complete" else GATE_META[phase]["label"]
        print(
            f"  {state['release_id']:<8} {state['release_name']:<30} "
            f"{phase_label:<28} {state['created_at'][:10]}"
        )

    print(_divider("═"))


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sdlc_workflow.py",
        description="NOC Platform SDLC gate enforcement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  init            R-15 "Feature Name"            Initialise a new release
  status          R-15                           Full gate status report
  submit          R-15 <gate> <path.md>          Validate and register a deliverable
  approve         R-15 <gate> --role X --name Y  Record gate approval
  check           R-15 <gate>                    Check whether a gate is cleared
  list                                           List all tracked releases
  data-check      R-15 [--db <path>]             Run data quality pre-flight (Gate 2 prerequisite)
  scan            R-15 <file1> [file2 ...]       Run static code scan (Gate 3 prerequisite)
  lessons-check   R-15 [--dashboard <path>]      Run lessons-learned check (Gate 5 prerequisite)

Gates (in order):
  requirements  hld  build  testing  deployment

Gate prerequisites (guardrails):
  Gate 2 (hld)        — data-check must PASS before approve is accepted
  Gate 3 (build)      — scan must PASS (no ERRORs) before approve is accepted
  Gate 5 (deployment) — lessons-check must PASS before approve is accepted
        """,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialise a new release")
    p_init.add_argument("release_id",   help="e.g. R-15")
    p_init.add_argument("release_name", help='e.g. "Alarm Trend Chart"')

    # status
    p_status = sub.add_parser("status", help="Show full SDLC gate status")
    p_status.add_argument("release_id")

    # submit
    p_submit = sub.add_parser("submit", help="Validate and register a deliverable file")
    p_submit.add_argument("release_id")
    p_submit.add_argument("gate", choices=GATES)
    p_submit.add_argument("deliverable_path", metavar="path.md")

    # approve
    p_approve = sub.add_parser("approve", help="Record gate approval")
    p_approve.add_argument("release_id")
    p_approve.add_argument("gate", choices=GATES)
    p_approve.add_argument("--role", required=True,
                           choices=sorted(VALID_ROLES),
                           metavar="ROLE",
                           help=f"One of: {', '.join(sorted(VALID_ROLES))}")
    p_approve.add_argument("--name", required=True, metavar="NAME",
                           help="Approver's full name")

    # check
    p_check = sub.add_parser("check", help="Check whether a gate is cleared")
    p_check.add_argument("release_id")
    p_check.add_argument("gate", choices=GATES)

    # list
    sub.add_parser("list", help="List all tracked releases")

    # data-check
    p_dc = sub.add_parser(
        "data-check",
        help="Run data quality pre-flight check (Gate 2 / HLD prerequisite)",
    )
    p_dc.add_argument("release_id")
    p_dc.add_argument("--db",      default=None,            help="Path to SQLite DB (default: data/tickets.db)")
    p_dc.add_argument("--table",   default="telco_tickets",  help="Table to check (default: telco_tickets)")
    p_dc.add_argument("--columns", nargs="+",                help="Columns to check for NULL/cardinality issues")

    # scan
    p_scan = sub.add_parser(
        "scan",
        help="Run static code scan against source files (Gate 3 / Build prerequisite)",
    )
    p_scan.add_argument("release_id")
    p_scan.add_argument("files", nargs="*", metavar="file",
                        help="Source files to scan (.py, .ts, .tsx)")

    # lessons-check
    p_lc = sub.add_parser(
        "lessons-check",
        help="Run lessons-learned completeness check (Gate 5 / Deployment prerequisite)",
    )
    p_lc.add_argument("release_id")
    p_lc.add_argument("--dashboard", default=None,
                      help="Path to SDLCDashboard.tsx (default: frontend/src/pages/SDLCDashboard.tsx)")
    p_lc.add_argument("--md", default=None,
                      help="Path to lessons-learned.md (default: releases/<ID>/docs/lessons-learned.md)")
    p_lc.add_argument("--min-entries", type=int, default=None,
                      help="Minimum LESSONS_LEARNED entries required (default: 1)")

    # dashboard-check
    p_dbc = sub.add_parser(
        "dashboard-check",
        help="Verify SDLCDashboard.tsx is updated with new release (Gate 3 / Build prerequisite)",
    )
    p_dbc.add_argument("release_id")
    p_dbc.add_argument("--dashboard", default=None,
                       help="Path to SDLCDashboard.tsx (default: frontend/src/pages/SDLCDashboard.tsx)")

    # framework-sync
    p_fs = sub.add_parser(
        "framework-sync",
        help="Register release in sdlc-framework and verify sync (Gate 5 / Deployment prerequisite)",
    )
    p_fs.add_argument("release_id")
    p_fs.add_argument("--url", default="http://localhost:8002",
                      help="sdlc-framework base URL (default: http://localhost:8002)")

    return p


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    dispatch = {
        "init":             cmd_init,
        "status":           cmd_status,
        "submit":           cmd_submit,
        "approve":          cmd_approve,
        "check":            cmd_check,
        "list":             cmd_list,
        "data-check":       cmd_data_check,
        "scan":             cmd_scan,
        "lessons-check":    cmd_lessons_check,
        "dashboard-check":  cmd_dashboard_check,
        "framework-sync":   cmd_framework_sync,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
