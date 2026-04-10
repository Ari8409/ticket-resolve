"""
Planned maintenance ingester — loads maintenance windows from:
  • JSON array / single object  (ITSM API response, ServiceNow export)
  • CSV export                  (Excel-derived schedules)
  • ICS / iCalendar             (Google Calendar, Outlook shared calendars)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.ingestion.telco.normalizer import _parse_timestamp
from app.maintenance.models import MaintenanceType, PlannedMaintenance

log = logging.getLogger(__name__)

_ID_ALIASES    = ["maintenance_id", "id", "change_id", "cr_number", "rfc", "change_request",
                   "sys_id", "number"]
_TITLE_ALIASES = ["title", "summary", "name", "short_description", "subject", "description_short"]
_START_ALIASES = ["start_time", "start", "start_date", "planned_start", "begins_at",
                   "dtstart", "start_datetime"]
_END_ALIASES   = ["end_time", "end", "end_date", "planned_end", "ends_at",
                   "dtend", "end_datetime"]
_NODES_ALIASES = ["affected_nodes", "nodes", "devices", "hosts", "elements",
                   "impacted_nodes", "ci_list", "configuration_items"]
_TYPE_ALIASES  = ["maintenance_type", "type", "change_type", "category"]
_DESC_ALIASES  = ["description", "details", "body", "notes", "long_description"]
_CONTACT_ALIASES = ["contact", "assigned_to", "owner", "engineer", "tech_contact"]
_REF_ALIASES   = ["external_ref", "cr_number", "change_number", "rfc", "ticket_ref"]

_TYPE_MAP: dict[str, MaintenanceType] = {
    "planned":       MaintenanceType.PLANNED,
    "standard":      MaintenanceType.PLANNED,
    "normal":        MaintenanceType.PLANNED,
    "emergency":     MaintenanceType.EMERGENCY,
    "expedited":     MaintenanceType.EMERGENCY,
    "change_freeze": MaintenanceType.CHANGE_FREEZE,
    "freeze":        MaintenanceType.CHANGE_FREEZE,
    "survey":        MaintenanceType.SURVEY,
    "inspection":    MaintenanceType.SURVEY,
}


def _find(d: dict, aliases: list[str]) -> Any:
    for a in aliases:
        for key in (a, a.upper(), a.lower()):
            v = d.get(key)
            if v not in (None, "", "null", "NULL"):
                return v
    return None


def _parse_nodes(raw: Any) -> list[str]:
    """Accept list, comma-separated string, or JSON string."""
    if isinstance(raw, list):
        return [str(n).strip() for n in raw if str(n).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(n).strip() for n in parsed if str(n).strip()]
        except (json.JSONDecodeError, ValueError):
            pass
        return [n.strip() for n in re.split(r"[,;|]", raw) if n.strip()]
    return []


def _normalise_record(raw: dict) -> PlannedMaintenance:
    maint_id    = str(_find(raw, _ID_ALIASES) or uuid.uuid4().hex[:12])
    title       = str(_find(raw, _TITLE_ALIASES) or "Untitled Maintenance")
    start_raw   = _find(raw, _START_ALIASES)
    end_raw     = _find(raw, _END_ALIASES)
    nodes_raw   = _find(raw, _NODES_ALIASES)
    type_raw    = _find(raw, _TYPE_ALIASES)
    description = str(_find(raw, _DESC_ALIASES) or "")
    contact     = str(_find(raw, _CONTACT_ALIASES) or "") or None
    ext_ref     = str(_find(raw, _REF_ALIASES) or "") or None

    start_time  = _parse_timestamp(start_raw) if start_raw else datetime.now(tz=timezone.utc)
    end_time    = _parse_timestamp(end_raw)   if end_raw   else start_time

    nodes = _parse_nodes(nodes_raw) if nodes_raw else []

    mtype_str = str(type_raw).lower().strip() if type_raw else "planned"
    mtype = _TYPE_MAP.get(mtype_str, MaintenanceType.PLANNED)

    return PlannedMaintenance(
        maintenance_id=maint_id,
        title=title[:256],
        maintenance_type=mtype,
        affected_nodes=nodes,
        start_time=start_time,
        end_time=end_time,
        description=description[:4000],
        contact=contact,
        external_ref=ext_ref,
    )


class MaintenanceIngester:
    """
    Parses planned maintenance schedules from multiple formats.

    Usage::

        ingester = MaintenanceIngester()
        windows = ingester.from_json(api_response_bytes)
        windows = ingester.from_csv(csv_bytes)
        windows = ingester.from_ics(ics_bytes)
    """

    def from_dict(self, payload: dict) -> PlannedMaintenance:
        return _normalise_record(payload)

    def from_json(self, raw: str | bytes | list | dict) -> list[PlannedMaintenance]:
        if isinstance(raw, (str, bytes)):
            data = json.loads(raw)
        else:
            data = raw
        records = data if isinstance(data, list) else [data]
        results: list[PlannedMaintenance] = []
        for i, item in enumerate(records):
            try:
                results.append(_normalise_record(item))
            except Exception as exc:
                log.warning("Maintenance record %d skipped: %s", i, exc)
        return results

    def from_csv(self, content: bytes) -> list[PlannedMaintenance]:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
        results: list[PlannedMaintenance] = []
        for i, row in enumerate(reader):
            try:
                results.append(_normalise_record(dict(row)))
            except Exception as exc:
                log.warning("Maintenance CSV row %d skipped: %s", i, exc)
        return results

    def from_ics(self, content: bytes) -> list[PlannedMaintenance]:
        """
        Parse iCalendar (.ics) format — each VEVENT becomes a maintenance window.
        Requires the `icalendar` package (optional dep).
        """
        try:
            import icalendar  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "icalendar package required for ICS parsing. "
                "Install with: pip install icalendar"
            )
        cal = icalendar.Calendar.from_ical(content)
        results: list[PlannedMaintenance] = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            try:
                nodes_str = str(component.get("LOCATION", ""))
                raw = {
                    "maintenance_id": str(component.get("UID", uuid.uuid4().hex[:12])),
                    "title":          str(component.get("SUMMARY", "Maintenance")),
                    "description":    str(component.get("DESCRIPTION", "")),
                    "start_time":     component.get("DTSTART").dt.isoformat(),
                    "end_time":       component.get("DTEND").dt.isoformat(),
                    "affected_nodes": nodes_str,
                    "contact":        str(component.get("ORGANIZER", "")),
                }
                results.append(_normalise_record(raw))
            except Exception as exc:
                log.warning("ICS VEVENT skipped: %s", exc)
        return results
