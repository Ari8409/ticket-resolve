"""
SQLite schema and repository for telco tickets.

Tables
------
sops
    Master table of Standard Operating Procedures referenced by tickets.

telco_tickets
    One row per network fault ticket. resolution_steps stored as a
    JSON-encoded array so SQLite doesn't need an extra join table.

telco_dispatch_decisions
    One row per resolved/short-circuited ticket. Stores the full
    DispatchDecision produced by the correlation+LLM pipeline.

Indexes
-------
  ix_telco_tickets_affected_node   — fast lookups by node ID
  ix_telco_tickets_fault_type      — filter by fault category
  ix_telco_tickets_severity        — filter / sort by severity
  ix_telco_tickets_status          — filter open / escalated tickets
  ix_telco_tickets_sop_id          — look up all tickets for a given SOP

The raw DDL is reproduced in the module docstring below for documentation
and for use outside SQLModel (e.g. direct sqlite3, Alembic migrations).

Raw DDL
-------
CREATE TABLE IF NOT EXISTS sops (
    sop_id      TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    category    TEXT,
    doc_path    TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS telco_tickets (
    ticket_id        TEXT    PRIMARY KEY,
    timestamp        TEXT    NOT NULL,
    fault_type       TEXT    NOT NULL
                             CHECK (fault_type IN (
                                 'signal_loss','latency','node_down',
                                 'packet_loss','congestion',
                                 'hardware_failure','configuration_error','unknown'
                             )),
    affected_node    TEXT    NOT NULL,
    severity         TEXT    NOT NULL
                             CHECK (severity IN ('low','medium','high','critical')),
    status           TEXT    NOT NULL DEFAULT 'open'
                             CHECK (status IN (
                                 'open','in_progress','resolved','closed','escalated'
                             )),
    description      TEXT    NOT NULL,
    resolution_steps TEXT    NOT NULL DEFAULT '[]',   -- JSON array of strings
    sop_id           TEXT    REFERENCES sops(sop_id) ON DELETE SET NULL,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS telco_dispatch_decisions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id           TEXT    NOT NULL UNIQUE REFERENCES telco_tickets(ticket_id),
    dispatch_mode       TEXT    NOT NULL
                                CHECK (dispatch_mode IN ('remote','on_site','hold','escalate')),
    confidence_score    REAL    NOT NULL DEFAULT 0.0,
    recommended_steps   TEXT    NOT NULL DEFAULT '[]',  -- JSON array of strings
    reasoning           TEXT    NOT NULL DEFAULT '',
    escalation_required INTEGER NOT NULL DEFAULT 0,
    relevant_sops       TEXT    NOT NULL DEFAULT '[]',  -- JSON array of strings
    similar_ticket_ids  TEXT    NOT NULL DEFAULT '[]',  -- JSON array of strings
    short_circuited     INTEGER NOT NULL DEFAULT 0,
    short_circuit_reason TEXT,
    alarm_status        TEXT,
    maintenance_active  INTEGER,
    remote_feasible     INTEGER,
    remote_confidence   REAL,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS ix_telco_tickets_affected_node ON telco_tickets(affected_node);
CREATE INDEX IF NOT EXISTS ix_telco_tickets_fault_type    ON telco_tickets(fault_type);
CREATE INDEX IF NOT EXISTS ix_telco_tickets_severity      ON telco_tickets(severity);
CREATE INDEX IF NOT EXISTS ix_telco_tickets_status        ON telco_tickets(status);
CREATE INDEX IF NOT EXISTS ix_telco_tickets_sop_id        ON telco_tickets(sop_id);
CREATE INDEX IF NOT EXISTS ix_dispatch_decisions_ticket   ON telco_dispatch_decisions(ticket_id);
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select

from app.models.telco_ticket import (
    FaultType,
    Severity,
    TelcoTicketCreate,
    TelcoTicketStatus,
    TelcoTicketUpdate,
)


# ---------------------------------------------------------------------------
# Forward-reference for DispatchDecision (imported lazily to avoid cycles)
# ---------------------------------------------------------------------------
# from app.correlation.models import DispatchDecision  — done at method level


# ---------------------------------------------------------------------------
# SQLModel table: sops
# ---------------------------------------------------------------------------

class SOPRow(SQLModel, table=True):
    """Master SOP catalogue referenced by telco tickets."""

    __tablename__ = "sops"

    sop_id:     str           = Field(primary_key=True, max_length=64)
    title:      str           = Field(..., max_length=256)
    category:   Optional[str] = Field(default=None, max_length=64)
    doc_path:   Optional[str] = Field(default=None, max_length=512)
    created_at: datetime      = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# SQLModel table: telco_tickets
# ---------------------------------------------------------------------------

class TelcoTicketRow(SQLModel, table=True):
    """
    Persisted telco ticket.  Enum columns are stored as plain TEXT with
    CHECK constraints enforced at the DDL layer (see module docstring).

    Aligned with the CTTS (Customer Trouble Ticket System) data schema used
    in the NOC daily ticket exports (27 Nov – 4 Dec 2025, 39 columns).
    All CTTS-sourced columns are nullable to support both manual and import
    creation paths.
    """

    __tablename__ = "telco_tickets"

    # --- Primary key ---
    ticket_id: str = Field(
        default_factory=lambda: f"TKT-{uuid.uuid4().hex[:8].upper()}",
        primary_key=True,
        max_length=32,
    )

    # --- CTTS identity ---
    ctts_ticket_number: Optional[int] = Field(default=None, index=True)

    # --- Timestamps ---
    timestamp:        datetime           = Field(default_factory=datetime.utcnow)
    event_start_time: Optional[datetime] = Field(default=None)
    event_end_time:   Optional[datetime] = Field(default=None)
    modified_date:    Optional[datetime] = Field(default=None)

    # --- Core fault fields ---
    fault_type:    str = Field(..., max_length=32)       # FaultType value
    affected_node: str = Field(..., max_length=128, index=True)
    severity:      str = Field(..., max_length=16)       # Severity value
    status:        str = Field(default=TelcoTicketStatus.OPEN.value, max_length=16, index=True)

    # --- Content ---
    description:      str = Field(..., max_length=4000)
    resolution_steps: str = Field(default="[]", max_length=8000)  # JSON list[str]

    # --- Parsed alarm fields (auto-populated from CTTS description) ---
    node_id:             Optional[str] = Field(default=None, max_length=128)
    alarm_category:      Optional[str] = Field(default=None, max_length=64)
    alarm_name:          Optional[str] = Field(default=None, max_length=128)
    alarm_severity_code: Optional[str] = Field(default=None, max_length=8)

    # --- Assignment & ownership ---
    title:               Optional[str] = Field(default=None, max_length=256)
    assignment_profile:  Optional[str] = Field(default=None, max_length=128)
    group:               Optional[str] = Field(default=None, max_length=64)
    object_class:        Optional[str] = Field(default=None, max_length=32)
    owner_profile:       Optional[str] = Field(default=None, max_length=128)
    owner_profile_group: Optional[str] = Field(default=None, max_length=128)
    resolved_group:      Optional[str] = Field(default=None, max_length=128)
    last_ack_by:         Optional[str] = Field(default=None, max_length=128)
    resolved_person:     Optional[str] = Field(default=None, max_length=128)

    # --- Source & categorisation ---
    source:          Optional[str] = Field(default=None, max_length=64)
    category_group:  Optional[str] = Field(default=None, max_length=64)
    network_type:    Optional[str] = Field(default=None, max_length=16)
    mobile_or_fixed: Optional[str] = Field(default=None, max_length=32)

    # --- Location ---
    location_details: Optional[str] = Field(default=None, max_length=256)
    location_id:      Optional[str] = Field(default=None, max_length=64)

    # --- Resolution ---
    primary_cause:   Optional[str] = Field(default=None, max_length=256)
    remarks:         Optional[str] = Field(default=None, max_length=2000)
    resolution:      Optional[str] = Field(default=None, max_length=1000)
    resolution_code: Optional[str] = Field(default=None, max_length=256)

    # --- SOP linkage — nullable FK to sops.sop_id ---
    sop_id: Optional[str] = Field(
        default=None,
        max_length=64,
        foreign_key="sops.sop_id",
        index=True,
    )

    # --- Audit ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional indexes (fault_type, severity) declared outside the model
    __table_args__ = (
        Index("ix_telco_tickets_fault_type", "fault_type"),
        Index("ix_telco_tickets_severity",   "severity"),
    )


# ---------------------------------------------------------------------------
# SQLModel table: telco_dispatch_decisions
# ---------------------------------------------------------------------------

class TelcoDispatchDecisionRow(SQLModel, table=True):
    """
    Persisted output of the correlation + LLM pipeline.
    One row per ticket — unique on ticket_id.
    """

    __tablename__ = "telco_dispatch_decisions"

    id: Optional[int] = Field(default=None, primary_key=True)

    # FK to telco_tickets
    ticket_id: str = Field(
        ...,
        max_length=32,
        foreign_key="telco_tickets.ticket_id",
        index=True,
    )

    # Core decision fields
    dispatch_mode:       str   = Field(..., max_length=16)           # DispatchMode value
    confidence_score:    float = Field(default=0.0)
    recommended_steps:   str   = Field(default="[]")                 # JSON list[str]
    reasoning:           str   = Field(default="")
    escalation_required: bool  = Field(default=False)
    relevant_sops:       str   = Field(default="[]")                 # JSON list[str]
    similar_ticket_ids:  str   = Field(default="[]")                 # JSON list[str]

    # Short-circuit metadata
    short_circuited:      bool            = Field(default=False)
    short_circuit_reason: Optional[str]  = Field(default=None)

    # Denormalised snapshot of correlation results for quick querying
    alarm_status:       Optional[str]   = Field(default=None, max_length=16)
    maintenance_active: Optional[bool]  = Field(default=None)
    remote_feasible:    Optional[bool]  = Field(default=None)
    remote_confidence:  Optional[float] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class TelcoTicketRepository:
    """Async CRUD for TelcoTicketRow. Accepts and returns domain models."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _to_row(ticket: TelcoTicketCreate) -> TelcoTicketRow:
        return TelcoTicketRow(
            ticket_id=ticket.ticket_id,
            ctts_ticket_number=ticket.ctts_ticket_number,
            timestamp=ticket.timestamp,
            event_start_time=ticket.event_start_time,
            event_end_time=ticket.event_end_time,
            modified_date=ticket.modified_date,
            fault_type=ticket.fault_type.value,
            affected_node=ticket.affected_node,
            severity=ticket.severity.value,
            status=TelcoTicketStatus.OPEN.value,
            description=ticket.description,
            resolution_steps=json.dumps(ticket.resolution_steps),
            node_id=ticket.node_id,
            alarm_category=ticket.alarm_category,
            alarm_name=ticket.alarm_name,
            alarm_severity_code=ticket.alarm_severity_code,
            title=ticket.title,
            assignment_profile=ticket.assignment_profile,
            group=ticket.group,
            object_class=ticket.object_class,
            owner_profile=ticket.owner_profile,
            owner_profile_group=ticket.owner_profile_group,
            resolved_group=ticket.resolved_group,
            last_ack_by=ticket.last_ack_by,
            resolved_person=ticket.resolved_person,
            source=ticket.source,
            category_group=ticket.category_group,
            network_type=ticket.network_type,
            mobile_or_fixed=ticket.mobile_or_fixed,
            location_details=ticket.location_details,
            location_id=ticket.location_id,
            primary_cause=ticket.primary_cause,
            remarks=ticket.remarks,
            resolution=ticket.resolution,
            resolution_code=ticket.resolution_code,
            sop_id=ticket.sop_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    @staticmethod
    def _row_to_dict(row: TelcoTicketRow) -> dict:
        return {
            "ticket_id":           row.ticket_id,
            "ctts_ticket_number":  row.ctts_ticket_number,
            "timestamp":           row.timestamp,
            "event_start_time":    row.event_start_time,
            "event_end_time":      row.event_end_time,
            "modified_date":       row.modified_date,
            "fault_type":          FaultType(row.fault_type),
            "affected_node":       row.affected_node,
            "severity":            Severity(row.severity),
            "status":              TelcoTicketStatus(row.status),
            "description":         row.description,
            "resolution_steps":    json.loads(row.resolution_steps),
            "node_id":             row.node_id,
            "alarm_category":      row.alarm_category,
            "alarm_name":          row.alarm_name,
            "alarm_severity_code": row.alarm_severity_code,
            "title":               row.title,
            "assignment_profile":  row.assignment_profile,
            "group":               row.group,
            "object_class":        row.object_class,
            "owner_profile":       row.owner_profile,
            "owner_profile_group": row.owner_profile_group,
            "resolved_group":      row.resolved_group,
            "last_ack_by":         row.last_ack_by,
            "resolved_person":     row.resolved_person,
            "source":              row.source,
            "category_group":      row.category_group,
            "network_type":        row.network_type,
            "mobile_or_fixed":     row.mobile_or_fixed,
            "location_details":    row.location_details,
            "location_id":         row.location_id,
            "primary_cause":       row.primary_cause,
            "remarks":             row.remarks,
            "resolution":          row.resolution,
            "resolution_code":     row.resolution_code,
            "sop_id":              row.sop_id,
            "created_at":          row.created_at,
            "updated_at":          row.updated_at,
        }

    # --- write operations ---------------------------------------------------

    async def create(self, ticket: TelcoTicketCreate) -> str:
        """Insert a new ticket row. Returns the ticket_id."""
        row = self._to_row(ticket)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row.ticket_id

    async def update(self, ticket_id: str, patch: TelcoTicketUpdate) -> Optional[dict]:
        """Apply partial update. Returns updated dict or None if not found."""
        result = await self._session.execute(
            select(TelcoTicketRow).where(TelcoTicketRow.ticket_id == ticket_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None

        if patch.status is not None:
            row.status = patch.status.value
        if patch.resolution_steps is not None:
            row.resolution_steps = json.dumps(patch.resolution_steps)
        if patch.sop_id is not None:
            row.sop_id = patch.sop_id
        if patch.description is not None:
            row.description = patch.description
        if patch.primary_cause is not None:
            row.primary_cause = patch.primary_cause
        if patch.remarks is not None:
            row.remarks = patch.remarks
        if patch.resolution is not None:
            row.resolution = patch.resolution
        if patch.resolution_code is not None:
            row.resolution_code = patch.resolution_code
        if patch.resolved_group is not None:
            row.resolved_group = patch.resolved_group
        if patch.resolved_person is not None:
            row.resolved_person = patch.resolved_person

        row.updated_at = datetime.utcnow()
        await self._session.commit()
        await self._session.refresh(row)
        return self._row_to_dict(row)

    # --- read operations ----------------------------------------------------

    async def get(self, ticket_id: str) -> Optional[dict]:
        result = await self._session.execute(
            select(TelcoTicketRow).where(TelcoTicketRow.ticket_id == ticket_id)
        )
        row = result.scalar_one_or_none()
        return self._row_to_dict(row) if row else None

    async def list_by_node(self, affected_node: str, limit: int = 50) -> list[dict]:
        result = await self._session.execute(
            select(TelcoTicketRow)
            .where(TelcoTicketRow.affected_node == affected_node)
            .order_by(TelcoTicketRow.timestamp.desc())
            .limit(limit)
        )
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def list_by_fault_type(self, fault_type: FaultType, limit: int = 50) -> list[dict]:
        result = await self._session.execute(
            select(TelcoTicketRow)
            .where(TelcoTicketRow.fault_type == fault_type.value)
            .order_by(TelcoTicketRow.timestamp.desc())
            .limit(limit)
        )
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def list_open_by_severity(self, severity: Severity, limit: int = 50) -> list[dict]:
        result = await self._session.execute(
            select(TelcoTicketRow)
            .where(
                TelcoTicketRow.severity == severity.value,
                TelcoTicketRow.status.in_(
                    [TelcoTicketStatus.OPEN.value, TelcoTicketStatus.IN_PROGRESS.value]
                ),
            )
            .order_by(TelcoTicketRow.timestamp.desc())
            .limit(limit)
        )
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def list_by_sop(self, sop_id: str, limit: int = 50) -> list[dict]:
        result = await self._session.execute(
            select(TelcoTicketRow)
            .where(TelcoTicketRow.sop_id == sop_id)
            .order_by(TelcoTicketRow.timestamp.desc())
            .limit(limit)
        )
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def update_status(self, ticket_id: str, status: TelcoTicketStatus) -> None:
        """Update ticket status in-place."""
        result = await self._session.execute(
            select(TelcoTicketRow).where(TelcoTicketRow.ticket_id == ticket_id)
        )
        row = result.scalar_one_or_none()
        if row:
            row.status = status.value
            row.updated_at = datetime.utcnow()
            await self._session.commit()

    async def save_dispatch_decision(self, ticket_id: str, decision) -> None:
        """
        Persist a DispatchDecision produced by the resolution pipeline.

        Accepts ``app.correlation.models.DispatchDecision`` (imported lazily
        to avoid circular imports at module load time).

        If a decision row already exists for the ticket_id it is deleted first
        so the upsert remains idempotent (SQLite has no ON CONFLICT for
        multi-column unique + autoincrement combos via SQLModel).
        """
        # Remove any previous decision for this ticket (idempotency)
        existing = await self._session.execute(
            select(TelcoDispatchDecisionRow).where(
                TelcoDispatchDecisionRow.ticket_id == ticket_id
            )
        )
        old_row = existing.scalar_one_or_none()
        if old_row:
            await self._session.delete(old_row)
            await self._session.flush()

        # Extract alarm/maintenance/feasibility snapshots when available
        alarm_status: Optional[str] = None
        maintenance_active: Optional[bool] = None
        remote_feasible: Optional[bool] = None
        remote_confidence: Optional[float] = None

        if decision.alarm_check is not None:
            ac = decision.alarm_check
            alarm_status = ac.status.value if ac.status else None

        if decision.maintenance_check is not None:
            maintenance_active = decision.maintenance_check.in_maintenance

        if decision.remote_feasibility is not None:
            rf = decision.remote_feasibility
            remote_feasible   = rf.feasible
            remote_confidence = rf.confidence

        row = TelcoDispatchDecisionRow(
            ticket_id=ticket_id,
            dispatch_mode=decision.dispatch_mode.value,
            confidence_score=decision.confidence_score,
            recommended_steps=json.dumps(decision.recommended_steps),
            reasoning=decision.reasoning,
            escalation_required=decision.escalation_required,
            relevant_sops=json.dumps(decision.relevant_sops),
            similar_ticket_ids=json.dumps(decision.similar_ticket_ids),
            short_circuited=decision.short_circuited,
            short_circuit_reason=decision.short_circuit_reason if decision.short_circuited else None,
            alarm_status=alarm_status,
            maintenance_active=maintenance_active,
            remote_feasible=remote_feasible,
            remote_confidence=remote_confidence,
            created_at=datetime.utcnow(),
        )
        self._session.add(row)
        await self._session.commit()

    async def get_dispatch_decision(self, ticket_id: str) -> Optional[dict]:
        """Return the persisted DispatchDecision dict for a ticket, or None."""
        result = await self._session.execute(
            select(TelcoDispatchDecisionRow).where(
                TelcoDispatchDecisionRow.ticket_id == ticket_id
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "ticket_id":          row.ticket_id,
            "dispatch_mode":      row.dispatch_mode,
            "confidence_score":   row.confidence_score,
            "recommended_steps":  json.loads(row.recommended_steps),
            "reasoning":          row.reasoning,
            "escalation_required": row.escalation_required,
            "relevant_sops":      json.loads(row.relevant_sops),
            "similar_ticket_ids": json.loads(row.similar_ticket_ids),
            "short_circuited":    row.short_circuited,
            "short_circuit_reason": row.short_circuit_reason,
            "alarm_status":       row.alarm_status,
            "maintenance_active": row.maintenance_active,
            "remote_feasible":    row.remote_feasible,
            "remote_confidence":  row.remote_confidence,
            "created_at":         row.created_at,
        }
