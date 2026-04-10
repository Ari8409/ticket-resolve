import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, SQLModel, select


# ---------------------------------------------------------------------------
# SQLModel table definitions
# ---------------------------------------------------------------------------

class TicketRow(SQLModel, table=True):
    __tablename__ = "tickets"

    ticket_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    source: str
    title: str
    description: str
    priority: str
    category: Optional[str] = None
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolution_summary: Optional[str] = None


class RecommendationRow(SQLModel, table=True):
    __tablename__ = "recommendations"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: str = Field(index=True)
    recommended_steps: str = "[]"      # JSON-encoded list[str]
    confidence_score: float = 0.0
    relevant_sops: str = "[]"           # JSON-encoded list[str]
    similar_ticket_ids: str = "[]"      # JSON-encoded list[str]
    escalation_required: bool = False
    reasoning: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------

_engine = None
_async_session = None


def init_engine(database_url: str):
    global _engine, _async_session
    _engine = create_async_engine(database_url, echo=False)
    _async_session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables():
    # Import all SQLModel table modules so their metadata is registered
    import app.storage.telco_repositories  # noqa: F401  — SOPRow, TelcoTicketRow, TelcoDispatchDecisionRow
    import app.alarms.store               # noqa: F401  — AlarmRow
    import app.maintenance.store          # noqa: F401  — MaintenanceRow
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


def get_session() -> AsyncSession:
    return _async_session()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class TicketRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, ticket_in, ticket_id: Optional[str] = None) -> str:
        from app.models.ticket import TicketIn
        row = TicketRow(
            ticket_id=ticket_id or str(uuid.uuid4()),
            source=ticket_in.source,
            title=ticket_in.title,
            description=ticket_in.description,
            priority=ticket_in.priority.value,
            category=ticket_in.category,
            status="pending",
            created_at=ticket_in.created_at,
            updated_at=datetime.utcnow(),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row.ticket_id

    async def update_status(self, ticket_id: str, status) -> None:
        result = await self._session.execute(select(TicketRow).where(TicketRow.ticket_id == ticket_id))
        row = result.scalar_one_or_none()
        if row:
            row.status = status.value if hasattr(status, "value") else status
            row.updated_at = datetime.utcnow()
            await self._session.commit()

    async def save_recommendation(self, ticket_id: str, result) -> None:
        rec = RecommendationRow(
            ticket_id=ticket_id,
            recommended_steps=json.dumps(result.recommended_steps),
            confidence_score=result.confidence_score,
            relevant_sops=json.dumps(result.relevant_sops),
            similar_ticket_ids=json.dumps(result.similar_ticket_ids),
            escalation_required=result.escalation_required,
            reasoning=result.reasoning,
        )
        self._session.add(rec)
        await self._session.commit()

    async def get_recommendation(self, ticket_id: str) -> Optional[dict]:
        result = await self._session.execute(
            select(RecommendationRow).where(RecommendationRow.ticket_id == ticket_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "ticket_id": ticket_id,
            "recommended_steps": json.loads(row.recommended_steps),
            "confidence_score": row.confidence_score,
            "relevant_sops": json.loads(row.relevant_sops),
            "similar_ticket_ids": json.loads(row.similar_ticket_ids),
            "escalation_required": row.escalation_required,
            "reasoning": row.reasoning,
            "created_at": row.created_at,
        }

    async def get_ticket(self, ticket_id: str) -> Optional[TicketRow]:
        result = await self._session.execute(select(TicketRow).where(TicketRow.ticket_id == ticket_id))
        return result.scalar_one_or_none()
