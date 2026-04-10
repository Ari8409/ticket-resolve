"""
Alarm domain models.

An AlarmRecord represents a single fault event raised by a Network
Management System (NMS).  The key field for pre-dispatch logic is
`cleared_at`: if it is set, the underlying network fault has already
self-healed and no truck dispatch is warranted.

Raw DDL (for documentation / Alembic migrations)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS active_alarms (
    alarm_id        TEXT    PRIMARY KEY,
    affected_node   TEXT    NOT NULL,
    alarm_type      TEXT    NOT NULL,
    severity        TEXT    NOT NULL,
    source_system   TEXT    NOT NULL DEFAULT 'nms',
    raised_at       TEXT    NOT NULL,
    cleared_at      TEXT,                       -- NULL  → still active
    status          TEXT    NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','cleared','acknowledged')),
    raw_payload     TEXT    NOT NULL DEFAULT '{}',  -- original NMS JSON
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS ix_active_alarms_node   ON active_alarms(affected_node);
CREATE INDEX IF NOT EXISTS ix_active_alarms_status ON active_alarms(status);
CREATE INDEX IF NOT EXISTS ix_active_alarms_raised  ON active_alarms(raised_at);
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AlarmStatus(str, Enum):
    ACTIVE       = "active"
    CLEARED      = "cleared"
    ACKNOWLEDGED = "acknowledged"


class AlarmRecord(BaseModel):
    """A single NMS alarm event — the live truth about a node's fault state."""
    alarm_id:      str
    affected_node: str
    alarm_type:    str                       # maps loosely to FaultType
    severity:      str
    source_system: str = "nms"
    raised_at:     datetime
    cleared_at:    Optional[datetime] = None
    status:        AlarmStatus        = AlarmStatus.ACTIVE
    raw_payload:   dict               = Field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == AlarmStatus.ACTIVE and self.cleared_at is None

    @property
    def age_seconds(self) -> float:
        return (datetime.utcnow() - self.raised_at.replace(tzinfo=None)).total_seconds()


class AlarmCheckResult(BaseModel):
    """Output of AlarmChecker — consumed by CorrelationEngine and agent tools."""
    node:          str
    alarm_found:   bool
    status:        Optional[AlarmStatus]  = None
    alarm_id:      Optional[str]          = None
    alarm_type:    Optional[str]          = None
    severity:      Optional[str]          = None
    raised_at:     Optional[datetime]     = None
    cleared_at:    Optional[datetime]     = None
    # Derived flag used by the correlation engine
    dispatch_blocked: bool = False         # True when alarm is already cleared
    summary: str = ""

    @classmethod
    def not_found(cls, node: str) -> "AlarmCheckResult":
        return cls(node=node, alarm_found=False, summary=f"No alarm found for node {node}.")

    @classmethod
    def cleared(cls, node: str, alarm: "AlarmRecord") -> "AlarmCheckResult":
        return cls(
            node=node,
            alarm_found=True,
            status=AlarmStatus.CLEARED,
            alarm_id=alarm.alarm_id,
            alarm_type=alarm.alarm_type,
            severity=alarm.severity,
            raised_at=alarm.raised_at,
            cleared_at=alarm.cleared_at,
            dispatch_blocked=True,
            summary=(
                f"Alarm {alarm.alarm_id} on {node} was CLEARED at "
                f"{alarm.cleared_at.isoformat() if alarm.cleared_at else 'unknown'}. "
                "No truck dispatch required — fault has self-healed."
            ),
        )

    @classmethod
    def active(cls, node: str, alarm: "AlarmRecord") -> "AlarmCheckResult":
        return cls(
            node=node,
            alarm_found=True,
            status=AlarmStatus.ACTIVE,
            alarm_id=alarm.alarm_id,
            alarm_type=alarm.alarm_type,
            severity=alarm.severity,
            raised_at=alarm.raised_at,
            cleared_at=None,
            dispatch_blocked=False,
            summary=(
                f"Alarm {alarm.alarm_id} on {node} is still ACTIVE "
                f"(raised {alarm.raised_at.isoformat()}). Fault persists."
            ),
        )
