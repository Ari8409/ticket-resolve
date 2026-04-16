#!/usr/bin/env python3
"""
validate_prompt.py — NOC Platform prompt template guardrail

Usage:
    python validate_prompt.py <path-to-filled-prompt.md>

Exit codes:
    0  — prompt is valid, safe to execute
    1  — validation failed; list of issues printed to stdout
    2  — usage error (wrong arguments or file not found)

The validator:
  1. Detects which template type the file matches (enhancement or deliverable)
     based on its first H1 heading.
  2. Checks that every [FILL] / [FILL: hint] placeholder has been replaced
     with real content.
  3. Checks that all required section headings for the detected template type
     are present.
  4. Checks that the Document Metadata block (releases, RICEF ID, dates) is
     fully filled.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Template definitions — required H2/H3 headings per template type
# ---------------------------------------------------------------------------

ENHANCEMENT_SECTIONS = [
    "1. Platform Context",
    "2. Feature Description",
    "3. Data Source",
    "4. Component Breakdown",
    "5. RICEF Classification",
    "6. Acceptance Criteria",
    "7. Integration Points",
    "8. Testing Requirements",
]

DELIVERABLE_SECTIONS_COMMON = [
    "Document Metadata",
    "Platform Reference",
]

DELIVERABLE_SECTIONS: dict[str, list[str]] = {
    "requirements": [
        "1. Business Objective",
        "2. Stakeholders",
        "3. Functional Requirements",
        "4. Non-Functional Requirements",
        "5. Assumptions & Constraints",
        "6. Out of Scope",
        "7. Acceptance Criteria",
        "8. Dependencies",
    ],
    "hld": [
        "1. Architecture Overview",
        "2. Component Inventory",
        "3. API Contract Summary",
        "4. Data Store Design",
        "5. External Integrations",
        "6. Security Considerations",
        "7. Technology Decisions",
    ],
    "lld": [
        "1. Module Breakdown",
        "2. Database Schema DDL",
        "3. Pydantic Models",
        "4. React Component Tree",
        "5. React Query Keys & Cache Strategy",
        "6. State Transitions",
        "7. Error Handling Matrix",
    ],
    "tdd": [
        "1. Test Scope",
        "2. Test Environment",
        "3. Unit-Level Test Cases",
        "4. Integration Test Cases",
        "5. Edge Cases",
        "6. Performance Benchmarks",
        "7. Test Data",
    ],
    "ut-report": [
        "1. Test Execution Summary",
        "2. Pass Rate",
        "3. Failures & Root Causes",
        "4. Coverage Notes",
        "5. Sign-off",
    ],
    "sit-report": [
        "1. Integration Scenarios Tested",
        "2. Test Execution Results",
        "3. Defects Found",
        "4. Regression Check",
        "5. Environment Details",
        "6. Sign-off",
    ],
    "deployment": [
        "1. Pre-Deployment Checklist",
        "2. Deployment Steps",
        "3. Configuration Changes",
        "4. Database Changes",
        "5. Rollback Procedure",
        "6. Smoke Test After Deploy",
        "7. Monitoring Points",
    ],
    "rai-compliance": [
        "1. AI Component Inventory",
        "2. Data Privacy Assessment",
        "3. Bias & Fairness",
        "4. Explainability",
        "5. Human Oversight",
        "6. Failure Modes",
        "7. Audit Trail",
        "8. Responsible AI Checklist",
    ],
    "accessibility": [
        "1. Scope",
        "2. Standard",
        "3. Keyboard Navigation",
        "4. Screen Reader",
        "5. Colour Contrast",
        "6. Responsive Design",
        "7. Motion & Animation",
        "8. Issues & Remediation",
    ],
}

# Metadata fields that must not contain [FILL]
REQUIRED_METADATA_FIELDS = ["Release", "RICEF ID", "RICEF Type", "Author", "Date", "Version", "Status"]

# Regex patterns
FILL_PATTERN = re.compile(r"\[FILL(?::[^\]]*)?\]")
HEADING_PATTERN = re.compile(r"^#{1,4}\s+(.+)$", re.MULTILINE)
RICEF_ID_PATTERN = re.compile(r"R-\d+")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class TemplateType(NamedTuple):
    category: str        # "enhancement" | "deliverable"
    subtype: str | None  # e.g. "frontend", "requirements", None


def detect_template_type(text: str) -> TemplateType | None:
    """Determine which template this file was filled from."""
    # Extract first H1
    h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if not h1_match:
        return None
    title = h1_match.group(1).lower()

    # Enhancement types — detected by first-line keyword
    if "frontend enhancement" in title:
        return TemplateType("enhancement", "frontend")
    if "database enhancement" in title:
        return TemplateType("enhancement", "database")
    if "integration" in title and ("api" in title or "enhancement" in title):
        return TemplateType("enhancement", "integration")

    # Deliverable types — detected by keyword in first H1
    deliverable_keywords = {
        "requirements document": "requirements",
        "high-level design": "hld",
        "low-level design": "lld",
        "test design document": "tdd",
        "unit test report": "ut-report",
        "system integration test report": "sit-report",
        "deployment document": "deployment",
        "responsible ai compliance": "rai-compliance",
        "accessibility compliance": "accessibility",
    }
    for keyword, subtype in deliverable_keywords.items():
        if keyword in title:
            return TemplateType("deliverable", subtype)

    return None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def find_unfilled_placeholders(text: str) -> list[tuple[int, str]]:
    """Return (line_number, line_text) for every line still containing [FILL...]."""
    results = []
    for i, line in enumerate(text.splitlines(), start=1):
        # Skip comment lines (HTML comments are guidance notes, not real content)
        stripped = line.strip()
        if stripped.startswith("<!--") or stripped.endswith("-->"):
            continue
        if FILL_PATTERN.search(line):
            results.append((i, line.rstrip()))
    return results


def find_missing_sections(text: str, required: list[str]) -> list[str]:
    """Return section titles that are absent from the document."""
    headings_found = {m.group(1).strip() for m in HEADING_PATTERN.finditer(text)}
    missing = []
    for section in required:
        # Match if the section title appears as a substring of any heading (tolerant)
        if not any(section.lower() in h.lower() for h in headings_found):
            missing.append(section)
    return missing


def check_metadata(text: str) -> list[str]:
    """Return metadata field names that still contain [FILL] or are missing."""
    problems = []
    for field in REQUIRED_METADATA_FIELDS:
        # Look for the metadata table row: | Field | Value |
        pattern = re.compile(rf"\|\s*{re.escape(field)}\s*\|\s*(.+?)\s*\|", re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            problems.append(f"Metadata field '{field}' not found")
        elif FILL_PATTERN.search(match.group(1)):
            problems.append(f"Metadata field '{field}' is not filled in (still contains placeholder)")
    return problems


def check_ricef_id(text: str) -> list[str]:
    """Warn if RICEF ID field does not match R-<number> format."""
    problems = []
    ricef_row = re.search(r"\|\s*RICEF ID\s*\|\s*(.+?)\s*\|", text, re.IGNORECASE)
    if ricef_row:
        value = ricef_row.group(1).strip()
        if not RICEF_ID_PATTERN.fullmatch(value):
            problems.append(
                f"RICEF ID value '{value}' does not match expected format R-<number> (e.g. R-15)"
            )
    return problems


# ---------------------------------------------------------------------------
# Main validation orchestration
# ---------------------------------------------------------------------------

class ValidationResult(NamedTuple):
    passed: bool
    template_type: TemplateType | None
    errors: list[str]
    warnings: list[str]


def validate(text: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Detect template type
    ttype = detect_template_type(text)
    if ttype is None:
        errors.append(
            "Could not identify template type from H1 heading. "
            "Ensure the document starts with a heading matching one of the official templates "
            "(e.g. '# Frontend Enhancement Request — My Feature')."
        )
        return ValidationResult(False, None, errors, warnings)

    # 2. Check for unfilled placeholders
    unfilled = find_unfilled_placeholders(text)
    if unfilled:
        errors.append(
            f"{len(unfilled)} unfilled placeholder(s) found — "
            "replace every [FILL] with actual content before executing:"
        )
        for lineno, line in unfilled[:20]:  # cap output at 20 lines
            errors.append(f"  Line {lineno:4d}: {line[:100]}")
        if len(unfilled) > 20:
            errors.append(f"  ... and {len(unfilled) - 20} more")

    # 3. Check required sections
    if ttype.category == "enhancement":
        missing = find_missing_sections(text, ENHANCEMENT_SECTIONS)
    else:
        specific = DELIVERABLE_SECTIONS.get(ttype.subtype or "", [])
        required = DELIVERABLE_SECTIONS_COMMON + specific
        missing = find_missing_sections(text, required)

    if missing:
        errors.append(f"{len(missing)} required section(s) missing:")
        for s in missing:
            errors.append(f"  - {s}")

    # 4. Check metadata completeness (deliverables only — enhancements don't have a metadata table)
    if ttype.category == "deliverable":
        meta_errors = check_metadata(text)
        errors.extend(meta_errors)
        ricef_errors = check_ricef_id(text)
        warnings.extend(ricef_errors)

    # 5. Enhancement-specific: check RICEF ID in the classification section
    if ttype.category == "enhancement":
        ricef_section = re.search(
            r"## 5\. RICEF Classification.*?(?=\n## |\Z)", text, re.DOTALL
        )
        if ricef_section:
            section_text = ricef_section.group(0)
            id_match = re.search(r"\*\*RICEF ID:\*\*\s*(.+)", section_text)
            if id_match:
                value = id_match.group(1).strip()
                if not RICEF_ID_PATTERN.search(value):
                    warnings.append(
                        f"RICEF ID in section 5 ('{value}') doesn't look like R-<number>"
                    )

    passed = len(errors) == 0
    return ValidationResult(passed, ttype, errors, warnings)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _type_label(ttype: TemplateType) -> str:
    if ttype.category == "enhancement":
        return f"Enhancement / {ttype.subtype}"
    return f"Deliverable / {ttype.subtype}"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python validate_prompt.py <path-to-filled-prompt.md>")
        print()
        print("Example:")
        print("  python validate_prompt.py my-release-15-frontend.md")
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(2)
    if path.suffix.lower() != ".md":
        print(f"WARNING: Expected a .md file, got '{path.suffix}' — proceeding anyway.")

    text = path.read_text(encoding="utf-8")
    result = validate(text)

    print("=" * 60)
    print(f"NOC Platform Prompt Validator")
    print(f"File   : {path}")

    if result.template_type:
        print(f"Type   : {_type_label(result.template_type)}")

    print("=" * 60)

    if result.passed and not result.warnings:
        print("PASSED — prompt adheres to template. Safe to execute.")
        sys.exit(0)

    if result.warnings:
        print(f"\nWARNINGS ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"  ! {w}")

    if not result.passed:
        print(f"\nFAILED — {len(result.errors)} error(s) must be fixed before executing:\n")
        for e in result.errors:
            print(f"  {e}")
        print()
        print("Fix the issues above, then re-run this validator before proceeding.")
        sys.exit(1)

    # Passed with warnings
    print("\nPASSED with warnings — review the warnings above before executing.")
    sys.exit(0)


if __name__ == "__main__":
    main()
