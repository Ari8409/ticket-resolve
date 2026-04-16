"""
Network topology API endpoints.

GET  /network/graph   — returns pre-computed nodes (with positions + ticket stats) and edges
POST /network/refresh — re-runs build_network_graph.py to refresh topology from ticket data
"""

import os
import sqlite3
import subprocess
import sys

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/network", tags=["network"])

# Resolve DB path relative to project root (one level up from app/)
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "tickets.db")
_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "build_network_graph.py")


def _get_db():
    path = os.path.abspath(_DB_PATH)
    if not os.path.exists(path):
        raise HTTPException(status_code=503, detail=f"Database not found at {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/graph")
async def get_network_graph():
    """
    Returns pre-computed network topology.

    Response shape:
    {
      "nodes": [ { node_id, network_type, node_class, parent_node,
                   x_pos, y_pos, ticket_count, pending_count, open_count, resolved_count,
                   last_ticket_at } ],
      "edges": [ { edge_id, source_node, target_node, edge_type } ],
      "summary": { total_nodes, nodes_with_pending, nodes_with_issues }
    }
    """
    db = _get_db()
    try:
        # Check tables exist
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "network_nodes" not in tables:
            raise HTTPException(
                status_code=503,
                detail="Network topology not built yet. POST /network/refresh to generate it.",
            )

        nodes = db.execute("SELECT * FROM network_nodes").fetchall()
        edges = db.execute("SELECT * FROM network_edges").fetchall()

        node_list = [dict(n) for n in nodes]
        edge_list = [dict(e) for e in edges]

        return {
            "nodes": node_list,
            "edges": edge_list,
            "summary": {
                "total_nodes": len(node_list),
                "nodes_with_pending": sum(1 for n in node_list if (n["pending_count"] or 0) > 0),
                "nodes_with_issues": sum(1 for n in node_list if (n["open_count"] or 0) > 0),
                "total_edges": len(edge_list),
            },
        }
    finally:
        db.close()


@router.get("/node/{node_id}/tickets")
async def get_node_tickets(node_id: str, limit: int = 5):
    """
    Returns the most recent tickets for a specific network node.
    Used by the topology drill-down panel.
    """
    db = _get_db()
    try:
        rows = db.execute(
            """
            SELECT ticket_id, alarm_name, fault_type, severity, status, created_at, network_type
            FROM telco_tickets
            WHERE affected_node = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (node_id, limit),
        ).fetchall()
        return {"node_id": node_id, "tickets": [dict(r) for r in rows]}
    finally:
        db.close()


@router.post("/refresh")
async def refresh_network_graph():
    """
    Triggers re-computation of the network topology from current ticket data.
    Runs scripts/build_network_graph.py synchronously and returns status.
    """
    script = os.path.abspath(_SCRIPT_PATH)
    if not os.path.exists(script):
        raise HTTPException(status_code=500, detail=f"Build script not found at {script}")

    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Build script failed:\n{result.stderr}",
        )
    return {"status": "refreshed", "output": result.stdout}
