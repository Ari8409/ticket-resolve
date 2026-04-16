#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_scan.py - NOC Platform static code analyser (Gate 3 guardrail)

Scans Python and TypeScript source files for known anti-patterns that
document review cannot catch.  Must PASS before Gate 3 (Build Complete)
can be approved.

Usage:
    python code_scan.py <file1> [file2 ...]
    python code_scan.py app/api/v1/sla.py frontend/src/components/SLAWidget.tsx

Exit codes:  0 = all clear   1 = issues found   2 = usage error
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------

SEVERITY_ERROR   = "ERROR"
SEVERITY_WARNING = "WARNING"


@dataclass
class Issue:
    severity: str
    file: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"  [{self.severity}] {self.file}:{self.line}  {self.rule}\n           {self.message}"


# ---------------------------------------------------------------------------
# Python checks
# ---------------------------------------------------------------------------

ROUTER_ON_EVENT_RE = re.compile(
    r"@\w*router\w*\.on_event\s*\(",
    re.IGNORECASE,
)

SQL_FSTRING_RE = re.compile(
    r'f["\'].*?(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER).*?\{',
    re.IGNORECASE | re.DOTALL,
)

SQL_CONCAT_RE = re.compile(
    r'(SELECT|INSERT|UPDATE|DELETE)\s*["\']\s*\+',
    re.IGNORECASE,
)

ENSURE_TABLE_IN_ENDPOINT_RE = re.compile(
    r"@router\.(get|post|put|delete|patch)\b",
)

AWAIT_MISSING_RE = re.compile(
    r"(?<!await )(aiosqlite\.connect|db\.execute|cursor\.fetchone|cursor\.fetchall)\(",
)


def check_python(path: Path) -> list[Issue]:
    issues: list[Issue] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # ── Rule PY-001: APIRouter.on_event anti-pattern ──────────────────
        if ROUTER_ON_EVENT_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_ERROR,
                file=str(path),
                line=i,
                rule="PY-001",
                message=(
                    "`@router.on_event()` has no effect on APIRouter — "
                    "startup/shutdown hooks only fire on the main FastAPI app. "
                    "Move initialisation to `app/main.py` lifespan handler."
                ),
            ))

        # ── Rule PY-002: SQL f-string injection risk ───────────────────────
        if SQL_FSTRING_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_ERROR,
                file=str(path),
                line=i,
                rule="PY-002",
                message=(
                    "SQL query built with an f-string — SQL injection risk. "
                    "Use parameterised queries with `?` placeholders and a "
                    "separate params tuple passed to `db.execute()`."
                ),
            ))

        # ── Rule PY-003: SQL string concatenation ─────────────────────────
        if SQL_CONCAT_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_ERROR,
                file=str(path),
                line=i,
                rule="PY-003",
                message=(
                    "SQL query built via string concatenation (`+`) — injection risk. "
                    "Use parameterised `?` placeholders."
                ),
            ))

        # ── Rule PY-004: ensure_table() called inside endpoint ────────────
        # If we see both a router decorator and ensure_*_table in the same
        # function, flag it as a warning — prefer lifespan-time init.
        if ENSURE_TABLE_IN_ENDPOINT_RE.search(line):
            # Scan the next 15 lines for ensure_*_table call
            snippet = "\n".join(lines[i : i + 15])
            if re.search(r"ensure_\w+_table\s*\(", snippet):
                issues.append(Issue(
                    severity=SEVERITY_WARNING,
                    file=str(path),
                    line=i,
                    rule="PY-004",
                    message=(
                        "`ensure_*_table()` called inside an endpoint handler. "
                        "This adds per-request overhead. Move to `app/main.py` "
                        "lifespan so it runs once at startup."
                    ),
                ))

        # ── Rule PY-005: await missing on known async DB calls ────────────
        # Exclude `async with` context manager lines — those don't need `await`
        # on the same line (e.g. `async with aiosqlite.connect(...) as db:`).
        if (
            AWAIT_MISSING_RE.search(stripped)
            and not stripped.startswith("#")
            and "async with" not in stripped
        ):
            issues.append(Issue(
                severity=SEVERITY_ERROR,
                file=str(path),
                line=i,
                rule="PY-005",
                message=(
                    "Async DB call without `await` — this returns a coroutine "
                    "object instead of executing the query, silently producing "
                    "no results."
                ),
            ))

    # ── Rule PY-006: new router file not registered in router.py ──────────
    repo_root = _find_repo_root(path)
    if repo_root and "app/api/v1" in str(path).replace("\\", "/"):
        router_py = repo_root / "app" / "api" / "v1" / "router.py"
        if router_py.exists() and path.stem != "router" and path.stem != "__init__":
            router_text = router_py.read_text(encoding="utf-8", errors="replace")
            if f"import {path.stem}" not in router_text and \
               f", {path.stem}" not in router_text:
                issues.append(Issue(
                    severity=SEVERITY_ERROR,
                    file=str(path),
                    line=1,
                    rule="PY-006",
                    message=(
                        f"Module `{path.stem}` appears to be a new API router but "
                        f"is not imported or registered in `app/api/v1/router.py`. "
                        f"Add `from app.api.v1 import {path.stem}` and "
                        f"`v1_router.include_router({path.stem}.router)`."
                    ),
                ))

    # ── Rule PY-007: ensure_*_table not wired into main.py lifespan ───────
    if re.search(r"async def ensure_\w+_table", text):
        if repo_root:
            main_py = repo_root / "app" / "main.py"
            if main_py.exists():
                main_text = main_py.read_text(encoding="utf-8", errors="replace")
                fn_names = re.findall(r"async def (ensure_\w+_table)", text)
                for fn in fn_names:
                    if fn not in main_text:
                        issues.append(Issue(
                            severity=SEVERITY_ERROR,
                            file=str(path),
                            line=1,
                            rule="PY-007",
                            message=(
                                f"`{fn}()` is defined but NOT called in "
                                f"`app/main.py` lifespan handler. "
                                f"The table will never be created on startup — "
                                f"add `await {fn}()` to the lifespan context manager."
                            ),
                        ))

    return issues


