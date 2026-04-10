"""SQLModel table + repository for NMS alarm records."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, Index, SQLModel, select

from app.alarms.models import AlarmRecord, AlarmStatus


# ---------------------------------------------------------------------------
# SQLModel table
# ---------------------------------------------------------------------------

class AlarmRow(SQLModel, table=True):
    __tablename__ = "active_alarms"

    alarm_id:      str           = Field(primary_key=True, max_length=64)
    affected_node: str           = Field(..., max_length=128, index=True)
    alarm_type:    str           = Field(..., max_length=64)
    severity:      str           = Field(..., max_length=16)
    source_system: str           = Field(default="nms", max_length=64)
    raised_at:     datetime      = Field(default_factory=datetime.utcnow)
    cleared_at:    Optional[datetime] = Field(default=None)
    status:        str           = Field(default=AlarmStatus.ACTIVE.value, max_length=16, index=True)
    raw_payload:   str           = Field(default="{}", max_length=8000)  # JSON
    created_at:    datetime      = Field(default_factory=datetime.utcnow)
    updated_at:    datetime      = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("ix_active_alarms_raised", "raised_at"),
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class AlarmStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: AlarmRow) -> AlarmRecord:
        return AlarmRecord(
            alarm_id=row.alarm_id,
            affected_node=row.affected_node,
            alarm_type=row.alarm_type,
            severity=row.severity,
            source_system=row.source_system,
            raised_at=row.raised_at,
            cleared_at=row.cleared_at,
            status=AlarmStatus(row.status),
            raw_payload=json.loads(row.raw_payload),
        )

    async def upsert(self, alarm: AlarmRecord) -> None:
        """Insert or update an alarm record (upsert by alarm_id)."""
        result = await self._session.execute(
            select(AlarmRow).where(AlarmRow.alarm_id == alarm.alarm_id)
        )
        row = result.scalar_one_or_none()
        if row:
            row.status     = alarm.status.value
            row.cleared_at = alarm.cleared_at
            row.severity   = alarm.severity
            row.updated_at = datetime.utcnow()
            row.raw_payload = json.dumps(alarm.raw_payload)
        else:
            row = AlarmRow(
                alarm_id=alarm.alarm_id,
                affected_node=alarm.affected_node,
                alarm_type=alarm.alarm_type,
                severity=alarm.severity,
                source_system=alarm.source_system,
                raised_at=alarm.raised_at,
                cleared_at=alarm.cleared_at,
                status=alarm.status.value,
                raw_payload=json.dumps(alarm.raw_payload),
            )
            self._session.add(row)
        await self._session.commit()

    async def get_latest_for_node(
        self, node: str, alarm_type: Optional[str] = None
    ) -> Optional[AlarmRecord]:
        """Return the most-recently-raised alarm for a node (any status)."""
        stmt = (
            select(AlarmRow)
            .where(AlarmRow.affected_node == node)
            .order_by(AlarmRow.raised_at.desc())
            .limit(1)
        )
        if alarm_type:
            stmt = stmt.where(AlarmRow.alarm_type == alarm_type)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_active_for_node(self, node: str) -> list[AlarmRecord]:
        """Return all currently-active alarms for a node."""
        result = await self._session.execute(
            select(AlarmRow)
            .where(AlarmRow.affected_node == node, AlarmRow.status == AlarmStatus.ACTIVE.value)
            .order_by(AlarmRow.raised_at.desc())
        )
        return [self._to_domain(r) for r in result.scalars().all()]

    async def mark_cleared(self, alarm_id: str, cleared_at: Optional[datetime] = None) -> None:
        result = await self._session.execute(
            select(AlarmRow).where(AlarmRow.alarm_id == alarm_id)
        )
        row = result.scalar_one_or_none()
        if row:
            row.status     = AlarmStatus.CLEARED.value
            row.cleared_at = cleared_at or datetime.utcnow()
            row.updated_at = datetime.utcnow()
            await self._session.commit()
