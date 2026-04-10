from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    FAILED = "failed"


class TicketIn(BaseModel):
    source: str
    title: str = Field(..., min_length=3)
    description: str = Field(..., min_length=10)
    priority: TicketPriority = TicketPriority.MEDIUM
    category: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TicketOut(BaseModel):
    ticket_id: str
    status: TicketStatus
    created_at: datetime
    recommendation_ready: bool = False


class TicketRecord(BaseModel):
    ticket_id: str
    source: str
    title: str
    description: str
    priority: TicketPriority
    category: Optional[str]
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    resolution_summary: Optional[str] = None
