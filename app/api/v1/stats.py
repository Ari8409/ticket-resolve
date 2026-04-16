"""
Dashboard statistics endpoint.

GET /api/v1/stats
    Returns ticket counts by status.  Used by the NOC React dashboard for
    the summary cards (Total Tickets, Open, Escalated to Human).

GET /api/v1/telco-tickets
    Paginated list of all telco tickets with optional status filter.
    Used by the dashboard recent-tickets table and chat context lookups.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_telco_repo
from app.storage.telco_repositories import TelcoTicketRepository

router = APIRouter(tags=["dashboard"])

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "tickets.db")


# ---------------------------------------------------------------------------
# Stats summary
# ---------------------------------------------------------------------------

@router.get(
    "/stats",
    summary="Ticket counts by status for NOC dashboard",
    response_model=dict,
)
async def get_stats(
    repo: Annotated[TelcoTicketRepository, Depends(get_telco_repo)],
):
    """
    Return aggregate ticket counts for the NOC dashboard summary cards.

    Response fields:
    - **total**          — all tickets in the database
    - **open**           — OPEN + ASSIGNED + IN_PROGRESS combined
    - **in_progress**    — IN_PROGRESS only
    - **pending_review** — awaiting human triage (HITL queue)
    - **resolved**       — successfully closed by pipeline or engineer
    - **escalated**      — escalated to senior NOC / vendor
    - **closed**         — administratively closed
    - **failed**         — pipeline errors requiring attention
    - **by_status**      — raw counts per status key
    - **by_fault_type**  — ticket counts grouped by fault_type
    - **by_alarm**       — top 15 alarm_name counts
    - **by_network**     — ticket counts grouped by network_type
    """
    return await repo.get_stats()


# ---------------------------------------------------------------------------
# Dispatch stats (remote vs field resolution)
# ---------------------------------------------------------------------------

@router.get(
    "/dispatch-stats",
    summary="Remote vs field dispatch breakdown from dispatch decisions",
    response_model=dict,
)
async def get_dispatch_stats():
    """
    Return resolution mode stats from telco_dispatch_decisions.

    Response fields:
    - **remote**       — count of tickets resolved remotely
    - **on_site**      — count of tickets requiring field dispatch
    - **hold**         — count of tickets on hold (pending review)
    - **total**        — total dispatch decision records
    - **remote_pct**   — remote as % of remote+on_site (resolved only)
    - **on_site_pct**  — on_site as % of remote+on_site (resolved only)
    - **remote_avg_confidence** — avg confidence score for remote decisions
    - **on_site_avg_confidence** — avg confidence score for on_site decisions
    - **by_fault_type** — dispatch mode breakdown per fault_type
    - **by_network**    — dispatch mode breakdown per network_type
    """
    db = sqlite3.connect(os.path.normpath(_DB_PATH))
    db.row_factory = sqlite3.Row

    # Mode counts + avg confidence
    mode_rows = db.execute("""
        SELECT dispatch_mode,
               COUNT(*) AS cnt,
               ROUND(AVG(confidence_score), 3) AS avg_conf
        FROM telco_dispatch_decisions
        GROUP BY dispatch_mode
    """).fetchall()

    counts = {r["dispatch_mode"]: r["cnt"] for r in mode_rows}
    confs  = {r["dispatch_mode"]: r["avg_conf"] for r in mode_rows}

    remote  = counts.get("remote",  0)
    on_site = counts.get("on_site", 0)
    hold    = counts.get("hold",    0)
    total   = remote + on_site + hold
    resolved_total = remote + on_site

    # Fault-type breakdown: remote vs on_site counts per fault_type
    ft_rows = db.execute("""
        SELECT t.fault_type, d.dispatch_mode, COUNT(*) AS cnt
        FROM telco_dispatch_decisions d
        JOIN telco_tickets t ON t.ticket_id = d.ticket_id
        WHERE d.dispatch_mode IN ('remote', 'on_site')
        GROUP BY t.fault_type, d.dispatch_mode
        ORDER BY t.fault_type
    """).fetchall()

    by_fault: dict = {}
    for r in ft_rows:
        ft = r["fault_type"]
        if ft not in by_fault:
            by_fault[ft] = {"remote": 0, "on_site": 0}
        by_fault[ft][r["dispatch_mode"]] = r["cnt"]

    # Network-type breakdown
    net_rows = db.execute("""
        SELECT t.network_type, d.dispatch_mode, COUNT(*) AS cnt
        FROM telco_dispatch_decisions d
        JOIN telco_tickets t ON t.ticket_id = d.ticket_id
        WHERE d.dispatch_mode IN ('remote', 'on_site')
          AND t.network_type IS NOT NULL
        GROUP BY t.network_type, d.dispatch_mode
        ORDER BY t.network_type
    """).fetchall()

    by_network: dict = {}
    for r in net_rows:
        nt = r["network_type"]
        if nt not in by_network:
            by_network[nt] = {"remote": 0, "on_site": 0}
        by_network[nt][r["dispatch_mode"]] = r["cnt"]

    db.close()

    return {
        "remote":  remote,
        "on_site": on_site,
        "hold":    hold,
        "total":   total,
        "remote_pct":  round(remote  / resolved_total * 100, 1) if resolved_total else 0,
        "on_site_pct": round(on_site / resolved_total * 100, 1) if resolved_total else 0,
        "remote_avg_confidence":  confs.get("remote",  0.0),
        "on_site_avg_confidence": confs.get("on_site", 0.0),
        "by_fault_type": by_fault,
        "by_network":    by_network,
    }


# ---------------------------------------------------------------------------
# Paginated ticket list
# ---------------------------------------------------------------------------

@router.get(
    "/telco-tickets",
    summary="List telco tickets with optional status filter",
    response_model=dict,
)
async def list_telco_tickets(
    repo: Annotated[TelcoTicketRepository, Depends(get_telco_repo)],
    status: Optional[str] = Query(
        default=None,
        description=(
            "Filter by status. One of: open, assigned, in_progress, pending_review, "
            "resolved, escalated, closed, failed"
        ),
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Results per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    """
    Return a paginated list of telco tickets.

    Used by the NOC dashboard recent-tickets table.  Each ticket row includes
    the key fields needed for display: ticket_id, affected_node, fault_type,
    severity, status, alarm_name, network_type, created_at, assigned_to.

    Returns:
        tickets — list of ticket dicts
        total   — total matching count (for pagination controls)
        limit   — echoed page size
        offset  — echoed offset
    """
    rows, total = await repo.list_tickets(status=status, limit=limit, offset=offset)

    # Serialise enum values so FastAPI can JSON-encode them
    serialised = []
    for r in rows:
        serialised.append({
            "ticket_id":     r["ticket_id"],
            "affected_node": r["affected_node"],
            "fault_type":    str(r["fault_type"].value if hasattr(r["fault_type"], "value") else r["fault_type"]),
            "severity":      str(r["severity"].value if hasattr(r["severity"], "value") else r["severity"]),
            "status":        str(r["status"].value if hasattr(r["status"], "value") else r["status"]),
            "network_type":  r.get("network_type"),
            "alarm_name":    r.get("alarm_name"),
            "alarm_category": r.get("alarm_category"),
            "location_details": r.get("location_details"),
            "location_id":      r.get("location_id"),
            "description":   r["description"][:200],
            "assigned_to":   r.get("assigned_to"),
            "sop_id":        r.get("sop_id"),
            "primary_cause": r.get("primary_cause"),
            "pending_review_reasons": r.get("pending_review_reasons", []),
            "created_at":    r["created_at"].isoformat() if r.get("created_at") else None,
            "updated_at":    r["updated_at"].isoformat() if r.get("updated_at") else None,
        })

    return {
        "tickets": serialised,
        "total":   total,
        "limit":   limit,
        "offset":  offset,
    }
