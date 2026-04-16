"""
Telco-domain ticket models.

Aligned with the CTTS (Customer Trouble Ticket System) data schema used
in the NOC daily ticket exports. All fields reflect real column names from
the CTTS Excel dump (27 Nov – 4 Dec 2025).

Lifecycle:
  TelcoTicketCreate  → validated input (API / ingestion / CTTS import)
  TelcoTicketRead    → API response (includes all DB-generated fields)
  TelcoTicketUpdate  → partial update payload (status, resolution_steps)
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class FaultType(str, Enum):
    # Generic network faults
    SIGNAL_LOSS         = "signal_loss"
    LATENCY             = "latency"
    NODE_DOWN           = "node_down"
    PACKET_LOSS         = "packet_loss"
    CONGESTION          = "congestion"
    HARDWARE_FAILURE    = "hardware_failure"
    CONFIGURATION_ERROR = "configuration_error"
    # RAN / Ericsson-specific (aligned with classifier taxonomy)
    SYNC_REFERENCE_QUALITY      = "sync_reference_quality"
    SYNC_TIME_PHASE_ACCURACY    = "sync_time_phase_accuracy"
    SERVICE_UNAVAILABLE         = "service_unavailable"
    SW_ERROR                    = "sw_error"
    RESOURCE_ACTIVATION_TIMEOUT = "resource_activation_timeout"
    UNKNOWN                     = "unknown"


class Severity(str, Enum):
    """
    Maps to the CTTS "Priority" column.

    CTTS value → Severity
    -----------------------
    Critical   → CRITICAL
    Major      → MAJOR
    Minor      → MINOR
    Info       → INFO
    """
    INFO     = "info"
    MINOR    = "minor"
    MEDIUM   = "medium"    # kept for backward compatibility / generic tickets
    LOW      = "low"       # kept for backward compatibility
    MAJOR    = "major"
    HIGH     = "high"      # kept for backward compatibility
    CRITICAL = "critical"


class TelcoTicketStatus(str, Enum):
    """
    Maps to the CTTS "Status" column.

    CTTS value → TelcoTicketStatus
    --------------------------------
    Assigned   → ASSIGNED
    Cleared    → CLEARED
    Closed     → CLOSED
    Pending    → PENDING
    (+ internal pipeline statuses below)
    """
    OPEN           = "open"
    ASSIGNED       = "assigned"
    PENDING        = "pending"
    IN_PROGRESS    = "in_progress"
    CLEARED        = "cleared"
    RESOLVED       = "resolved"
    CLOSED         = "closed"
    ESCALATED      = "escalated"
    FAILED         = "failed"           # internal: pipeline error during processing
    PENDING_REVIEW = "pending_review"   # flagged: no SOP/history match — needs human triage


class NetworkType(str, Enum):
    """Maps to CTTS "Network Type" column."""
    G2         = "2G"
    G3         = "3G"
    G4         = "4G"
    G5         = "5G"
    HUAWEI_CE  = "Huawei_CE"
    UNKNOWN    = ""


class ObjectClass(str, Enum):
    """
    Maps to CTTS "H-Fld-ObjectClass" column.
    A1 = Critical alarm class, A2 = Major alarm class.
    """
    A1            = "A1"
    A2            = "A2"
    A2_MNOC       = "A2_MNOC"
    MOB_RADIO_DOT = "MOB_RADIO_DOT"
    UNKNOWN       = ""


# ---------------------------------------------------------------------------
# Shared field annotations
# ---------------------------------------------------------------------------

TicketIdField     = Annotated[str, Field(default_factory=lambda: f"TKT-{uuid.uuid4().hex[:8].upper()}")]
AffectedNodeField = Annotated[str, Field(..., min_length=1, max_length=128, examples=["LTE_ENB_780321", "5G_GNB_1039321"])]
DescriptionField  = Annotated[str, Field(..., min_length=5, max_length=4000)]
SOPIdField        = Annotated[Optional[str], Field(default=None, max_length=64)]


# ---------------------------------------------------------------------------
# Helper — parse description into structured fields
# ---------------------------------------------------------------------------

_DESC_RE = re.compile(
    r"^(?P<node_id>[^*]+)\*"
    r"(?P<alarm_category>[^/]+)/(?P<alarm_name>[^*]+)\*"
    r"(?P<alarm_severity_code>\d+)\*",
    re.MULTILINE,
)

# Normalise non-standard spaced alarm categories (e.g. "Equipment Alarm") to
# the camelCase form used throughout the CTTS schema and SOP metadata.
_ALARM_CATEGORY_MAP: dict[str, str] = {
    "equipment alarm":          "equipmentAlarm",
    "communications alarm":     "communicationsAlarm",
    "processing error alarm":   "processingErrorAlarm",
    "performance alarm":        "performanceAlarm",
    "environmental alarm":      "environmentalAlarm",
    "quality of service alarm": "qualityOfServiceAlarm",
}

# Strip Ericsson-specific "UNKNOWN/" or any ALL-CAPS MO-type prefix that
# precedes the real alarm name in the alarm_name capture group.
# e.g. "UNKNOWN/DigitalCable_CableFailure" → "DigitalCable_CableFailure"
_ALARM_NAME_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9_]*/")


def _parse_ctts_description(description: str) -> dict:
    """
    Extract structured fields from CTTS description format:
      {NodeID}*{alarmCategory}/{alarmName}*{severityCode}*{shortText}\\n\\n{longText}

    Handles two non-standard variants observed in 3G/legacy CTTS exports:
    1. Spaced alarm categories  — "Equipment Alarm" → normalised to "equipmentAlarm"
    2. Sub-category prefixes    — "UNKNOWN/DigitalCable_CableFailure" → "DigitalCable_CableFailure"

    Returns a dict of parsed fields (all optional — returns {} on no match).
    """
    m = _DESC_RE.match(description.strip())
    if not m:
        return {}

    # Normalise alarm_category: map spaced legacy forms to camelCase
    category_raw = m.group("alarm_category").strip()
    alarm_category = _ALARM_CATEGORY_MAP.get(category_raw.lower(), category_raw)

    # Strip leading ALL-CAPS MO-type prefix from alarm_name (e.g. "UNKNOWN/")
    alarm_name_raw = m.group("alarm_name").strip()
    alarm_name = _ALARM_NAME_PREFIX_RE.sub("", alarm_name_raw)

    return {
        "node_id":             m.group("node_id").strip(),
        "alarm_category":      alarm_category,
        "alarm_name":          alarm_name,
        "alarm_severity_code": m.group("alarm_severity_code").strip(),
    }


# ---------------------------------------------------------------------------
# Create (input) model
# ---------------------------------------------------------------------------

class TelcoTicketCreate(BaseModel):
    """
    Payload accepted by POST /telco-tickets/ or produced by the CTTS importer.

    Core fields (fault_type, affected_node, severity, description) are required.
    All CTTS operational fields are optional so the model can be used for both
    manually-created tickets and full CTTS imports.
    """

    # --- Identity ---
    ticket_id: str = Field(
        default_factory=lambda: f"TKT-{uuid.uuid4().hex[:8].upper()}",
        description="Auto-generated if omitted. Format: TKT-<8 hex chars>.",
    )
    ctts_ticket_number: Optional[int] = Field(
        default=None,
        description="Original CTTS ticket number (Ticket Number column in the dump).",
        examples=[1617827],
    )

    # --- Timestamps ---
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC time the fault was detected. Defaults to now.",
    )
    event_start_time: Optional[datetime] = Field(
        default=None,
        description="CTTS Event Start Time — when the alarm was first raised.",
    )
    event_end_time: Optional[datetime] = Field(
        default=None,
        description="CTTS Event End Time — when the alarm cleared.",
    )
    modified_date: Optional[datetime] = Field(
        default=None,
        description="CTTS Modified Date — last update timestamp on the ticket.",
    )

    # --- Core fault fields ---
    fault_type: FaultType = Field(
        default=FaultType.UNKNOWN,
        description="Classification of the network fault (set by classifier pipeline).",
        examples=["hardware_failure", "node_down", "sync_reference_quality"],
    )
    affected_node: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Primary node identifier. For CTTS imports this is the Location ID+.",
        examples=["LTE_ENB_780321", "5G_GNB_1039321", "Rnc15_2650"],
    )
    severity: Severity = Field(
        default=Severity.MAJOR,
        description="Ticket priority/severity. Maps from CTTS Priority column.",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=4000,
        description="Full CTTS description text including alarm name and details.",
    )

    # --- Parsed alarm fields (auto-populated from description if not provided) ---
    node_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Node ID parsed from CTTS description (e.g. LTE_ENB_780321).",
    )
    alarm_category: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Alarm category from description (e.g. equipmentAlarm, communicationsAlarm).",
    )
    alarm_name: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Alarm name from description (e.g. HW Fault, Link Failure, Heartbeat Failure).",
    )
    alarm_severity_code: Optional[str] = Field(
        default=None,
        max_length=8,
        description="Numeric severity code from description field (e.g. '1').",
    )

    # --- Assignment & ownership ---
    title: Optional[str] = Field(
        default=None,
        max_length=256,
        description="CTTS Title field (e.g. 'A2 LTE_ENB_780321').",
    )
    assignment_profile: Optional[str] = Field(
        default=None,
        max_length=128,
        description="CTTS Assignment Profile (e.g. 'Mobile | BSM (East)').",
    )
    group: Optional[str] = Field(
        default=None,
        max_length=64,
        description="CTTS Group (e.g. 'ATO-BSM').",
    )
    object_class: Optional[str] = Field(
        default=None,
        max_length=32,
        description="CTTS H-Fld-ObjectClass: A1 (critical) or A2 (major).",
        examples=["A1", "A2", "A2_MNOC"],
    )
    owner_profile: Optional[str] = Field(
        default=None,
        max_length=128,
        description="CTTS Owner Profile (e.g. 'Mobile | BSM').",
    )
    owner_profile_group: Optional[str] = Field(
        default=None,
        max_length=128,
        description="CTTS Owner Profile (group) (e.g. 'Tier2/FieldOps').",
    )
    resolved_group: Optional[str] = Field(
        default=None,
        max_length=128,
        description="CTTS Resolved Group — team that closed the ticket.",
    )
    last_ack_by: Optional[str] = Field(
        default=None,
        max_length=128,
        description="CTTS Last Ack By — last person/system to acknowledge the alarm.",
    )
    resolved_person: Optional[str] = Field(
        default=None,
        max_length=128,
        description="CTTS Resolved Person — engineer or system that resolved the ticket.",
    )

    # --- Source & categorisation ---
    source: Optional[str] = Field(
        default=None,
        max_length=64,
        description="CTTS Source (e.g. 'Network', 'Customer').",
    )
    category_group: Optional[str] = Field(
        default=None,
        max_length=64,
        description="CTTS Category_Group (e.g. 'Non-Core', 'Core').",
    )
    network_type: Optional[str] = Field(
        default=None,
        max_length=16,
        description="CTTS Network Type: '3G', '4G', '5G', 'Huawei_CE'.",
        examples=["4G", "5G", "3G"],
    )
    mobile_or_fixed: Optional[str] = Field(
        default=None,
        max_length=32,
        description="CTTS Mobile or Fixed Group (e.g. 'Mobile Group', 'Fixed Group').",
    )

    # --- Location ---
    location_details: Optional[str] = Field(
        default=None,
        max_length=256,
        description="CTTS Location Details — site address.",
        examples=["209 Hougang Street 21", "1 Tuas South Street 12"],
    )
    location_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="CTTS Location ID+ — site or node identifier.",
        examples=["780321", "735557"],
    )

    # --- Resolution ---
    primary_cause: Optional[str] = Field(
        default=None,
        max_length=256,
        description="CTTS Primary Cause (e.g. 'Power Fault', 'Planned Activity', 'Hardware Fault').",
    )
    remarks: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="CTTS Remarks — free-text engineer notes.",
    )
    resolution: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="CTTS Resolution — how the ticket was resolved.",
    )
    resolution_code: Optional[str] = Field(
        default=None,
        max_length=256,
        description="CTTS Resolution Code — standardised resolution category.",
        examples=["Reset ELR", "Auto-restoration", "Self-restored after Ericsson Planned Activity"],
    )
    resolution_steps: list[str] = Field(
        default_factory=list,
        description="Ordered steps taken or recommended to resolve the fault.",
    )
    sop_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Reference to the SOP applied. Nullable.",
    )

    @field_validator("resolution_steps", mode="before")
    @classmethod
    def coerce_steps_to_list(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.splitlines() if s.strip()]
        return v  # type: ignore[return-value]

    @model_validator(mode="after")
    def auto_parse_description(self) -> "TelcoTicketCreate":
        """
        If node_id / alarm_category / alarm_name are absent, try to parse
        them from the CTTS-formatted description field.
        """
        if not any([self.node_id, self.alarm_category, self.alarm_name]):
            parsed = _parse_ctts_description(self.description)
            if parsed:
                if not self.node_id:
                    object.__setattr__(self, "node_id", parsed.get("node_id"))
                if not self.alarm_category:
                    object.__setattr__(self, "alarm_category", parsed.get("alarm_category"))
                if not self.alarm_name:
                    object.__setattr__(self, "alarm_name", parsed.get("alarm_name"))
                if not self.alarm_severity_code:
                    object.__setattr__(self, "alarm_severity_code", parsed.get("alarm_severity_code"))
        # Back-fill affected_node from node_id if not explicitly set
        if self.node_id and self.affected_node in ("", "UNKNOWN"):
            object.__setattr__(self, "affected_node", self.node_id)
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "ctts_ticket_number": 1617847,
                "affected_node": "LTE_ENB_781561",
                "severity": "critical",
                "network_type": "4G",
                "description": "LTE_ENB_781561*communicationsAlarm/Heartbeat Failure*1*Heartbeat Failure\n\nHeartbeat Failure Unknown",
                "event_start_time": "2025-11-27T00:58:00",
                "location_details": "1 Tuas South Street 12",
                "location_id": "781561",
                "assignment_profile": "Mobile | BSM (West)",
                "group": "ATO-BSM",
                "object_class": "A1",
                "primary_cause": "Power Fault",
                "resolution_code": "Reset ELR",
                "resolved_person": "jumari.binali",
            }
        }
    }


# ---------------------------------------------------------------------------
# Read (response) model
# ---------------------------------------------------------------------------

class TelcoTicketRead(BaseModel):
    """Full ticket representation returned by the API."""

    ticket_id:             str
    ctts_ticket_number:    Optional[int]
    timestamp:             datetime
    fault_type:            FaultType
    affected_node:         str
    severity:              Severity
    status:                TelcoTicketStatus
    description:           str
    # Parsed alarm fields
    node_id:               Optional[str]
    alarm_category:        Optional[str]
    alarm_name:            Optional[str]
    alarm_severity_code:   Optional[str]
    # CTTS operational fields
    title:                 Optional[str]
    assignment_profile:    Optional[str]
    group:                 Optional[str]
    object_class:          Optional[str]
    owner_profile:         Optional[str]
    owner_profile_group:   Optional[str]
    resolved_group:        Optional[str]
    source:                Optional[str]
    category_group:        Optional[str]
    network_type:          Optional[str]
    mobile_or_fixed:       Optional[str]
    event_start_time:      Optional[datetime]
    event_end_time:        Optional[datetime]
    location_details:      Optional[str]
    location_id:           Optional[str]
    primary_cause:         Optional[str]
    remarks:               Optional[str]
    resolution:            Optional[str]
    resolution_code:       Optional[str]
    last_ack_by:           Optional[str]
    resolved_person:       Optional[str]
    modified_date:         Optional[datetime]
    # Pipeline fields
    resolution_steps:      list[str]
    sop_id:                Optional[str]
    created_at:            datetime
    updated_at:            datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Update (patch) model
# ---------------------------------------------------------------------------

class TelcoTicketUpdate(BaseModel):
    """Fields that may be updated after creation."""

    status:           Optional[TelcoTicketStatus] = None
    resolution_steps: Optional[list[str]]         = None
    sop_id:           Optional[str]               = Field(default=None, max_length=64)
    description:      Optional[str]               = Field(default=None, min_length=5, max_length=4000)
    primary_cause:    Optional[str]               = Field(default=None, max_length=256)
    remarks:          Optional[str]               = Field(default=None, max_length=2000)
    resolution:       Optional[str]               = Field(default=None, max_length=1000)
    resolution_code:  Optional[str]               = Field(default=None, max_length=256)
    resolved_group:   Optional[str]               = Field(default=None, max_length=128)
    resolved_person:  Optional[str]               = Field(default=None, max_length=128)

    model_config = {"extra": "forbid"}
