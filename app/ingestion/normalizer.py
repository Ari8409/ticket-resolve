from typing import Any

from app.models.ticket import TicketIn, TicketPriority


# Field aliases: maps source field names → canonical field names
_TITLE_ALIASES = ["title", "summary", "subject", "name", "headline"]
_DESCRIPTION_ALIASES = ["description", "body", "content", "details", "message", "text", "issue"]
_PRIORITY_ALIASES = ["priority", "severity", "urgency", "importance"]
_CATEGORY_ALIASES = ["category", "type", "ticket_type", "issue_type", "label"]

_PRIORITY_MAP = {
    "low": TicketPriority.LOW,
    "p3": TicketPriority.LOW,
    "medium": TicketPriority.MEDIUM,
    "normal": TicketPriority.MEDIUM,
    "p2": TicketPriority.MEDIUM,
    "high": TicketPriority.HIGH,
    "p1": TicketPriority.HIGH,
    "critical": TicketPriority.CRITICAL,
    "urgent": TicketPriority.CRITICAL,
    "p0": TicketPriority.CRITICAL,
    "blocker": TicketPriority.CRITICAL,
}


def _find_field(payload: dict, aliases: list[str]) -> Any:
    for alias in aliases:
        val = payload.get(alias) or payload.get(alias.upper()) or payload.get(alias.lower())
        if val:
            return val
    return None


class TicketNormalizer:
    def normalize(self, raw: dict, source: str) -> TicketIn:
        title = _find_field(raw, _TITLE_ALIASES)
        description = _find_field(raw, _DESCRIPTION_ALIASES)

        # Fallback: use first long string value if no dedicated field found
        if not title or not description:
            for val in raw.values():
                if isinstance(val, str) and len(val) > 50:
                    if not description:
                        description = val
                    elif not title:
                        title = val[:80]

        title = (title or "Untitled ticket")[:200]
        description = description or title

        # Priority
        raw_priority = _find_field(raw, _PRIORITY_ALIASES)
        priority = TicketPriority.MEDIUM
        if raw_priority:
            priority = _PRIORITY_MAP.get(str(raw_priority).lower(), TicketPriority.MEDIUM)

        category = _find_field(raw, _CATEGORY_ALIASES)

        # Collect remaining fields as metadata
        known = set(_TITLE_ALIASES + _DESCRIPTION_ALIASES + _PRIORITY_ALIASES + _CATEGORY_ALIASES)
        metadata = {k: v for k, v in raw.items() if k not in known and not isinstance(v, dict)}

        return TicketIn(
            source=source,
            title=title,
            description=description,
            priority=priority,
            category=str(category) if category else None,
            metadata=metadata,
        )
