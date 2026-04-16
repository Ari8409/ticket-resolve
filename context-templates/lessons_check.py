#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lessons_check.py - NOC Platform Lessons Learned completeness checker (Gate 5 guardrail)

Verifies that the SDLC dashboard has been updated with at least one LESSONS_LEARNED
entry for the release being deployed, AND that a lessons-learned.md deliverable exists
and has been filled.

A release cannot be declared "done" without a post-mortem.  Skipping lessons learned
is exactly how the R-15 defects (silent @router.on_event, bulk-load timestamp issue)
propagated undetected through all 5 gates.

Usage:
    python lessons_check.py R-15
    python lessons_check.py R-15 --dashboard frontend/src/pages/SDLCDashboard.tsx
    python lessons_check.py R-15 --md path/to/lessons-learned.md
    python lessons_check.py R-15 --min-entries 2

Exit codes:  0 = all clear   1 = issues found   2 = usage / file error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DASHBOARD = "frontend/src/pages/SDLCDashboard.tsx"
DEFAULT_MIN_ENTRIES = 1

# Pattern that matches an entry with the release iteration tag:
#   iteration: 'R-15'   or   iteration: "R-15"
ITERATION_FIELD_RE = re.compile(
    r"iteration\s*:\s*['\"]({release})['\"]"
)

# Alternative: title starting with the release tag (legacy entries)
#   title: 'R-15: ...'   or   'R-15: ...'
TITLE_TAG_RE = re.compile(
    r"['\"]({release})\s*:"
)

# Detect unfilled [FILL] placeholders (same as validate_prompt.py)
FILL_RE = re.compile(r"\[FILL(?::[^\]]*)?\]")

# Required sections in lessons-learned.md
REQUIRED_SECTIONS = [
    "Document Metadata",
    "Lessons Learned",
    "Root Cause",
    "Fix Applied",
]


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------

SEVERITY_ERROR   = "ERROR"
SEVERITY_WARNING = "WARNING"


