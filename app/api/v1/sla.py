"""
app/api/v1/sla.py — SLA Tracking endpoints (R-15)

Exposes:
  GET  /sla/summary              — overall + per-fault compliance stats
  GET  /sla/targets              — list all SLA target configurations
  PUT  /sla/targets/{fault_type} — update target hours for one fault type
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/sla", tags=["SLA"])

DB_PATH = "data/tickets.db"

# ---------------------------------------------------------------------------
# Default SLA targets — seeded on first startup
# ---------------------------------------------------------------------------

DEFAULT_TARGETS: list[tuple[str, int, str]] = [
    ("node_down",                   4,  "Complete node outage"),
    ("signal_loss",                 8,  "Partial signal degradation"),
    ("latency",                     6,  "Network latency spike"),
    ("packet_loss",                 6,  "Packet loss event"),
    ("congestion",                  8,  "Network congestion"),
    ("hardware_failure",            12, "Physical hardware fault"),
    ("configuration_error",         6,  "Config or firmware issue"),
    ("unknown",                     24, "Unclassified fault"),
    # Additional fault types present in live ticket data
    ("sync_reference_quality",      8,  "Sync reference quality alarm"),
    ("sw_error",                    6,  "Software error"),
    ("resource_activation_timeout", 6,  "Resource activation timeout"),
    ("service_unavailable",         4,  "Service unavailable"),
]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SLAFaultSummary(BaseModel):
    fault_type: str
    target_hours: int
    description: str
    total_resolved: int
    within_sla: int
    breached: int
    compliance_rate: float        # percentage 0–100
    avg_resolution_hours: float


class SLASummaryResponse(BaseModel):
    total_resolved: int
    within_sla: int
    breached: int
    compliance_rate: float
    avg_resolution_hours: float
    by_fault_type: list[SLAFaultSummary]


class SLATarget(BaseModel):
    fault_type: str
    target_hours: int
    description: str
    updated_at: str


class SLATargetsResponse(BaseModel):
    targets: list[SLATarget]


class SLATargetUpdateRequest(BaseModel):
    target_hours: int
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def ensure_sla_table() -> None:
    """Create sla_targets table and seed defaults if needed (idempotent)."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sla_targets (
                fault_type    TEXT PRIMARY KEY,
                target_hours  INTEGER NOT NULL,
                description   TEXT    NOT NULL DEFAULT '',
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            )
            """
        )
        for fault_type, hours, desc in DEFAULT_TARGETS:
            await db.execute(
                """
                INSERT OR IGNORE INTO sla_targets
                    (fault_type, target_hours, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fault_type, hours, desc, now, now),
            )
        await db.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=SLASummaryResponse)
async def get_sla_summary() -> SLASummaryResponse:
    """
    Compute SLA compliance across all resolved/closed tickets.

    Breach: elapsed hours (updated_at − created_at) > sla_targets.target_hours.
    Only tickets with status IN ('resolved', 'closed') are included.
    """
    await ensure_sla_table()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Per-fault-type breakdown
        async with db.execute(
            """
            SELECT
                t.fault_type,
                COALESCE(s.target_hours, 24)  AS target_hours,
                COALESCE(s.description, '')   AS description,
                COUNT(*)                       AS total_resolved,
                SUM(
                    CASE WHEN
                        (JULIANDAY(t.updated_at) - JULIANDAY(t.created_at)) * 24
                        <= COALESCE(s.target_hours, 24)
                    THEN 1 ELSE 0 END
                ) AS within_sla,
                SUM(
                    CASE WHEN
                        (JULIANDAY(t.updated_at) - JULIANDAY(t.created_at)) * 24
                        > COALESCE(s.target_hours, 24)
                    THEN 1 ELSE 0 END
                ) AS breached,
                AVG(
                    (JULIANDAY(t.updated_at) - JULIANDAY(t.created_at)) * 24
                ) AS avg_resolution_hours
            FROM telco_tickets t
            LEFT JOIN sla_targets s ON t.fault_type = s.fault_type
            WHERE t.status IN ('resolved', 'closed')
              AND t.created_at  IS NOT NULL
              AND t.updated_at  IS NOT NULL
              AND t.fault_type  IS NOT NULL
              AND t.fault_type  != ''
            GROUP BY t.fault_type, s.target_hours, s.description
            ORDER BY breached DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()

    by_fault: list[SLAFaultSummary] = []
    total_resolved = 0
    total_within   = 0
    total_breached = 0
    total_hours    = 0.0

    for r in rows:
        resolved  = r["total_resolved"] or 0
        within    = r["within_sla"]     or 0
        breached  = r["breached"]       or 0
        avg_h     = round(float(r["avg_resolution_hours"] or 0), 2)
        comp_rate = round((within / resolved * 100) if resolved else 0.0, 1)

        by_fault.append(
            SLAFaultSummary(
                fault_type=r["fault_type"],
                target_hours=r["target_hours"],
                description=r["description"],
                total_resolved=resolved,
                within_sla=within,
                breached=breached,
                compliance_rate=comp_rate,
                avg_resolution_hours=avg_h,
            )
        )
        total_resolved += resolved
        total_within   += within
        total_breached += breached
        total_hours    += avg_h * resolved

    overall_rate  = round((total_within / total_resolved * 100) if total_resolved else 0.0, 1)
    overall_avg_h = round((total_hours / total_resolved) if total_resolved else 0.0, 2)

    return SLASummaryResponse(
        total_resolved=total_resolved,
        within_sla=total_within,
        breached=total_breached,
        compliance_rate=overall_rate,
        avg_resolution_hours=overall_avg_h,
        by_fault_type=by_fault,
    )


@router.get("/targets", response_model=SLATargetsResponse)
async def get_sla_targets() -> SLATargetsResponse:
    """Return all SLA target configurations."""
    await ensure_sla_table()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT fault_type, target_hours, description, updated_at FROM sla_targets ORDER BY fault_type"
        ) as cursor:
            rows = await cursor.fetchall()

    return SLATargetsResponse(
        targets=[
            SLATarget(
                fault_type=r["fault_type"],
                target_hours=r["target_hours"],
                description=r["description"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
    )


@router.put("/targets/{fault_type}", response_model=SLATarget)
async def update_sla_target(
    fault_type: str,
    payload: SLATargetUpdateRequest,
) -> SLATarget:
    """Update the target_hours (and optionally description) for one fault type."""
    await ensure_sla_table()

    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Check row exists
        async with db.execute(
            "SELECT fault_type FROM sla_targets WHERE fault_type = ?", (fault_type,)
        ) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail=f"SLA target not found for fault_type '{fault_type}'. "
                           f"Valid types: {[t[0] for t in DEFAULT_TARGETS]}",
                )

        if payload.description is not None:
            await db.execute(
                """
                UPDATE sla_targets
                   SET target_hours = ?, description = ?, updated_at = ?
                 WHERE fault_type = ?
                """,
                (payload.target_hours, payload.description, now, fault_type),
            )
        else:
            await db.execute(
                """
                UPDATE sla_targets
                   SET target_hours = ?, updated_at = ?
                 WHERE fault_type = ?
                """,
                (payload.target_hours, now, fault_type),
            )
        await db.commit()

        async with db.execute(
            "SELECT fault_type, target_hours, description, updated_at FROM sla_targets WHERE fault_type = ?",
            (fault_type,),
        ) as cursor:
            row = await cursor.fetchone()

    return SLATarget(
        fault_type=row["fault_type"],
        target_hours=row["target_hours"],
        description=row["description"],
        updated_at=row["updated_at"],
    )