# ---------------------------------------------------------------------------
# TypeScript checks
# ---------------------------------------------------------------------------

TS_FILL_RE = re.compile(r"\[FILL(?::[^\]]*)?\]")

TS_QUERY_KEY_RE = re.compile(
    r"useQuery\s*\(\s*\{[^}]*queryKey\s*:\s*['\"]",
    re.DOTALL,
)

TS_ANY_CAST_RE = re.compile(r"\bas\s+any\b")

TS_CONSOLE_LOG_RE = re.compile(r"\bconsole\.log\s*\(")

TS_HARDCODED_URL_RE = re.compile(
    r'(fetch|axios\.get|axios\.post)\s*\(\s*["\']https?://',
    re.IGNORECASE,
)

TS_MISSING_ERROR_HANDLER = re.compile(
    r"useQuery\s*\(\s*\{",
    re.DOTALL,
)


def check_typescript(path: Path) -> list[Issue]:
    issues: list[Issue] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue

        # ── Rule TS-001: unfilled placeholder in source file ──────────────
        if TS_FILL_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_ERROR,
                file=str(path),
                line=i,
                rule="TS-001",
                message=(
                    f"Unfilled `[FILL]` placeholder found in source file. "
                    f"Template placeholders must not appear in production code."
                ),
            ))

        # ── Rule TS-002: queryKey as string instead of array ──────────────
        if TS_QUERY_KEY_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_ERROR,
                file=str(path),
                line=i,
                rule="TS-002",
                message=(
                    "React Query `queryKey` must be an array `['key']`, not a "
                    "plain string `'key'`. String keys bypass cache deduplication."
                ),
            ))

        # ── Rule TS-003: console.log left in production code ──────────────
        if TS_CONSOLE_LOG_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_WARNING,
                file=str(path),
                line=i,
                rule="TS-003",
                message=(
                    "`console.log` left in source file. "
                    "Remove debug logging before marking build complete."
                ),
            ))

        # ── Rule TS-004: hardcoded absolute URL ───────────────────────────
        if TS_HARDCODED_URL_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_ERROR,
                file=str(path),
                line=i,
                rule="TS-004",
                message=(
                    "Hardcoded absolute URL found. Use `apiClient` from "
                    "`frontend/src/api/client.ts` so the base URL is "
                    "resolved from `VITE_API_BASE` env var."
                ),
            ))

        # ── Rule TS-005: `as any` type cast ───────────────────────────────
        if TS_ANY_CAST_RE.search(line):
            issues.append(Issue(
                severity=SEVERITY_WARNING,
                file=str(path),
                line=i,
                rule="TS-005",
                message=(
                    "`as any` cast disables TypeScript safety. "
                    "Define a proper interface or use `unknown` with a type guard."
                ),
            ))

    # ── Rule TS-006: useQuery without error state rendering ───────────────
    if TS_MISSING_ERROR_HANDLER.search(text):
        if "isError" not in text and "error" not in text.lower():
            issues.append(Issue(
                severity=SEVERITY_WARNING,
                file=str(path),
                line=1,
                rule="TS-006",
                message=(
                    "`useQuery` is used but no `isError` / `error` branch found. "
                    "All widgets must handle the error state to avoid blank panels "
                    "when the backend is unavailable."
                ),
            ))

    return issues


