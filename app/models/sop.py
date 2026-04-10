"""
SOP domain models.

SOPRecord      — structured representation of a single SOP parsed from markdown.
                 This is the canonical in-memory form used by SOPKnowledgeBase.

SOPDocument    — lightweight document model (legacy, used by SOPLoader for generic files).
SOPChunk       — chunk produced by splitting an SOPDocument for Chroma indexing.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SOPRecord(BaseModel):
    """
    Structured representation of a Standard Operating Procedure.

    All six core fields are required for a valid SOP.  They are either parsed
    from YAML frontmatter (preferred) or extracted from markdown section
    headers (fallback — see app/sop/parser.py).

    Fields
    ------
    sop_id
        Unique identifier.  Format convention: ``SOP-<DOMAIN>-<NNN>``
        e.g. ``SOP-RF-001``, ``SOP-RAN-003``, ``SOP-HW-007``.
    fault_category
        The primary fault type this SOP addresses.  Should match one of
        the FaultType enum values (signal_loss, latency, node_down,
        sync_reference_quality, resource_activation_timeout, …)
        but accepts free-text for custom categories.
    preconditions
        Ordered list of conditions that must be true before the engineer
        begins the procedure (access, safety, alarm state, etc.).
    resolution_steps
        Ordered list of actionable steps.  Each item is a complete
        instruction — no sub-bullets.
    escalation_path
        Who to contact and in what order if steps do not resolve the fault
        within the estimated time.  Free-text, e.g.
        "L1 NOC → L2 RF Engineer → Vendor TAC (Ericsson SLA-001)".
        For Ericsson RAN OPIs this is typically
        "Consult the next level of maintenance support".
    estimated_resolution_time
        Human-readable time budget, e.g. "30–60 minutes" or
        "2 hours (remote); 8 hours if physical replacement required".

    RAN-specific optional fields
    -----------------------------
    managed_object
        Ericsson Managed Object class that raised the alarm, e.g.
        ``RadioEquipmentClockReference``, ``ENodeBFunction``,
        ``NRSectorCarrier``.  Used to discriminate between remedy
        action branches within the same alarm type.
    additional_text
        The "Additional Text" field from the Ericsson alarm OPI table.
        Different additional texts map to different remedy procedures
        for the same alarm name.
    alarm_severity
        ``"primary"`` — root-cause alarm that must be cleared directly.
        ``"secondary"`` — symptom alarm caused by a correlated primary
        alarm; resolver must identify and clear the primary first.
    on_site_required
        Whether the remedy requires a field engineer on site.
        Derived from the "On-site Activities" column in the OPI table.
    secondary_alarm_pointer
        For secondary alarms: the name of the correlated primary alarm
        that must be resolved first (e.g. "Sync Reference Quality Level
        Too Low" for a Service Unavailable secondary alarm).
    """

    sop_id:                    str
    fault_category:            str
    preconditions:             list[str]        = Field(default_factory=list)
    resolution_steps:          list[str]        = Field(default_factory=list)
    escalation_path:           str
    estimated_resolution_time: str

    # RAN / Ericsson OPI fields (optional — absent for generic SOPs)
    managed_object:           str  = ""
    additional_text:          str  = ""
    alarm_severity:           str  = "primary"   # "primary" | "secondary"
    on_site_required:         bool = False
    secondary_alarm_pointer:  str  = ""

    # Derived / storage metadata
    title:       str            = ""
    source_path: str            = ""
    raw_content: str            = Field(default="", repr=False)

    @field_validator("sop_id")
    @classmethod
    def sop_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("sop_id must not be blank")
        return v.strip()

    @field_validator("fault_category")
    @classmethod
    def fault_category_normalised(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_")

    @field_validator("resolution_steps", "preconditions", mode="before")
    @classmethod
    def coerce_to_list(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.splitlines() if s.strip()]
        return v  # type: ignore[return-value]

    @property
    def step_count(self) -> int:
        return len(self.resolution_steps)

    @property
    def precondition_count(self) -> int:
        return len(self.preconditions)


class SOPDocument(BaseModel):
    """Lightweight document model used by SOPLoader for unstructured files."""
    sop_id:   str
    title:    str
    content:  str
    category: Optional[str] = None
    doc_path: Optional[str] = None
    tags:     list[str]     = []


class SOPChunk(BaseModel):
    """Chunk produced by splitting an SOPDocument for Chroma indexing."""
    chunk_id:    str
    sop_id:      str
    title:       str
    content:     str
    chunk_index: int
    doc_path:    Optional[str] = None
    category:    Optional[str] = None
