"""
Planned maintenance / change-freeze domain models.

A PlannedMaintenance record describes a time window during which one or
more network nodes are under scheduled work.  If a ticket arrives for a
node that is inside an active maintenance window, the expected behaviour is:

  1. Do NOT dispatch an additional truck — the maintenance team is already
     on site (or the fault is a known side-effect of the work).
  2. Attach the maintenance reference to the ticket for NOC visibility.
  3. Set dispatch mode to HOLD and resolve automatically once the window ends.

Raw DDL
-------
CREATE TABLE IF NOT EXISTS planned_maintenance (
    maintenance_id   TEXT    PRIMARY KEY,
    title            TEXT    NOT NULL,
    maintenance_type TEXT    NOT NULL DEFAULT 'planned'
                             CHECK (maintenance_type IN
                               ('planned','emergency','change_freeze','survey')),
    affected_nodes   TEXT    NOT NULL DEFAULT '[]',  -- JSON array of node IDs
    start_time       TEXT    NOT NULL,
    end_time         TEXT    NOT NULL,
    description      TEXT    NOT NULL DEFAULT '',
    contact          TEXT,
    external_ref     TEXT,   -- CR/change-request number from ITSM
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS ix_pm_start ON planned_maintenance(start_time);
CREATE INDEX IF NOT EXISTS ix_pm_end   ON planned_maintenance(end_time);
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class MaintenanceType(str, Enum):
    PLANNED       = "planned"
    EMERGENCY     = "emergency"
    CHANGE_FREEZE = "change_freeze"
    SURVEY        = "survey"


class PlannedMaintenance(BaseModel):
    maintenance_id:   str
    title:            str
    maintenance_type: MaintenanceType  = MaintenanceType.PLANNED
    affected_nodes:   list[str]        = Field(default_factory=list)
    start_time:       datetime
    end_time:         datetime
    description:      str              = ""
    contact:          Optional[str]    = None
    external_ref:     Optional[str]    = None   # CR / RFC number

    @model_validator(mode="after")
    def end_after_start(self) -> "PlannedMaintenance":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    def covers_node(self, node: str) -> bool:
        """True if this window applies to `node` (exact or prefix match)."""
        node_upper = node.upper()
        return any(
            node_upper == n.upper() or node_upper.startswith(n.upper())
            for n in self.affected_nodes
        )

    def is_active_at(self, when: datetime) -> bool:
        when_naive = when.replace(tzinfo=None)
        start_naive = self.start_time.replace(tzinfo=None)
        end_naive   = self.end_time.replace(tzinfo=None)
        return start_naive <= when_naive <= end_naive


class MaintenanceCheckResult(BaseModel):
    """Output of MaintenanceChecker — consumed by CorrelationEngine and agent tools."""
    node:             str
    in_maintenance:   bool
    window:           Optional[PlannedMaintenance] = None
    # Derived flag — True means suppress ticket and hold dispatch
    dispatch_blocked: bool = False
    summary:          str  = ""

    @classmethod
    def none_found(cls, node: str) -> "MaintenanceCheckResult":
        return cls(
            node=node,
            in_maintenance=False,
            summary=f"No active maintenance window found for node {node}.",
        )

    @classmethod
    def found(cls, node: str, window: PlannedMaintenance) -> "MaintenanceCheckResult":
        return cls(
            node=node,
            in_maintenance=True,
            window=window,
            dispatch_blocked=True,
            summary=(
                f"Node {node} is under planned maintenance '{window.title}' "
                f"(ref: {window.external_ref or 'N/A'}) until "
                f"{window.end_time.isoformat()}. "
                f"Contact: {window.contact or 'NOC'}. "
                "Truck dispatch suppressed — maintenance team is responsible."
            ),
        )