# ---------------------------------------------------------------------------
# Repo root helper
# ---------------------------------------------------------------------------

def _find_repo_root(start: Path) -> Path | None:
    for parent in [start, *start.parents]:
        if (parent / "app" / "main.py").exists():
            return parent
    return None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

PYTHON_EXTENSIONS = {".py"}
TS_EXTENSIONS = {".ts", ".tsx"}


def scan_file(path: Path) -> list[Issue]:
    if path.suffix in PYTHON_EXTENSIONS:
        return check_python(path)
    if path.suffix in TS_EXTENSIONS:
        return check_typescript(path)
    return []


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python code_scan.py <file1> [file2 ...]")
        print()
        print("Scans Python (.py) and TypeScript (.ts/.tsx) files for known")
        print("anti-patterns that document review cannot detect.")
        print()
        print("Rules checked:")
        print("  PY-001  APIRouter.on_event anti-pattern")
        print("  PY-002  SQL f-string injection risk")
        print("  PY-003  SQL string concatenation risk")
        print("  PY-004  ensure_*_table() called per-request instead of at startup")
        print("  PY-005  await missing on async DB calls")
        print("  PY-006  Router file not registered in router.py")
        print("  PY-007  ensure_*_table() not wired into main.py lifespan")
        print("  TS-001  [FILL] placeholder in source file")
        print("  TS-002  queryKey as string instead of array")
        print("  TS-003  console.log left in code")
        print("  TS-004  Hardcoded absolute URL")
        print("  TS-005  `as any` type cast")
        print("  TS-006  useQuery without error state handler")
        sys.exit(2)

    files = [Path(p) for p in sys.argv[1:]]
    missing = [f for f in files if not f.exists()]
    if missing:
        for f in missing:
            print(f"ERROR: File not found: {f}", file=sys.stderr)
        sys.exit(2)

    all_issues: list[Issue] = []
    for f in files:
        all_issues.extend(scan_file(f))

    errors   = [i for i in all_issues if i.severity == SEVERITY_ERROR]
    warnings = [i for i in all_issues if i.severity == SEVERITY_WARNING]

    print("=" * 62)
    print("  NOC Platform Code Scanner")
    print(f"  Files scanned : {len(files)}")
    print(f"  Errors        : {len(errors)}")
    print(f"  Warnings      : {len(warnings)}")
    print("=" * 62)

    if not all_issues:
        print("  ALL CLEAR — no issues found. Safe to submit for Gate 3.")
        sys.exit(0)

    if warnings and not errors:
        print()
        print(f"WARNINGS ({len(warnings)}) — review before proceeding:\n")
        for w in warnings:
            print(w)
        print()
        print("PASSED with warnings — no blocking errors.")
        sys.exit(0)

    if errors:
        print()
        print(f"FAILED — {len(errors)} blocking error(s) must be fixed:\n")
        for e in errors:
            print(e)
            print()
        if warnings:
            print(f"Additionally, {len(warnings)} warning(s):")
            for w in warnings:
                print(w)
                print()
        print("Fix all ERRORs above, then re-run before submitting to Gate 3.")
        sys.exit(1)


if __name__ == "__main__":
    main()
