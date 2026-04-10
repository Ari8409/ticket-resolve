"""
Telco-domain ticket models.

Covers the full lifecycle:
  TelcoTicketCreate  → validated input (API / ingestion)
  TelcoTicketRead    → API response (includes all DB-generated fields)
  TelcoTicketUpdate  → partial update payload (status, resolution_steps)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class FaultType(str, Enum):
    SIGNAL_LOSS        = "signal_loss"
    LATENCY            = "latency"
    NODE_DOWN          = "node_down"
    PACKET_LOSS        = "packet_loss"
    CONGESTION         = "congestion"
    HARDWARE_FAILURE   = "hardware_failure"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN            = "unknown"


class Severity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class TelcoTicketStatus(str, Enum):
    OPEN        = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED    = "resolved"
    CLOSED      = "closed"
    ESCALATED   = "escalated"


# ---------------------------------------------------------------------------
# Shared field annotations
# ---------------------------------------------------------------------------

TicketIdField      = Annotated[str, Field(default_factory=lambda: f"TKT-{uuid.uuid4().hex[:8].upper()}")]
AffectedNodeField  = Annotated[str, Field(..., min_length=1, max_length=128,  examples=["NODE-ATL-01", "BS-MUM-042"])]
DescriptionField   = Annotated[str, Field(..., min_length=10, max_length=4000)]
SOPIdField         = Annotated[Optional[str], Field(default=None, max_length=64, examples=["SOP-DB-001", "SOP-NET-003"])]


# ---------------------------------------------------------------------------
# Create (input) model
# ---------------------------------------------------------------------------

class TelcoTicketCreate(BaseModel):
    """Payload accepted by POST /telco-tickets/"""

    ticket_id: str = Field(
        default_factory=lambda: f"TKT-{uuid.uuid4().hex[:8].upper()}",
        description="Auto-generated if omitted. Format: TKT-<8 hex chars>.",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC time the fault was detected. Defaults to now.",
    )
    fault_type: FaultType = Field(
        ...,
        description="Classification of the network fault.",
        examples=["signal_loss", "node_down"],
    )
    affected_node: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Identifier of the impacted network node, base station, or router.",
        examples=["NODE-ATL-01", "BS-MUM-042", "RTR-LON-CORE-03"],
    )
    severity: Severity = Field(
        ...,
        description="Impact severity of the fault.",
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=4000,
        description="Human-readable description of the fault, symptoms, and impact.",
    )
    resolution_steps: list[str] = Field(
        default_factory=list,
        description="Ordered list of steps taken or recommended to resolve the fault.",
        examples=[["Restart BGP session", "Verify route tables", "Notify NOC"]],
    )
    sop_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Reference to the Standard Operating Procedure applied. Nullable.",
        examples=["SOP-NET-003"],
    )

    @field_validator("resolution_steps", mode="before")
    @classmethod
    def coerce_steps_to_list(cls, v: object) -> list[str]:
        """Accept a newline-delimited string as well as a proper list."""
        if isinstance(v, str):
            return [s.strip() for s in v.splitlines() if s.strip()]
        return v  # type: ignore[return-value]

    @model_validator(mode="after")
    def escalate_critical_faults(self) -> "TelcoTicketCreate":
        """Warn callers when a CRITICAL node_down has no SOP linked."""
        if self.severity == Severity.CRITICAL and self.fault_type == FaultType.NODE_DOWN and not self.sop_id:
            # Not an error — callers may link an SOP later — but flag it in metadata
            object.__setattr__(self, "_missing_sop_warning", True)
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "fault_type": "signal_loss",
                "affected_node": "BS-MUM-042",
                "severity": "high",
                "description": "Base station BS-MUM-042 reporting -110 dBm RSSI. 3,200 subscribers affected in the Mumbai North sector.",
                "resolution_steps": [
                    "Verify antenna alignment via NMS",
                    "Check feeder cable integrity",
                    "Reboot RRU if alignment is nominal",
                ],
                "sop_id": "SOP-RF-007",
            }
        }
    }


# ---------------------------------------------------------------------------
# Read (response) model
# ---------------------------------------------------------------------------

class TelcoTicketRead(BaseModel):
    """Full ticket representation returned by the API."""

    ticket_id:        str
    timestamp:        datetime
    fault_type:       FaultType
    affected_node:    str
    severity:         Severity
    status:           TelcoTicketStatus
    description:      str
    resolution_steps: list[str]
    sop_id:           Optional[str]
    created_at:       datetime
    updated_at:       datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Update (patch) model
# ---------------------------------------------------------------------------

class TelcoTicketUpdate(BaseModel):
    """Fields that may be updated after creation."""

    status:           Optional[TelcoTicketStatus] = None
    resolution_steps: Optional[list[str]]         = None
    sop_id:           Optional[str]               = Field(default=None, max_length=64)
    description:      Optional[str]               = Field(default=None, min_length=10, max_length=4000)

    model_config = {"extra": "forbid"}
