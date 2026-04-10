"""
TelcoNormalizer — maps any raw dict (from email, CSV, or API) to TelcoTicketCreate.

Design
------
Two-pass normalisation:
  1. Field extraction  — walk alias lists to find each canonical field value.
  2. Inference         — when a field is still missing, infer it from the
                         description text using keyword/regex rules.

This keeps the normaliser deterministic and easy to extend: add entries to
the alias maps or inference tables without touching the core logic.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.telco_ticket import (
    FaultType,
    Severity,
    TelcoTicketCreate,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field alias tables
# Each list is checked in order; first non-empty value wins.
# ---------------------------------------------------------------------------

_TICKET_ID_ALIASES = [
    "ticket_id", "id", "ticket_number", "alarm_id", "alert_id",
    "incident_id", "event_id", "case_id", "ref",
]
_TIMESTAMP_ALIASES = [
    "timestamp", "created_at", "event_time", "alarm_time", "detection_time",
    "raised_at", "opened_at", "start_time", "date", "time",
]
_FAULT_TYPE_ALIASES = [
    "fault_type", "alarm_type", "alert_name", "event_type", "error_type",
    "fault_category", "issue_type", "alarm_category", "problem_type",
]
_NODE_ALIASES = [
    "affected_node", "node_id", "host", "hostname", "device", "element",
    "source", "network_element", "ne_id", "node", "target", "resource",
    "entity", "asset",
]
_SEVERITY_ALIASES = [
    "severity", "priority", "alarm_level", "alert_level", "urgency",
    "criticality", "impact", "level",
]
_DESCRIPTION_ALIASES = [
    "description", "details", "body", "message", "summary", "alarm_text",
    "event_description", "text", "content", "notes", "remark",
]
_STEPS_ALIASES = [
    "resolution_steps", "steps", "remedy", "resolution", "fix_steps",
    "action_items", "actions", "remediation", "recommended_actions",
]
_SOP_ALIASES = [
    "sop_id", "sop", "procedure_id", "kb_id", "runbook_id",
    "knowledge_base", "playbook_id",
]


# ---------------------------------------------------------------------------
# Fault-type inference: keyword/pattern → FaultType
# Checked in order; first match wins.
# ---------------------------------------------------------------------------

_FAULT_INFERENCE_RULES: list[tuple[re.Pattern, FaultType]] = [
    (re.compile(r"signal\s*loss|rssi|rsrp|rsrq|no\s*signal|low\s*signal|rf\s*loss|antenna", re.I), FaultType.SIGNAL_LOSS),
    (re.compile(r"node\s*down|host\s*down|device\s*down|unreachable|offline|not\s*respond|ping\s*fail|down\b", re.I), FaultType.NODE_DOWN),
    (re.compile(r"packet\s*loss|packet\s*drop|frame\s*drop|drops\b", re.I), FaultType.PACKET_LOSS),
    (re.compile(r"high\s*latency|latency|delay|rtt|jitter|response\s*time|slow\s*response|timeout", re.I), FaultType.LATENCY),
    (re.compile(r"congestion|bandwidth|traffic\s*spike|overload|capacity|throughput\s*limit", re.I), FaultType.CONGESTION),
    (re.compile(r"hardware|equipment\s*fail|disk\s*fail|power\s*fail|fan\s*fail|temperature|physical", re.I), FaultType.HARDWARE_FAILURE),
    (re.compile(r"config|misconfigur|wrong\s*config|invalid\s*config|provisioning\s*error|bgp\s*config", re.I), FaultType.CONFIGURATION_ERROR),
]


# ---------------------------------------------------------------------------
# Severity inference: keyword → Severity
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, Severity] = {
    # explicit labels
    "critical": Severity.CRITICAL, "sev0": Severity.CRITICAL, "sev1": Severity.CRITICAL,
    "p0": Severity.CRITICAL, "emergency": Severity.CRITICAL, "blocker": Severity.CRITICAL,
    "disaster": Severity.CRITICAL, "outage": Severity.CRITICAL,
    # high
    "high": Severity.HIGH, "sev2": Severity.HIGH, "p1": Severity.HIGH,
    "major": Severity.HIGH, "severe": Severity.HIGH,
    # medium
    "medium": Severity.MEDIUM, "sev3": Severity.MEDIUM, "p2": Severity.MEDIUM,
    "minor": Severity.MEDIUM, "warning": Severity.MEDIUM, "warn": Severity.MEDIUM,
    "moderate": Severity.MEDIUM, "average": Severity.MEDIUM,
    # low
    "low": Severity.LOW, "sev4": Severity.LOW, "sev5": Severity.LOW,
    "p3": Severity.LOW, "informational": Severity.LOW, "info": Severity.LOW,
    "notice": Severity.LOW, "trivial": Severity.LOW,
}

# Regex pattern that maps severity-indicative words inside description text
_SEVERITY_INFERENCE_RULES: list[tuple[re.Pattern, Severity]] = [
    (re.compile(r"full\s*outage|complete\s*outage|total\s*loss|emergency", re.I), Severity.CRITICAL),
    (re.compile(r"degraded|partial\s*outage|significant\s*impact", re.I), Severity.HIGH),
    (re.compile(r"intermittent|flapping|brief|temporary", re.I), Severity.MEDIUM),
]


# ---------------------------------------------------------------------------
# Node-ID extraction heuristic
# ---------------------------------------------------------------------------

# Common telco node naming patterns; searched in the full description text
_NODE_PATTERN = re.compile(
    r"\b("
    r"[A-Z]{1,6}-[A-Z0-9]{1,10}-\d{2,4}"   # e.g. BS-MUM-042, NODE-ATL-01
    r"|[A-Z]{2,6}\d{3,6}"                    # e.g. RTR001, ENB12345
    r"|(?:node|host|device|ne|bs|rtr|enb|gnb|olt|onu|bts)\s*[-_]?\s*\w{1,20}"  # labelled
    r")\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find(raw: dict, aliases: list[str]) -> Any:
    """Return first truthy value found under any alias (case-insensitive key lookup)."""
    for alias in aliases:
        for key in (alias, alias.upper(), alias.lower()):
            val = raw.get(key)
            if val is not None and val != "":
                return val
    return None


def _parse_timestamp(raw_ts: Any) -> datetime:
    """Best-effort ISO-8601 / epoch parse; falls back to utcnow()."""
    if isinstance(raw_ts, datetime):
        return raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
    if isinstance(raw_ts, (int, float)):
        return datetime.fromtimestamp(raw_ts, tz=timezone.utc)
    if isinstance(raw_ts, str):
        raw_ts = raw_ts.strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",    "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",         "%d/%m/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(raw_ts, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    log.debug("Could not parse timestamp %r — using utcnow()", raw_ts)
    return datetime.now(tz=timezone.utc)


def _infer_fault_type(text: str) -> FaultType:
    for pattern, fault in _FAULT_INFERENCE_RULES:
        if pattern.search(text):
            return fault
    return FaultType.UNKNOWN


def _infer_severity(text: str) -> Severity:
    for pattern, sev in _SEVERITY_INFERENCE_RULES:
        if pattern.search(text):
            return sev
    return Severity.MEDIUM


def _extract_node(text: str) -> Optional[str]:
    match = _NODE_PATTERN.search(text)
    return match.group(0).strip() if match else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TelcoNormalizer:
    """
    Converts an arbitrary raw dict into a validated TelcoTicketCreate.

    Usage::

        normalizer = TelcoNormalizer()
        ticket = normalizer.normalize(raw_dict, source="csv")
    """

    def normalize(self, raw: dict, source: str) -> TelcoTicketCreate:
        # ── 1. Extract each field using alias lookup ──────────────────────
        ticket_id   = _find(raw, _TICKET_ID_ALIASES)
        raw_ts      = _find(raw, _TIMESTAMP_ALIASES)
        raw_fault   = _find(raw, _FAULT_TYPE_ALIASES)
        raw_node    = _find(raw, _NODE_ALIASES)
        raw_sev     = _find(raw, _SEVERITY_ALIASES)
        raw_desc    = _find(raw, _DESCRIPTION_ALIASES)
        raw_steps   = _find(raw, _STEPS_ALIASES)
        sop_id      = _find(raw, _SOP_ALIASES)

        # ── 2. Coerce / infer each field ──────────────────────────────────
        timestamp = _parse_timestamp(raw_ts)

        description: str = str(raw_desc).strip() if raw_desc else ""
        if not description:
            # Concatenate all string values as a last resort
            description = " | ".join(
                str(v) for v in raw.values()
                if isinstance(v, str) and len(v) > 3
            )
        if len(description) < 10:
            description = f"[{source.upper()}] Raw alert: " + description

        # Fault type — direct value first, then infer from description
        fault_type = FaultType.UNKNOWN
        if raw_fault:
            normalised = str(raw_fault).strip().lower().replace(" ", "_").replace("-", "_")
            try:
                fault_type = FaultType(normalised)
            except ValueError:
                fault_type = _infer_fault_type(str(raw_fault) + " " + description)
        else:
            fault_type = _infer_fault_type(description)

        # Severity — alias lookup then description inference
        severity = Severity.MEDIUM
        if raw_sev:
            normalised_sev = str(raw_sev).strip().lower().replace(" ", "").replace("-", "")
            severity = _SEVERITY_MAP.get(normalised_sev, _infer_severity(description))
        else:
            severity = _infer_severity(description)

        # Affected node — alias lookup then regex extraction from description
        affected_node: str = str(raw_node).strip() if raw_node else ""
        if not affected_node:
            affected_node = _extract_node(description) or f"UNKNOWN-{source.upper()}"

        # Resolution steps
        steps: list[str] = []
        if raw_steps:
            if isinstance(raw_steps, list):
                steps = [str(s).strip() for s in raw_steps if str(s).strip()]
            else:
                steps = [s.strip() for s in str(raw_steps).splitlines() if s.strip()]

        # ── 3. Build and validate TelcoTicketCreate ───────────────────────
        kwargs: dict = dict(
            fault_type=fault_type,
            affected_node=affected_node[:128],
            severity=severity,
            description=description[:4000],
            resolution_steps=steps,
            sop_id=str(sop_id)[:64] if sop_id else None,
            timestamp=timestamp,
        )
        if ticket_id:
            kwargs["ticket_id"] = str(ticket_id)[:32]

        ticket = TelcoTicketCreate(**kwargs)
        log.debug(
            "Normalised [%s] → ticket_id=%s fault=%s severity=%s node=%s",
            source, ticket.ticket_id, ticket.fault_type, ticket.severity, ticket.affected_node,
        )
        return ticket
