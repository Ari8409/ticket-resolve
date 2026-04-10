"""SQLModel table + repository for planned maintenance windows."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, Index, SQLModel, select

from app.maintenance.models import MaintenanceType, PlannedMaintenance


# ---------------------------------------------------------------------------
# SQLModel table
# ---------------------------------------------------------------------------

class MaintenanceRow(SQLModel, table=True):
    __tablename__ = "planned_maintenance"

    maintenance_id:   str           = Field(primary_key=True, max_length=64)
    title:            str           = Field(..., max_length=256)
    maintenance_type: str           = Field(default=MaintenanceType.PLANNED.value, max_length=32)
    affected_nodes:   str           = Field(default="[]", max_length=4000)  # JSON list[str]
    start_time:       datetime      = Field(...)
    end_time:         datetime      = Field(...)
    description:      str           = Field(default="", max_length=4000)
    contact:          Optional[str] = Field(default=None, max_length=256)
    external_ref:     Optional[str] = Field(default=None, max_length=128)
    created_at:       datetime      = Field(default_factory=datetime.utcnow)
    updated_at:       datetime      = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("ix_pm_start", "start_time"),
        Index("ix_pm_end",   "end_time"),
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class MaintenanceStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: MaintenanceRow) -> PlannedMaintenance:
        return PlannedMaintenance(
            maintenance_id=row.maintenance_id,
            title=row.title,
            maintenance_type=MaintenanceType(row.maintenance_type),
            affected_nodes=json.loads(row.affected_nodes),
            start_time=row.start_time,
            end_time=row.end_time,
            description=row.description,
            contact=row.contact,
            external_ref=row.external_ref,
        )

    async def upsert(self, mw: PlannedMaintenance) -> None:
        result = await self._session.execute(
            select(MaintenanceRow).where(MaintenanceRow.maintenance_id == mw.maintenance_id)
        )
        row = result.scalar_one_or_none()
        if row:
            row.title            = mw.title
            row.maintenance_type = mw.maintenance_type.value
            row.affected_nodes   = json.dumps(mw.affected_nodes)
            row.start_time       = mw.start_time
            row.end_time         = mw.end_time
            row.description      = mw.description
            row.contact          = mw.contact
            row.external_ref     = mw.external_ref
            row.updated_at       = datetime.utcnow()
        else:
            self._session.add(MaintenanceRow(
                maintenance_id=mw.maintenance_id,
                title=mw.title,
                maintenance_type=mw.maintenance_type.value,
                affected_nodes=json.dumps(mw.affected_nodes),
                start_time=mw.start_time,
                end_time=mw.end_time,
                description=mw.description,
                contact=mw.contact,
                external_ref=mw.external_ref,
            ))
        await self._session.commit()

    async def get_active_windows(self, at: Optional[datetime] = None) -> list[PlannedMaintenance]:
        """Return all windows that overlap the given timestamp (default: now)."""
        when = at or datetime.utcnow()
        result = await self._session.execute(
            select(MaintenanceRow)
            .where(MaintenanceRow.start_time <= when, MaintenanceRow.end_time >= when)
            .order_by(MaintenanceRow.start_time)
        )
        return [self._to_domain(r) for r in result.scalars().all()]

    async def get_for_node(
        self, node: str, at: Optional[datetime] = None
    ) -> Optional[PlannedMaintenance]:
        """Return the first active window that covers `node`, or None."""
        windows = await self.get_active_windows(at)
        for w in windows:
            if w.covers_node(node):
                return w
        return None

    async def get_upcoming(self, hours_ahead: int = 24) -> list[PlannedMaintenance]:
        """Return windows starting within the next `hours_ahead` hours."""
        from datetime import timedelta
        now  = datetime.utcnow()
        cutoff = now + timedelta(hours=hours_ahead)
        result = await self._session.execute(
            select(MaintenanceRow)
            .where(MaintenanceRow.start_time >= now, MaintenanceRow.start_time <= cutoff)
            .order_by(MaintenanceRow.start_time)
        )
        return [self._to_domain(r) for r in result.scalars().all()]
