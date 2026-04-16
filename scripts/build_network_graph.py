"""
Build the network graph database from telco_tickets data.

Reads unique (affected_node, network_type) pairs from telco_tickets,
classifies each node, computes NetworkX layout positions, aggregates
ticket stats, and writes to network_nodes + network_edges tables.

Usage (from repo root):
    python scripts/build_network_graph.py
"""

import os
import re
import sqlite3
import datetime

import networkx as nx

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tickets.db")

# ---------------------------------------------------------------------------
# Node classification
# ---------------------------------------------------------------------------
RNC_RE    = re.compile(r"^Rnc\d+$",         re.IGNORECASE)
NODEB_RE  = re.compile(r"^(Rnc\d+)_(\d+)$", re.IGNORECASE)
ENB_RE    = re.compile(r"^LTE_ENB_",        re.IGNORECASE)
ESS4G_RE  = re.compile(r"^LTE_ESS_",        re.IGNORECASE)
GNB_RE    = re.compile(r"^5G_GNB_",         re.IGNORECASE)
ESS5G_RE  = re.compile(r"^5G_ESS_",         re.IGNORECASE)


def classify(node_id: str):
    """Return (node_class, network_type, parent_node_id | None)."""
    if RNC_RE.match(node_id):
        return ("RNC", "3G", None)
    m = NODEB_RE.match(node_id)
    if m:
        parent = m.group(1)
        # Normalise to the capitalisation used in the DB (e.g. Rnc07)
        parent = parent[0].upper() + parent[1:].lower()
        # parent looks like "Rnc07" – match the exact form stored in tickets
        # We'll keep it as-is from the regex group and normalise later
        parent = m.group(1)
        return ("NodeB", "3G", parent)
    if ENB_RE.match(node_id):
        return ("ENB", "4G", None)
    if ESS4G_RE.match(node_id):
        return ("ESS", "4G", None)
    if GNB_RE.match(node_id):
        return ("GNB", "5G", None)
    if ESS5G_RE.match(node_id):
        return ("ESS", "5G", None)
    return ("Unknown", "Other", None)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _normalize(positions: dict) -> dict:
    """Scale all (x, y) values to [0.05, 0.95]."""
    if not positions:
        return positions
    xs = [v[0] for v in positions.values()]
    ys = [v[1] for v in positions.values()]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = x_max - x_min or 1.0
    y_range = y_max - y_min or 1.0
    return {
        k: (
            0.05 + 0.90 * (v[0] - x_min) / x_range,
            0.05 + 0.90 * (v[1] - y_min) / y_range,
        )
        for k, v in positions.items()
    }


def compute_3g_layout(rncs: list, nodeb_map: dict) -> dict:
    """
    Shell-style layout for 3G: RNCs in a ring in the centre,
    their NodeBs fanned out around each RNC.
    """
    import math
    positions = {}
    n_rncs = len(rncs)
    if n_rncs == 0:
        return positions

    # Place RNCs on a circle of radius 0.25 centred at (0, 0)
    rnc_radius = 0.25
    for i, rnc in enumerate(rncs):
        angle = 2 * math.pi * i / n_rncs
        positions[rnc] = (rnc_radius * math.cos(angle), rnc_radius * math.sin(angle))

    # Place NodeBs around their RNC
    for rnc, children in nodeb_map.items():
        if rnc not in positions:
            continue
        cx, cy = positions[rnc]
        n_children = len(children)
        child_radius = 0.18
        for j, child in enumerate(children):
            angle = 2 * math.pi * j / max(n_children, 1)
            positions[child] = (
                cx + child_radius * math.cos(angle),
                cy + child_radius * math.sin(angle),
            )
    return positions


