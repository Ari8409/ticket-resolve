"""
Immutable audit log for ticket lifecycle events.

Satisfies EU AI Act Art.12 (traceability of automated decisions),
GSMA-ACCT-01 (accountability), and ITU-T Y.3172 §7.4 (audit trail).

Table: ticket_audit_log
    append-only — no UPDATE or DELETE operations on this table.
    Each row records a single state transition or lifecycle event.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select


# ---------------------------------------------------------------------------
# Event type enum
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    STATUS_CHANGE = "status_change"
    ASSIGNMENT    = "assignment"
    FLAG_REVIEW   = "flag_review"
    ESCALATION    = "escalation"
    RESOLUTION    = "resolution"


# ---------------------------------------------------------------------------
# SQLModel table
# ---------------------------------------------------------------------------

class TicketAuditLogRow(SQLModel, table=True):
    """One immutable row per lifecycle event. Never updated or deleted."""

    __tablename__ = "ticket_audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)

    ticket_id:   str           = Field(
        ...,
        foreign_key="telco_tickets.ticket_id",
        index=True,
        max_length=32,
    )
    event_type:  str           = Field(..., max_length=32)   # EventType value
    from_status: Optional[str] = Field(default=None, max_length=32)
    to_status:   Optional[str] = Field(default=None, max_length=32)
    changed_by:  Optional[str] = Field(default=None, max_length=128)
    reason:      Optional[str] = Field(default=None, max_length=2000)
    created_at:  datetime      = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Repository — append-only
# ---------------------------------------------------------------------------

class AuditLogRepository:
    """Append-only repository for ticket_audit_log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        ticket_id:   str,
        event_type:  EventType,
        from_status: Optional[str] = None,
        to_status:   Optional[str] = None,
        changed_by:  Optional[str] = None,
        reason:      Optional[str] = None,
    ) -> None:
        """Insert one audit row. Never raises on duplicate — each call is additive."""
        row = TicketAuditLogRow(
            ticket_id=ticket_id,
            event_type=event_type.value,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            reason=reason,
        )
        self._session.add(row)
        await self._session.commit()

    async def get_trail(self, ticket_id: str) -> list[TicketAuditLogRow]:
        """Return all audit rows for a ticket, chronological order."""
        result = await self._session.execute(
            select(TicketAuditLogRow)
            .where(TicketAuditLogRow.ticket_id == ticket_id)
            .order_by(TicketAuditLogRow.created_at.asc())
        )
        return result.scalars().all()