@dataclass
class Issue:
    severity: str
    check: str
    message: str
    detail: str = ""

    def __str__(self) -> str:
        lines = [f"  [{self.severity}] {self.check}\n           {self.message}"]
        if self.detail:
            for line in self.detail.splitlines():
                lines.append(f"           {line}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Check 1: LESSONS_LEARNED entries in SDLCDashboard.tsx
# ---------------------------------------------------------------------------

def check_dashboard_entries(
    dashboard_path: Path,
    release_id: str,
    min_entries: int,
) -> list[Issue]:
    issues: list[Issue] = []

    if not dashboard_path.exists():
        issues.append(Issue(
            severity=SEVERITY_WARNING,
            check="DASHBOARD-EXISTS",
            message=f"SDLCDashboard.tsx not found at '{dashboard_path}' — skipping dashboard check.",
            detail=(
                "Pass --dashboard with the correct path to enable this check.\n"
                "Alternatively, run from the repo root so the default path resolves."
            ),
        ))
        return issues

    text = dashboard_path.read_text(encoding="utf-8", errors="replace")

    # Check that LESSONS_LEARNED array exists at all
    if "LESSONS_LEARNED" not in text:
        issues.append(Issue(
            severity=SEVERITY_ERROR,
            check="LESSONS-ARRAY",
            message="LESSONS_LEARNED constant not found in SDLCDashboard.tsx.",
            detail=(
                "The dashboard component must contain a LESSONS_LEARNED array.\n"
                "See context-templates/deliverables/lessons-learned.md for the format."
            ),
        ))
        return issues

    # Count entries matching the release
    iter_pattern = ITERATION_FIELD_RE.pattern.replace("{release}", re.escape(release_id))
    title_pattern = TITLE_TAG_RE.pattern.replace("{release}", re.escape(release_id))

    iter_matches  = len(re.findall(iter_pattern, text))
    title_matches = len(re.findall(title_pattern, text))
    total_matches = iter_matches + title_matches

    if total_matches == 0:
        issues.append(Issue(
            severity=SEVERITY_ERROR,
            check="LESSONS-ENTRIES",
            message=(
                f"No LESSONS_LEARNED entries found for release '{release_id}' "
                f"in SDLCDashboard.tsx."
            ),
            detail=(
                f"Add at least {min_entries} entry(ies) to the LESSONS_LEARNED array with:\n"
                f"  iteration: '{release_id}',\n\n"
                f"Required fields per entry:\n"
                f"  severity: 'High' | 'Medium' | 'Low'\n"
                f"  area: string          (e.g. 'FastAPI / Architecture')\n"
                f"  title: string         (e.g. '{release_id}: Short description of defect')\n"
                f"  problem: string       (what went wrong and why it wasn't caught earlier)\n"
                f"  fix: string           (what was changed + what guardrail now prevents recurrence)\n"
                f"  iteration: '{release_id}'  (required for all releases R-14 onwards)\n\n"
                f"Each entry should be inside the LESSONS_LEARNED array in SDLCDashboard.tsx,\n"
                f"grouped under a // ── {release_id} ─── comment."
            ),
        ))
    elif total_matches < min_entries:
        issues.append(Issue(
            severity=SEVERITY_WARNING,
            check="LESSONS-ENTRIES",
            message=(
                f"Only {total_matches} LESSONS_LEARNED entr{'y' if total_matches==1 else 'ies'} "
                f"found for '{release_id}' — minimum required is {min_entries}."
            ),
            detail=(
                f"Add more entries to reach the minimum of {min_entries}.\n"
                f"Each significant defect, near-miss, or process gap encountered during\n"
                f"'{release_id}' should have its own entry."
            ),
        ))
    else:
        issues.append(Issue(
            severity="INFO",
            check="LESSONS-ENTRIES",
            message=(
                f"{total_matches} LESSONS_LEARNED entr{'y' if total_matches==1 else 'ies'} "
                f"found for '{release_id}' — minimum {min_entries} satisfied."
            ),
        ))

    return issues


# ---------------------------------------------------------------------------
# Check 2: lessons-learned.md deliverable
# ---------------------------------------------------------------------------

def check_lessons_md(
    md_path: Path | None,
    release_id: str,
) -> list[Issue]:
    issues: list[Issue] = []

    if md_path is None:
        # Try to find it in the standard release directory
        script_dir = Path(__file__).parent
        candidate = script_dir / "releases" / release_id.upper() / "docs" / "lessons-learned.md"
        if candidate.exists():
            md_path = candidate
        else:
            issues.append(Issue(
                severity=SEVERITY_WARNING,
                check="LESSONS-MD",
                message=(
                    f"lessons-learned.md not found in releases/{release_id.upper()}/docs/."
                ),
                detail=(
                    f"Fill in context-templates/deliverables/lessons-learned.md and submit it:\n"
                    f"  python sdlc_workflow.py submit {release_id} deployment "
                    f"path/to/lessons-learned.md\n\n"
                    f"Or pass --md <path> to specify a different location."
                ),
            ))
            return issues

    if not md_path.exists():
        issues.append(Issue(
            severity=SEVERITY_ERROR,
            check="LESSONS-MD",
            message=f"lessons-learned.md not found at '{md_path}'.",
            detail=(
                f"Fill in context-templates/deliverables/lessons-learned.md,\n"
                f"then submit as a Gate 5 deliverable:\n"
                f"  python sdlc_workflow.py submit {release_id} deployment <path>"
            ),
        ))
        return issues

    text = md_path.read_text(encoding="utf-8", errors="replace")

    # Check for unfilled placeholders
    unfilled = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("<!--") or stripped.endswith("-->"):
            continue
        if FILL_RE.search(line):
            unfilled.append((i, line.rstrip()))

    if unfilled:
        issues.append(Issue(
            severity=SEVERITY_ERROR,
            check="LESSONS-MD-FILL",
            message=f"lessons-learned.md has {len(unfilled)} unfilled [FILL] placeholder(s).",
            detail="\n".join(
                f"  Line {ln:4d}: {txt[:100]}"
                for ln, txt in unfilled[:8]
            ) + (f"\n  ... and {len(unfilled)-8} more" if len(unfilled) > 8 else ""),
        ))

    # Check required sections
    headings = {m.group(1).strip().lower() for m in re.finditer(r"^#{1,4}\s+(.+)$", text, re.MULTILINE)}
    missing = [s for s in REQUIRED_SECTIONS if not any(s.lower() in h for h in headings)]
    if missing:
        issues.append(Issue(
            severity=SEVERITY_ERROR,
            check="LESSONS-MD-SECTIONS",
            message=f"lessons-learned.md is missing {len(missing)} required section(s).",
            detail="\n".join(f"  - {s}" for s in missing),
        ))

    if not unfilled and not missing:
        issues.append(Issue(
            severity="INFO",
            check="LESSONS-MD",
            message=f"lessons-learned.md validated — no placeholders, all sections present.",
        ))

    return issues


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        prog="lessons_check.py",
        description=(
            "NOC Platform Lessons Learned completeness checker.\n"
            "Verifies that at least one LESSONS_LEARNED entry exists in SDLCDashboard.tsx\n"
            "for the release being deployed, and that lessons-learned.md is filled.\n\n"
            "Must PASS before Gate 5 (Deployment) can be approved."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Checks performed:
  LESSONS-ARRAY     LESSONS_LEARNED constant must exist in SDLCDashboard.tsx
  LESSONS-ENTRIES   At least --min-entries entries with iteration: 'R-xx' must be present
  LESSONS-MD        lessons-learned.md must exist in the release docs directory
  LESSONS-MD-FILL   lessons-learned.md must have no [FILL] placeholders remaining
  LESSONS-MD-SECTIONS  lessons-learned.md must contain all required sections

Examples:
  python lessons_check.py R-15
  python lessons_check.py R-15 --min-entries 2
  python lessons_check.py R-15 --dashboard ../frontend/src/pages/SDLCDashboard.tsx
  python lessons_check.py R-15 --md releases/R-15/docs/lessons-learned.md
        """,
    )
    p.add_argument("release_id",       help="Release ID to check (e.g. R-15)")
    p.add_argument("--dashboard",      default=None, help=f"Path to SDLCDashboard.tsx (default: repo root relative)")
    p.add_argument("--md",             default=None, help="Path to lessons-learned.md (default: releases/<ID>/docs/lessons-learned.md)")
    p.add_argument("--min-entries",    type=int, default=DEFAULT_MIN_ENTRIES, help=f"Minimum LESSONS_LEARNED entries required (default: {DEFAULT_MIN_ENTRIES})")

    args       = p.parse_args()
    release_id = args.release_id.upper()

    # Resolve dashboard path
    script_dir     = Path(__file__).parent
    repo_root      = script_dir.parent
    dashboard_path = Path(args.dashboard) if args.dashboard else (repo_root / DEFAULT_DASHBOARD)
    md_path        = Path(args.md) if args.md else None

    all_issues = []
    all_issues.extend(check_dashboard_entries(dashboard_path, release_id, args.min_entries))
    all_issues.extend(check_lessons_md(md_path, release_id))

    errors   = [i for i in all_issues if i.severity == SEVERITY_ERROR]
    warnings = [i for i in all_issues if i.severity == SEVERITY_WARNING]
    infos    = [i for i in all_issues if i.severity == "INFO"]

    print("=" * 62)
    print("  NOC Platform Lessons Learned Check")
    print(f"  Release  : {release_id}")
    print(f"  Dashboard: {dashboard_path}")
    print(f"  Errors   : {len(errors)}")
    print(f"  Warnings : {len(warnings)}")
    print("=" * 62)

    if infos:
        print()
        for info in infos:
            print(f"  [INFO] {info.check}  {info.message}")

    if not errors and not warnings:
        print()
        print("  ALL CLEAR — Lessons Learned check passed.")
        print("  Gate 5 (Deployment) lessons-learned prerequisite satisfied.")
        sys.exit(0)

    if warnings and not errors:
        print()
        print(f"WARNINGS ({len(warnings)}) — review before Gate 5 approval:\n")
        for w in warnings:
            print(w)
            print()
        print("PASSED with warnings — no blocking errors.")
        sys.exit(0)

    if errors:
        print()
        print(f"FAILED — {len(errors)} blocking issue(s) must be resolved:\n")
        for e in errors:
            print(e)
            print()
        if warnings:
            print(f"Additionally, {len(warnings)} warning(s):")
            for w in warnings:
                print(w)
                print()
        print("Resolve all ERRORs above, then re-run before submitting to Gate 5.")
        sys.exit(1)


if __name__ == "__main__":
    main()