def compute_cluster_layout(nodes: list, center_x: float, center_y: float, spread: float = 0.35) -> dict:
    """Spring layout for a cluster of nodes, offset to (center_x, center_y)."""
    if not nodes:
        return {}
    G = nx.Graph()
    G.add_nodes_from(nodes)
    pos = nx.spring_layout(G, seed=42, k=2.0 / max(len(nodes) ** 0.5, 1))
    # Scale spread and translate to cluster centre
    return {
        n: (center_x + spread * pos[n][0], center_y + spread * pos[n][1])
        for n in nodes
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    now = datetime.datetime.utcnow().isoformat()

    # ------------------------------------------------------------------
    # 1. Fetch unique nodes + ticket stats
    # ------------------------------------------------------------------
    rows = db.execute("""
        SELECT
            affected_node,
            COUNT(*) AS ticket_count,
            SUM(CASE WHEN status = 'pending_review' THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN status IN ('open','in_progress','escalated','assigned') THEN 1 ELSE 0 END) AS open_count,
            SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved_count,
            MAX(created_at) AS last_ticket_at
        FROM telco_tickets
        WHERE affected_node IS NOT NULL AND affected_node != ''
        GROUP BY affected_node
    """).fetchall()

    print(f"Unique nodes found in telco_tickets: {len(rows)}")

    # ------------------------------------------------------------------
    # 2. Classify each node
    # ------------------------------------------------------------------
    nodes = {}          # node_id -> dict
    rncs = []
    nodeb_map = {}      # rnc_id -> [child_node_ids]
    nodes_4g = []
    nodes_5g = []
    nodes_other = []

    for row in rows:
        nid = row["affected_node"]
        nc, nt, parent = classify(nid)
        nodes[nid] = {
            "node_id": nid,
            "network_type": nt,
            "node_class": nc,
            "parent_node": parent,
            "ticket_count": row["ticket_count"],
            "pending_count": row["pending_count"] or 0,
            "open_count": row["open_count"] or 0,
            "resolved_count": row["resolved_count"] or 0,
            "last_ticket_at": row["last_ticket_at"],
            "created_at": now,
            "x_pos": 0.0,
            "y_pos": 0.0,
        }
        if nc == "RNC":
            rncs.append(nid)
        elif nc == "NodeB":
            nodeb_map.setdefault(parent, []).append(nid)
        elif nt == "4G":
            nodes_4g.append(nid)
        elif nt == "5G":
            nodes_5g.append(nid)
        else:
            nodes_other.append(nid)

    # Ensure all RNCs referenced as parents exist (even if they have no tickets)
    for parent in list(nodeb_map.keys()):
        if parent not in nodes:
            nodes[parent] = {
                "node_id": parent,
                "network_type": "3G",
                "node_class": "RNC",
                "parent_node": None,
                "ticket_count": 0,
                "pending_count": 0,
                "open_count": 0,
                "resolved_count": 0,
                "last_ticket_at": None,
                "created_at": now,
                "x_pos": 0.0,
                "y_pos": 0.0,
            }
            rncs.append(parent)
            print(f"  Added synthetic RNC node: {parent}")

    print(f"  3G RNCs: {len(rncs)}, NodeBs: {sum(len(v) for v in nodeb_map.values())}")
    print(f"  4G nodes: {len(nodes_4g)}")
    print(f"  5G nodes: {len(nodes_5g)}")
    print(f"  Other: {len(nodes_other)}")

    # ------------------------------------------------------------------
    # 3. Compute layout (three clusters in different quadrants)
    # ------------------------------------------------------------------
    # 3G cluster: left side [0.0, 0.5] x-range
    pos_3g = compute_3g_layout(rncs, nodeb_map)
    # Re-scale to fit in left third of canvas
    pos_3g_norm = _normalize(pos_3g)
    for nid, (x, y) in pos_3g_norm.items():
        # Map to left 32% horizontally, full height
        nodes[nid]["x_pos"] = round(0.01 + 0.31 * x, 4)
        nodes[nid]["y_pos"] = round(0.05 + 0.90 * y, 4)

    # 4G cluster: centre
    pos_4g = compute_cluster_layout(nodes_4g, center_x=0.0, center_y=0.0, spread=0.5)
    pos_4g_norm = _normalize(pos_4g)
    for nid, (x, y) in pos_4g_norm.items():
        nodes[nid]["x_pos"] = round(0.34 + 0.33 * x, 4)
        nodes[nid]["y_pos"] = round(0.05 + 0.90 * y, 4)

    # 5G cluster: right
    pos_5g = compute_cluster_layout(nodes_5g, center_x=0.0, center_y=0.0, spread=0.5)
    pos_5g_norm = _normalize(pos_5g)
    for nid, (x, y) in pos_5g_norm.items():
        nodes[nid]["x_pos"] = round(0.68 + 0.31 * x, 4)
        nodes[nid]["y_pos"] = round(0.05 + 0.90 * y, 4)

    # Other — place at bottom-right corner
    for i, nid in enumerate(nodes_other):
        nodes[nid]["x_pos"] = round(0.90 + 0.05 * (i % 3), 4)
        nodes[nid]["y_pos"] = round(0.90 + 0.05 * (i // 3), 4)

    # ------------------------------------------------------------------
    # 4. Build edges (RNC -> NodeB parent relationships)
    # ------------------------------------------------------------------
    edges = []
    for parent, children in nodeb_map.items():
        for child in children:
            edges.append({"source_node": parent, "target_node": child, "edge_type": "parent"})

    print(f"Edges (RNC->NodeB): {len(edges)}")

    # ------------------------------------------------------------------
    # 5. Write to SQLite
    # ------------------------------------------------------------------
    db.execute("DELETE FROM network_edges")
    db.execute("DELETE FROM network_nodes")

    node_records = [
        (
            n["node_id"], n["network_type"], n["node_class"], n["parent_node"],
            n["x_pos"], n["y_pos"],
            n["ticket_count"], n["pending_count"], n["open_count"], n["resolved_count"],
            n["last_ticket_at"], n["created_at"],
        )
        for n in nodes.values()
    ]
    db.executemany("""
        INSERT INTO network_nodes
            (node_id, network_type, node_class, parent_node,
             x_pos, y_pos,
             ticket_count, pending_count, open_count, resolved_count,
             last_ticket_at, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, node_records)

    edge_records = [(e["source_node"], e["target_node"], e["edge_type"]) for e in edges]
    db.executemany("""
        INSERT INTO network_edges (source_node, target_node, edge_type)
        VALUES (?,?,?)
    """, edge_records)

    db.commit()
    db.close()

    print(f"\nDone: {len(nodes)} nodes, {len(edges)} edges written to network_nodes/network_edges")


if __name__ == "__main__":
    main()
