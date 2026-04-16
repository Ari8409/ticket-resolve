"""
SQLModel table models for the network graph database.

Tables:
  network_nodes  — one row per unique network element (RNC, NodeB, ENB, GNB, ESS)
  network_edges  — parent/peer relationships between nodes
"""

import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class NetworkNodeRow(SQLModel, table=True):
    __tablename__ = "network_nodes"

    node_id: str = Field(primary_key=True)
    network_type: str                                      # "3G" | "4G" | "5G" | "Other"
    node_class: str                                        # "RNC" | "NodeB" | "ENB" | "ESS" | "GNB" | "Unknown"
    parent_node: Optional[str] = Field(
        default=None, foreign_key="network_nodes.node_id"
    )
    x_pos: float = Field(default=0.0)                     # pre-computed layout [0,1]
    y_pos: float = Field(default=0.0)
    ticket_count: int = Field(default=0)                  # total tickets referencing this node
    pending_count: int = Field(default=0)                 # tickets in pending_review
    open_count: int = Field(default=0)                    # open + in_progress + escalated
    resolved_count: int = Field(default=0)                # resolved tickets
    last_ticket_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.utcnow
    )


class NetworkEdgeRow(SQLModel, table=True):
    __tablename__ = "network_edges"

    edge_id: Optional[int] = Field(default=None, primary_key=True)
    source_node: str = Field(foreign_key="network_nodes.node_id")
    target_node: str = Field(foreign_key="network_nodes.node_id")
    edge_type: str = Field(default="parent")              # "parent" | "peer"
