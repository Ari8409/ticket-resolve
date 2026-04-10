"""
NMS alarm ingester — parses alarm feeds from multiple source formats
into AlarmRecord objects ready for upsert into AlarmStore.

Supported formats
-----------------
  • Generic JSON / REST poll  (direct field mapping)
  • SNMP trap JSON translation (NetSNMP / pysnmp translated dicts)
  • Cisco NSO / IOS-XR streaming telemetry JSON
  • CSV alarm dumps            (batch historical loads)
  • Netcool / OMNIbus JSON export

Detection is automatic based on payload structure.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.alarms.models import AlarmRecord, AlarmStatus
from app.ingestion.telco.normalizer import _parse_timestamp

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field alias tables  (same pattern as TelcoNormalizer)
# ---------------------------------------------------------------------------

_ID_ALIASES        = ["alarm_id", "id", "alert_id", "event_id", "trap_id", "oid", "alarm_key"]
_NODE_ALIASES      = ["affected_node", "node", "hostname", "host", "device", "source",
                      "managed_object", "ne_id", "network_element", "element"]
_TYPE_ALIASES      = ["alarm_type", "type", "event_type", "trap_type", "alert_name",
                      "alertname", "problem_type", "fault_type"]
_SEVERITY_ALIASES  = ["severity", "priority", "alarm_level", "sev", "level", "criticality"]
_RAISED_ALIASES    = ["raised_at", "first_occurrence", "start_time", "event_time",
                      "timestamp", "created_at", "startsAt", "alarmRaisedTime"]
_CLEARED_ALIASES   = ["cleared_at", "clear_time", "end_time", "endsAt",
                      "alarmClearedTime", "resolved_at"]
_STATUS_ALIASES    = ["status", "alarm_state", "state", "alarm_status"]
_SOURCE_ALIASES    = ["source_system", "source", "system", "nms", "manager", "tool"]


def _find(d: dict, aliases: list[str]) -> Any:
    for alias in aliases:
        for key in (alias, alias.upper(), alias.lower()):
            val = d.get(key)
            if val not in (None, "", "null"):
                return val
    return None


_STATUS_MAP = {
    "active": AlarmStatus.ACTIVE, "firing": AlarmStatus.ACTIVE,
    "open": AlarmStatus.ACTIVE, "raised": AlarmStatus.ACTIVE,
    "cleared": AlarmStatus.CLEARED, "resolved": AlarmStatus.CLEARED,
    "ok": AlarmStatus.CLEARED, "normal": AlarmStatus.CLEARED,
    "acknowledged": AlarmStatus.ACKNOWLEDGED, "ack": AlarmStatus.ACKNOWLEDGED,
}


def _parse_status(raw: Any, cleared_at: Any) -> AlarmStatus:
    if cleared_at:
        return AlarmStatus.CLEARED
    if raw:
        return _STATUS_MAP.get(str(raw).lower().strip(), AlarmStatus.ACTIVE)
    return AlarmStatus.ACTIVE


# ---------------------------------------------------------------------------
# Format adapters
# ---------------------------------------------------------------------------

def _adapt_netcool(payload: dict) -> dict:
    """Netcool/OMNIbus JSON alert schema."""
    return {
        "alarm_id":      payload.get("Identifier", ""),
        "affected_node": payload.get("Node", ""),
        "alarm_type":    payload.get("AlertGroup", ""),
        "severity":      str(payload.get("Severity", "3")),
        "raised_at":     payload.get("FirstOccurrence", ""),
        "cleared_at":    payload.get("ClearTime") or None,
        "status":        "cleared" if payload.get("ClearTime") else "active",
        "source_system": "netcool",
    }


def _adapt_prometheus_alert(payload: dict) -> dict:
    """Single Prometheus alert object (from AlertManager webhook)."""
    labels      = payload.get("labels", {})
    annotations = payload.get("annotations", {})
    ends_at     = payload.get("endsAt", "")
    cleared     = ends_at and not ends_at.startswith("0001")
    return {
        "alarm_id":      labels.get("alertname", "") + "_" + labels.get("instance", ""),
        "affected_node": labels.get("instance") or labels.get("node") or labels.get("host", ""),
        "alarm_type":    labels.get("alertname", ""),
        "severity":      labels.get("severity", "warning"),
        "raised_at":     payload.get("startsAt", ""),
        "cleared_at":    ends_at if cleared else None,
        "status":        "cleared" if cleared else "active",
        "source_system": "prometheus",
    }


def _detect_format(payload: dict) -> str:
    if "Identifier" in payload and "AlertGroup" in payload:
        return "netcool"
    if "labels" in payload and "startsAt" in payload:
        return "prometheus"
    return "generic"


def _normalise_single(raw: dict, source_system: str = "nms") -> AlarmRecord:
    """Convert any raw dict into an AlarmRecord."""
    fmt = _detect_format(raw)
    if fmt == "netcool":
        raw = _adapt_netcool(raw)
    elif fmt == "prometheus":
        raw = _adapt_prometheus_alert(raw)

    alarm_id      = str(_find(raw, _ID_ALIASES) or uuid.uuid4().hex[:12])
    affected_node = str(_find(raw, _NODE_ALIASES) or "UNKNOWN")
    alarm_type    = str(_find(raw, _TYPE_ALIASES) or "unknown")
    severity      = str(_find(raw, _SEVERITY_ALIASES) or "medium")
    raised_raw    = _find(raw, _RAISED_ALIASES)
    cleared_raw   = _find(raw, _CLEARED_ALIASES)
    status_raw    = _find(raw, _STATUS_ALIASES)
    src           = str(_find(raw, _SOURCE_ALIASES) or source_system)

    raised_at  = _parse_timestamp(raised_raw) if raised_raw else datetime.now(tz=timezone.utc)
    cleared_at = _parse_timestamp(cleared_raw) if cleared_raw else None
    status     = _parse_status(status_raw, cleared_at)

    return AlarmRecord(
        alarm_id=alarm_id,
        affected_node=affected_node.strip()[:128],
        alarm_type=alarm_type.strip()[:64],
        severity=severity.strip()[:16],
        source_system=src[:64],
        raised_at=raised_at,
        cleared_at=cleared_at,
        status=status,
        raw_payload=raw,
    )


# ---------------------------------------------------------------------------
# Public ingester
# ---------------------------------------------------------------------------

class AlarmIngester:
    """
    Parses NMS alarm feeds into AlarmRecord lists.

    Usage::

        ingester = AlarmIngester()

        # From a REST poll response (list of dicts)
        alarms = ingester.from_json(response_body)

        # From a single webhook alert
        alarm = ingester.from_dict(payload)

        # From a CSV dump
        alarms = ingester.from_csv(csv_bytes)
    """

    def from_dict(self, payload: dict, source_system: str = "nms") -> AlarmRecord:
        return _normalise_single(payload, source_system)

    def from_json(self, raw: str | bytes | list | dict, source_system: str = "nms") -> list[AlarmRecord]:
        if isinstance(raw, (str, bytes)):
            data = json.loads(raw)
        else:
            data = raw

        # Prometheus AlertManager envelope
        if isinstance(data, dict) and "alerts" in data:
            records = data["alerts"]
        elif isinstance(data, list):
            records = data
        else:
            records = [data]

        results: list[AlarmRecord] = []
        for i, item in enumerate(records):
            try:
                results.append(_normalise_single(item, source_system))
            except Exception as exc:
                log.warning("Alarm item %d skipped: %s", i, exc)
        return results

    def from_csv(self, content: bytes, source_system: str = "nms") -> list[AlarmRecord]:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
        results: list[AlarmRecord] = []
        for i, row in enumerate(reader):
            try:
                results.append(_normalise_single(dict(row), source_system))
            except Exception as exc:
                log.warning("Alarm CSV row %d skipped: %s", i, exc)
        return results
