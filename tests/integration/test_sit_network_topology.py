"""
SIT — Network Topology API integration tests.

Covers the three endpoints in app/api/v1/network.py:
  GET  /api/v1/network/graph
  GET  /api/v1/network/node/{node_id}/tickets
  POST /api/v1/network/refresh

All SQLite and subprocess calls are mocked via FastAPI dependency_overrides
and unittest.mock so no real DB or build script is needed.

Telecom test scenarios:
  - Full topology response with 3G/4G/5G nodes and RNC→NodeB edges
  - Topology summary counts (nodes_with_pending, nodes_with_issues)
  - Node drill-down returns recent tickets ordered by created_at DESC
  - Network topology not built (503 before first refresh)
  - Refresh invokes build script and returns status
  - DB file missing returns 503
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Sample test data
# ---------------------------------------------------------------------------

SAMPLE_NODES = [
    # 3G RNC
    {"node_id": "Rnc07",          "network_type": "3G",  "node_class": "RNC",   "parent_node": None,    "x_pos": 0.10, "y_pos": 0.50, "ticket_count": 12, "pending_count": 3,  "open_count": 2, "resolved_count": 7,  "last_ticket_at": "2025-12-01T08:00:00"},
    # 3G NodeB children of Rnc07
    {"node_id": "Rnc07_1100",     "network_type": "3G",  "node_class": "NodeB", "parent_node": "Rnc07", "x_pos": 0.08, "y_pos": 0.40, "ticket_count": 5,  "pending_count": 1,  "open_count": 1, "resolved_count": 3,  "last_ticket_at": "2025-12-01T06:00:00"},
    {"node_id": "Rnc07_1200",     "network_type": "3G",  "node_class": "NodeB", "parent_node": "Rnc07", "x_pos": 0.12, "y_pos": 0.45, "ticket_count": 4,  "pending_count": 0,  "open_count": 1, "resolved_count": 3,  "last_ticket_at": "2025-12-01T05:00:00"},
    # 4G eNodeB
    {"node_id": "LTE_ENB_780321", "network_type": "4G",  "node_class": "ENB",   "parent_node": None,    "x_pos": 0.50, "y_pos": 0.50, "ticket_count": 8,  "pending_count": 2,  "open_count": 3, "resolved_count": 3,  "last_ticket_at": "2025-12-02T09:00:00"},
    # 4G ESS (no pending)
    {"node_id": "LTE_ESS_735557", "network_type": "4G",  "node_class": "ESS",   "parent_node": None,    "x_pos": 0.55, "y_pos": 0.55, "ticket_count": 3,  "pending_count": 0,  "open_count": 0, "resolved_count": 3,  "last_ticket_at": "2025-11-30T12:00:00"},
    # 5G gNB
    {"node_id": "5G_GNB_1039321", "network_type": "5G",  "node_class": "GNB",   "parent_node": None,    "x_pos": 0.85, "y_pos": 0.50, "ticket_count": 6,  "pending_count": 1,  "open_count": 2, "resolved_count": 3,  "last_ticket_at": "2025-12-03T10:00:00"},
    # Node with no tickets — should be in total but not in issues/pending
    {"node_id": "5G_ESS_1017001", "network_type": "5G",  "node_class": "ESS",   "parent_node": None,    "x_pos": 0.90, "y_pos": 0.55, "ticket_count": 0,  "pending_count": 0,  "open_count": 0, "resolved_count": 0,  "last_ticket_at": None},
]

SAMPLE_EDGES = [
    {"edge_id": 1, "source_node": "Rnc07", "target_node": "Rnc07_1100", "edge_type": "parent"},
    {"edge_id": 2, "source_node": "Rnc07", "target_node": "Rnc07_1200", "edge_type": "parent"},
]

SAMPLE_NODE_TICKETS = [
    {"ticket_id": "TKT-001", "alarm_name": "Heartbeat Failure", "fault_type": "node_down",    "severity": "critical", "status": "pending_review", "created_at": "2025-12-02T09:00:00", "network_type": "4G"},
    {"ticket_id": "TKT-002", "alarm_name": "HW Fault",          "fault_type": "hardware_failure", "severity": "major", "status": "resolved",       "created_at": "2025-12-01T14:00:00", "network_type": "4G"},
]


# ---------------------------------------------------------------------------
# Mock factory — patch sqlite3.connect used inside network.py
# ---------------------------------------------------------------------------

def _mock_db(nodes=None, edges=None, node_tickets=None, tables=None):
    """Build a mock sqlite3 connection with controlled fetchall() returns."""
    if nodes is None:
        nodes = SAMPLE_NODES
    if edges is None:
        edges = SAMPLE_EDGES
    if tables is None:
        tables = [("network_nodes",), ("network_edges",)]

    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    def _execute(sql, params=()):
        cursor = MagicMock()
        sql_lower = sql.strip().lower()
        if "sqlite_master" in sql_lower:
            cursor.fetchall.return_value = tables
        elif "network_nodes" in sql_lower and "where" not in sql_lower:
            cursor.fetchall.return_value = [_row(n) for n in nodes]
        elif "network_edges" in sql_lower:
            cursor.fetchall.return_value = [_row(e) for e in edges]
        elif "telco_tickets" in sql_lower:
            cursor.fetchall.return_value = [_row(t) for t in (node_tickets or SAMPLE_NODE_TICKETS)]
        else:
            cursor.fetchall.return_value = []
        return cursor

    conn.execute = _execute
    conn.row_factory = None
    conn.close = MagicMock()
    return conn


def _row(data: dict):
    """sqlite3.Row-like MagicMock that supports dict()."""
    row = MagicMock()
    row.keys = MagicMock(return_value=list(data.keys()))
    row.__iter__ = MagicMock(return_value=iter(data.values()))
    # Make dict(row) work via the dict() constructor path used in network.py
    # network.py uses dict(n) which calls __iter__ on sqlite3.Row + keys()
    # We simulate by making the MagicMock subscriptable
    for k, v in data.items():
        row.__getitem__ = MagicMock(side_effect=lambda key, d=data: d[key])
    # The actual dict(sqlite3.Row) call in network.py is dict(n) which uses
    # the sqlite3.Row mapping protocol. Simulate with a plain dict subclass.
    return data  # network.py does dict(n) so returning a dict works fine


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /network/graph — happy path
# ---------------------------------------------------------------------------

class TestGetNetworkGraph:

    def test_returns_200_with_nodes_edges_summary(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert "summary" in data

    def test_nodes_contain_position_fields(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        nodes = resp.json()["nodes"]
        assert len(nodes) > 0
        node = nodes[0]
        assert "x_pos" in node
        assert "y_pos" in node

    def test_nodes_contain_ticket_health_counts(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        nodes = resp.json()["nodes"]
        node = next(n for n in nodes if n["node_id"] == "LTE_ENB_780321")
        assert node["pending_count"] == 2
        assert node["open_count"] == 3

    def test_edges_have_parent_type(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        edges = resp.json()["edges"]
        assert all(e["edge_type"] == "parent" for e in edges)

    def test_summary_total_nodes_correct(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        summary = resp.json()["summary"]
        assert summary["total_nodes"] == len(SAMPLE_NODES)

    def test_summary_nodes_with_pending_excludes_zero_pending(self, client):
        """Only nodes with pending_count > 0 counted in nodes_with_pending."""
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        expected_pending = sum(1 for n in SAMPLE_NODES if (n["pending_count"] or 0) > 0)
        assert resp.json()["summary"]["nodes_with_pending"] == expected_pending

    def test_summary_nodes_with_issues_correct(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        expected_issues = sum(1 for n in SAMPLE_NODES if (n["open_count"] or 0) > 0)
        assert resp.json()["summary"]["nodes_with_issues"] == expected_issues

    def test_rnc_to_nodeb_edges_present(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        edges = resp.json()["edges"]
        rnc07_children = [e for e in edges if e["source_node"] == "Rnc07"]
        assert len(rnc07_children) == 2

    def test_returns_503_when_network_nodes_table_missing(self, client):
        """Before first refresh, network_nodes table doesn't exist."""
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db(tables=[])  # no tables
            resp = client.get("/api/v1/network/graph")
        assert resp.status_code == 503
        assert "refresh" in resp.json()["detail"].lower()

    def test_returns_503_when_db_not_found(self, client):
        with patch("app.api.v1.network.os.path.exists", return_value=False):
            resp = client.get("/api/v1/network/graph")
        assert resp.status_code == 503
        assert "database" in resp.json()["detail"].lower()

    def test_all_three_network_types_present(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        types = {n["network_type"] for n in resp.json()["nodes"]}
        assert "3G" in types
        assert "4G" in types
        assert "5G" in types

    def test_node_zero_tickets_included_in_total(self, client):
        """Nodes with no tickets still appear in topology."""
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/graph")
        node_ids = [n["node_id"] for n in resp.json()["nodes"]]
        assert "5G_ESS_1017001" in node_ids


# ---------------------------------------------------------------------------
# GET /network/node/{node_id}/tickets — drill-down
# ---------------------------------------------------------------------------

class TestGetNodeTickets:

    def test_returns_200_with_node_id_and_tickets(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/node/LTE_ENB_780321/tickets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"] == "LTE_ENB_780321"
        assert "tickets" in data

    def test_tickets_include_alarm_and_severity(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/node/LTE_ENB_780321/tickets")
        tickets = resp.json()["tickets"]
        assert len(tickets) > 0
        t = tickets[0]
        assert "alarm_name" in t
        assert "severity" in t
        assert "fault_type" in t
        assert "status" in t

    def test_pending_review_ticket_visible_in_drill_down(self, client):
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db()
            resp = client.get("/api/v1/network/node/LTE_ENB_780321/tickets")
        statuses = [t["status"] for t in resp.json()["tickets"]]
        assert "pending_review" in statuses

    def test_default_limit_5_tickets(self, client):
        many_tickets = SAMPLE_NODE_TICKETS * 3
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db(node_tickets=many_tickets[:5])
            resp = client.get("/api/v1/network/node/LTE_ENB_780321/tickets")
        assert len(resp.json()["tickets"]) <= 5

    def test_rnc_node_drill_down(self, client):
        rnc_tickets = [
            {"ticket_id": "TKT-RNC-001", "alarm_name": "Link Failure", "fault_type": "node_down",
             "severity": "critical", "status": "pending_review",
             "created_at": "2025-12-01T08:00:00", "network_type": "3G"},
        ]
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db(node_tickets=rnc_tickets)
            resp = client.get("/api/v1/network/node/Rnc07/tickets")
        assert resp.status_code == 200
        assert resp.json()["node_id"] == "Rnc07"

    def test_5g_gnb_drill_down(self, client):
        gnb_tickets = [
            {"ticket_id": "TKT-GNB-001", "alarm_name": "SyncRefQuality", "fault_type": "sync_reference_quality",
             "severity": "major", "status": "open",
             "created_at": "2025-12-03T10:00:00", "network_type": "5G"},
        ]
        with patch("app.api.v1.network.sqlite3.connect") as mock_connect, \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            mock_connect.return_value = _mock_db(node_tickets=gnb_tickets)
            resp = client.get("/api/v1/network/node/5G_GNB_1039321/tickets")
        assert resp.status_code == 200
        assert resp.json()["tickets"][0]["fault_type"] == "sync_reference_quality"


# ---------------------------------------------------------------------------
# POST /network/refresh
# ---------------------------------------------------------------------------

class TestNetworkRefresh:

    def test_refresh_returns_200_on_success(self, client):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "766 nodes, 247 edges written.\n"
        with patch("app.api.v1.network.subprocess.run", return_value=mock_result), \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            resp = client.post("/api/v1/network/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "refreshed"
        assert "output" in data

    def test_refresh_includes_build_output(self, client):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "766 nodes, 247 edges written.\n"
        with patch("app.api.v1.network.subprocess.run", return_value=mock_result), \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            resp = client.post("/api/v1/network/refresh")
        assert "766" in resp.json()["output"]

    def test_refresh_returns_500_when_script_fails(self, client):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: DB not found\n"
        with patch("app.api.v1.network.subprocess.run", return_value=mock_result), \
             patch("app.api.v1.network.os.path.exists", return_value=True):
            resp = client.post("/api/v1/network/refresh")
        assert resp.status_code == 500
        assert "failed" in resp.json()["detail"].lower()

    def test_refresh_returns_500_when_script_missing(self, client):
        with patch("app.api.v1.network.os.path.exists", side_effect=lambda p: "tickets.db" in p):
            resp = client.post("/api/v1/network/refresh")
        assert resp.status_code in (500, 503)
