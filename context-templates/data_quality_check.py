#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_quality_check.py - NOC Platform data pre-flight checker (Gate 2 guardrail)

Interrogates the live SQLite database and flags data-quality issues that would
produce misleading or empty results for computation-heavy features (SLA metrics,
trend charts, network graphs, geocoded maps).

Must PASS before Gate 2 (HLD) can be approved for any release whose HLD
references columns in `telco_tickets`, `dispatch_records`, or new tables.

Usage:
    python data_quality_check.py [--db PATH] [--table TABLE] [--columns COL [COL ...]]
    python data_quality_check.py
    python data_quality_check.py --db data/tickets.db --table telco_tickets
    python data_quality_check.py --db data/tickets.db --table telco_tickets \\
        --columns created_at updated_at fault_type status location_details

Exit codes:  0 = all clear   1 = issues found   2 = usage / DB error
"""

from __future__ import annotations

import argparse
import sqlite3
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

DEFAULT_DB_PATH = "data/tickets.db"

# Primary table and columns to check when none are specified
PRIMARY_TABLE = "telco_tickets"

# Columns checked for pair-equality (bulk-load indicator)
TIMESTAMP_PAIRS: list[tuple[str, str]] = [
    ("created_at", "updated_at"),
]

# Columns checked for high NULL / empty-string rates
COMPUTATION_COLUMNS: list[str] = [
    "fault_type",
    "status",
    "created_at",
    "updated_at",
    "location_details",
    "network_type",
    "priority",
]

# Thresholds
NULL_RATE_ERROR_THRESHOLD    = 0.80   # >80% NULL/empty → ERROR
NULL_RATE_WARNING_THRESHOLD  = 0.30   # >30% NULL/empty → WARNING
PAIR_EQUAL_ERROR_THRESHOLD   = 0.95   # >95% identical pairs → ERROR
PAIR_EQUAL_WARNING_THRESHOLD = 0.50   # >50% identical pairs → WARNING
MIN_ROWS_WARNING             = 10     # fewer rows than this → WARNING
CARDINALITY_WARNING_RATIO    = 0.001  # distinct/total < 0.1% → suspicious (for text cols)


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------

SEVERITY_ERROR   = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO    = "INFO"


@dataclass
class DQIssue:
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
# Checks
# ---------------------------------------------------------------------------

def check_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def get_column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def check_row_count(conn: sqlite3.Connection, table: str) -> list[DQIssue]:
    issues: list[DQIssue] = []
    (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()

    if count == 0:
        issues.append(DQIssue(
            severity=SEVERITY_ERROR,
            check="ROW-COUNT",
            message=f"Table `{table}` has 0 rows.",
            detail=(
                "A table with no data cannot be used to compute metrics, charts, or SLA stats.\n"
                "Seed the table with representative data before locking the HLD design."
            ),
        ))
    elif count < MIN_ROWS_WARNING:
        issues.append(DQIssue(
            severity=SEVERITY_WARNING,
            check="ROW-COUNT",
            message=f"Table `{table}` has only {count} row(s) — sample size too small.",
            detail=(
                f"Less than {MIN_ROWS_WARNING} rows may produce misleading aggregates.\n"
                "Ensure the DB is loaded with representative production data."
            ),
        ))
    else:
        issues.append(DQIssue(
            severity=SEVERITY_INFO,
            check="ROW-COUNT",
            message=f"Table `{table}` has {count:,} rows — adequate sample size.",
        ))

    return issues


def check_null_rates(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
) -> list[DQIssue]:
    """Check NULL and empty-string rates for each specified column."""
    issues: list[DQIssue] = []
    (total,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if total == 0:
        return issues

    existing_cols = get_column_names(conn, table)

    for col in columns:
        if col not in existing_cols:
            issues.append(DQIssue(
                severity=SEVERITY_WARNING,
                check="NULL-RATE",
                message=f"Column `{col}` does not exist in `{table}` — skipped.",
            ))
            continue

        (null_count,) = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL OR TRIM(CAST({col} AS TEXT)) = ''"
        ).fetchone()

        rate = null_count / total

        if rate > NULL_RATE_ERROR_THRESHOLD:
            issues.append(DQIssue(
                severity=SEVERITY_ERROR,
                check="NULL-RATE",
                message=(
                    f"`{table}.{col}` is NULL/empty in {rate:.1%} of rows "
                    f"({null_count:,}/{total:,})."
                ),
                detail=(
                    f"A column with >{NULL_RATE_ERROR_THRESHOLD:.0%} missing values cannot "
                    f"reliably drive computations or visualisations.\n"
                    f"Investigate the data load pipeline — was this column populated correctly?"
                ),
            ))
        elif rate > NULL_RATE_WARNING_THRESHOLD:
            issues.append(DQIssue(
                severity=SEVERITY_WARNING,
                check="NULL-RATE",
                message=(
                    f"`{table}.{col}` is NULL/empty in {rate:.1%} of rows "
                    f"({null_count:,}/{total:,})."
                ),
                detail=(
                    f"Significant missing data. Confirm this is expected "
                    f"(e.g., optional field) before designing features that depend on it."
                ),
            ))

    return issues


def check_timestamp_pairs(
    conn: sqlite3.Connection,
    table: str,
    pairs: list[tuple[str, str]],
) -> list[DQIssue]:
    """
    Check whether timestamp column pairs are suspiciously identical.

    A high `created_at == updated_at` rate is a strong indicator that the table
    was bulk-loaded without ever updating rows — meaning time-elapsed computations
    (SLA hours, resolution time, trend charts) will produce 0 for every row.
    """
    issues: list[DQIssue] = []
    (total,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if total == 0:
        return issues

    existing_cols = get_column_names(conn, table)

    for col_a, col_b in pairs:
        if col_a not in existing_cols or col_b not in existing_cols:
            # Only warn if both columns exist in the table
            if col_a in existing_cols or col_b in existing_cols:
                issues.append(DQIssue(
                    severity=SEVERITY_WARNING,
                    check="TIMESTAMP-PAIR",
                    message=(
                        f"Cannot compare `{col_a}` vs `{col_b}` — one column is missing in `{table}`."
                    ),
                ))
            continue

        (equal_count,) = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col_a} = {col_b} "
            f"AND {col_a} IS NOT NULL AND {col_b} IS NOT NULL"
        ).fetchone()

        (non_null_total,) = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col_a} IS NOT NULL AND {col_b} IS NOT NULL"
        ).fetchone()

        if non_null_total == 0:
            continue

        rate = equal_count / non_null_total

        if rate > PAIR_EQUAL_ERROR_THRESHOLD:
            issues.append(DQIssue(
                severity=SEVERITY_ERROR,
                check="TIMESTAMP-PAIR",
                message=(
                    f"`{table}.{col_a}` == `{table}.{col_b}` "
                    f"in {rate:.1%} of rows ({equal_count:,}/{non_null_total:,})."
                ),
                detail=(
                    f"This is the bulk-load indicator that caused the R-15 SLA defect:\n"
                    f"  (JULIANDAY({col_b}) - JULIANDAY({col_a})) * 24  →  0 for every row.\n"
                    f"Any feature computing elapsed time (SLA hours, resolution time,\n"
                    f"trend intervals) will produce all-zero results on this dataset.\n\n"
                    f"Resolution options:\n"
                    f"  A) Re-seed `{col_b}` with realistic offsets before this release ships.\n"
                    f"  B) Redesign the metric to use a different time basis.\n"
                    f"  C) Document the limitation explicitly in the HLD and defer the feature."
                ),
            ))
        elif rate > PAIR_EQUAL_WARNING_THRESHOLD:
            issues.append(DQIssue(
                severity=SEVERITY_WARNING,
                check="TIMESTAMP-PAIR",
                message=(
                    f"`{table}.{col_a}` == `{table}.{col_b}` "
                    f"in {rate:.1%} of rows ({equal_count:,}/{non_null_total:,})."
                ),
                detail=(
                    f"More than half the rows have identical {col_a}/{col_b} values.\n"
                    f"Verify that elapsed-time computations will still be meaningful."
                ),
            ))
        else:
            issues.append(DQIssue(
                severity=SEVERITY_INFO,
                check="TIMESTAMP-PAIR",
                message=(
                    f"`{table}.{col_a}` == `{table}.{col_b}` "
                    f"in {rate:.1%} of rows — acceptable variance."
                ),
            ))

    return issues


def check_constant_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
) -> list[DQIssue]:
    """Flag columns where every non-NULL row has the same value."""
    issues: list[DQIssue] = []
    (total,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if total < 2:
        return issues

    existing_cols = get_column_names(conn, table)

    for col in columns:
        if col not in existing_cols:
            continue

        (distinct,) = conn.execute(
            f"SELECT COUNT(DISTINCT {col}) FROM {table} WHERE {col} IS NOT NULL"
        ).fetchone()

        (non_null,) = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL"
        ).fetchone()

        if non_null == 0:
            continue

        if distinct == 1:
            (single_val,) = conn.execute(
                f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL LIMIT 1"
            ).fetchone()
            issues.append(DQIssue(
                severity=SEVERITY_WARNING,
                check="CONSTANT-COLUMN",
                message=(
                    f"`{table}.{col}` has only 1 distinct non-NULL value: '{single_val}'."
                ),
                detail=(
                    f"A column with a single value cannot drive grouping, filtering, or charts.\n"
                    f"Confirm this is expected (e.g., single-environment DB) before designing "
                    f"features that group or filter by `{col}`."
                ),
            ))

    return issues


def check_enum_coverage(
    conn: sqlite3.Connection,
    table: str,
) -> list[DQIssue]:
    """
    Check known enum columns for unexpected or missing values.

    Specifically flags `status` values that are not in the expected set — which can
    cause LEFT JOINs or CASE expressions in computation queries to silently miss rows.
    """
    issues: list[DQIssue] = []
    existing_cols = get_column_names(conn, table)

    KNOWN_STATUSES = {
        "pending_review", "in_progress", "resolved", "closed",
        "pending", "open", "escalated",
    }

    if "status" in existing_cols:
        cur = conn.execute(
            f"SELECT DISTINCT status, COUNT(*) as cnt FROM {table} "
            f"WHERE status IS NOT NULL GROUP BY status ORDER BY cnt DESC"
        )
        rows = cur.fetchall()
        unknown = [(s, c) for s, c in rows if s.lower() not in KNOWN_STATUSES]
        if unknown:
            detail_lines = "\n".join(f"  '{s}' — {c:,} rows" for s, c in unknown[:10])
            issues.append(DQIssue(
                severity=SEVERITY_WARNING,
                check="ENUM-COVERAGE",
                message=(
                    f"`{table}.status` contains {len(unknown)} unrecognised value(s)."
                ),
                detail=(
                    f"These status values are not in the standard set:\n"
                    f"{detail_lines}\n"
                    f"SLA queries filter `WHERE status IN ('resolved', 'closed')` — "
                    f"other statuses are silently excluded from compliance metrics."
                ),
            ))

    return issues


def check_sla_targets_coverage(conn: sqlite3.Connection) -> list[DQIssue]:
    """
    If both `telco_tickets` and `sla_targets` exist, check that every
    `fault_type` in tickets has a matching entry in `sla_targets`.

    Missing entries fall back to COALESCE(..., 24) in SLA queries but produce
    no description and may hide gaps in the target configuration.
    """
    issues: list[DQIssue] = []

    if not check_table_exists(conn, "telco_tickets"):
        return issues
    if not check_table_exists(conn, "sla_targets"):
        return issues

    cur = conn.execute(
        """
        SELECT DISTINCT t.fault_type, COUNT(*) as cnt
        FROM telco_tickets t
        LEFT JOIN sla_targets s ON t.fault_type = s.fault_type
        WHERE t.fault_type IS NOT NULL
          AND t.fault_type != ''
          AND s.fault_type IS NULL
        GROUP BY t.fault_type
        ORDER BY cnt DESC
        """
    )
    missing = cur.fetchall()

    if missing:
        detail_lines = "\n".join(f"  '{ft}' — {cnt:,} tickets" for ft, cnt in missing[:10])
        issues.append(DQIssue(
            severity=SEVERITY_WARNING,
            check="SLA-TARGET-COVERAGE",
            message=(
                f"{len(missing)} fault type(s) in `telco_tickets` have no row in `sla_targets`."
            ),
            detail=(
                f"These fault types fall back to a 24-hour SLA target (COALESCE default):\n"
                f"{detail_lines}\n"
                f"Add them to `DEFAULT_TARGETS` in `app/api/v1/sla.py` and re-seed the table."
            ),
        ))

    return issues


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_checks(
    db_path: Path,
    table: str,
    columns: list[str] | None,
) -> tuple[list[DQIssue], int]:
    """Run all checks. Returns (all_issues, total_row_count)."""
    issues: list[DQIssue] = []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        print(f"ERROR: Cannot open database '{db_path}': {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        if not check_table_exists(conn, table):
            issues.append(DQIssue(
                severity=SEVERITY_ERROR,
                check="TABLE-EXISTS",
                message=f"Table `{table}` does not exist in `{db_path}`.",
                detail=(
                    "The table has not been created yet.\n"
                    "Start the backend with `uvicorn app.main:app --reload` so the lifespan\n"
                    "handler runs `ensure_*_table()` to create and seed all required tables."
                ),
            ))
            return issues, 0

        # Row count
        issues.extend(check_row_count(conn, table))

        (total,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if total == 0:
            return issues, 0

        # Determine columns to check
        check_cols = columns if columns else COMPUTATION_COLUMNS

        # NULL rates
        issues.extend(check_null_rates(conn, table, check_cols))

        # Timestamp pair equality (bulk-load indicator)
        if table == PRIMARY_TABLE:
            issues.extend(check_timestamp_pairs(conn, table, TIMESTAMP_PAIRS))

        # Constant columns
        issues.extend(check_constant_columns(conn, table, check_cols))

        # Enum coverage
        if table == PRIMARY_TABLE:
            issues.extend(check_enum_coverage(conn, table))

        # SLA targets cross-check
        issues.extend(check_sla_targets_coverage(conn))

        return issues, total

    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser(
        prog="data_quality_check.py",
        description=(
            "NOC Platform data pre-flight checker.\n"
            "Interrogates the SQLite database for data-quality issues that would\n"
            "produce misleading or empty results in computation-heavy features.\n\n"
            "Must PASS before Gate 2 (HLD) can be approved."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Checks performed:
  ROW-COUNT          Table must have >=10 rows for meaningful aggregation
  NULL-RATE          Key computation columns must be <30% NULL (warning) / <80% (error)
  TIMESTAMP-PAIR     created_at == updated_at rate must be <50% (warning) / <95% (error)
  CONSTANT-COLUMN    Columns with only 1 distinct value cannot drive charts or grouping
  ENUM-COVERAGE      Unrecognised status values may silently exclude rows from SLA queries
  SLA-TARGET-COVERAGE  fault_types not in sla_targets fall back to 24h default target

Examples:
  python data_quality_check.py
  python data_quality_check.py --db data/tickets.db
  python data_quality_check.py --table telco_tickets
  python data_quality_check.py --columns created_at updated_at fault_type status
        """,
    )
    p.add_argument("--db",      default=DEFAULT_DB_PATH, help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})")
    p.add_argument("--table",   default=PRIMARY_TABLE,   help=f"Table to check (default: {PRIMARY_TABLE})")
    p.add_argument("--columns", nargs="+",               help="Column(s) to include in NULL/cardinality checks (default: all known computation columns)")

    args   = p.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"ERROR: Database file not found: {db_path}", file=sys.stderr)
        print(f"  Start the backend first: uvicorn app.main:app --reload", file=sys.stderr)
        sys.exit(2)

    all_issues, row_count = run_checks(db_path, args.table, args.columns)

    errors   = [i for i in all_issues if i.severity == SEVERITY_ERROR]
    warnings = [i for i in all_issues if i.severity == SEVERITY_WARNING]
    infos    = [i for i in all_issues if i.severity == SEVERITY_INFO]

    print("=" * 62)
    print("  NOC Platform Data Quality Pre-Flight Check")
    print(f"  Database : {db_path}")
    print(f"  Table    : {args.table}  ({row_count:,} rows)")
    print(f"  Errors   : {len(errors)}")
    print(f"  Warnings : {len(warnings)}")
    print("=" * 62)

    if infos:
        print()
        for info in infos:
            print(f"  [INFO] {info.check}  {info.message}")

    if not errors and not warnings:
        print()
        print("  ALL CLEAR — data quality checks passed.")
        print("  Safe to proceed with Gate 2 (HLD) approval.")
        sys.exit(0)

    if warnings and not errors:
        print()
        print(f"WARNINGS ({len(warnings)}) — review before locking HLD:\n")
        for w in warnings:
            print(w)
            print()
        print("PASSED with warnings — no blocking data errors.")
        print("Acknowledge warnings in HLD Section 4 (Data Store Design).")
        sys.exit(0)

    if errors:
        print()
        print(f"FAILED — {len(errors)} blocking data issue(s) must be resolved:\n")
        for e in errors:
            print(e)
            print()
        if warnings:
            print(f"Additionally, {len(warnings)} warning(s):")
            for w in warnings:
                print(w)
                print()
        print("Resolve all ERRORs above, then re-run before submitting to Gate 2.")
        sys.exit(1)


if __name__ == "__main__":
    main()
