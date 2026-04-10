"""
Email ingester for telco alert tickets.

Supports three email alert formats via template detection:
  • Nagios / Icinga  — "** PROBLEM alert - <host>/<service> is DOWN **"
  • Zabbix           — "Problem: <trigger> on <host>"
  • Generic NOC      — structured key:value body or plain prose alert

Each format extracts: timestamp, fault type, affected node, severity,
description, and resolution steps (if present). Unrecognised fields are
passed to TelcoNormalizer for best-effort mapping.

Input: raw RFC-2822 email bytes (e.g. from IMAP fetch or .eml file).
"""
from __future__ import annotations

import email
import logging
import re
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Optional

from app.ingestion.telco.normalizer import TelcoNormalizer, _infer_fault_type, _infer_severity
from app.models.telco_ticket import FaultType, Severity, TelcoTicketCreate

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML → plain text stripper
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return "\n".join(p.strip() for p in self._parts if p.strip())


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


# ---------------------------------------------------------------------------
# Template matchers
# ---------------------------------------------------------------------------

# Nagios PROBLEM alert subject
_NAGIOS_SUBJECT_RE = re.compile(
    r"\*\*\s*(?P<state>PROBLEM|RECOVERY|ACKNOWLEDGEMENT)\s+(?:Service|Host)?\s*alert"
    r"(?:\s+-\s+(?P<host>[^/\*]+?)(?:/(?P<service>[^*]+?))?\s+is\s+(?P<nagios_state>\w+))?\s*\*\*",
    re.I,
)
# Nagios body KV block: "Host:  myhost.example.com\nService:  HTTP\n..."
_NAGIOS_KV_RE = re.compile(
    r"^(?P<key>Host|Service|State|Address|Date/Time|Additional Info|Output|Notification Type)"
    r"\s*:\s*(?P<value>.+)$",
    re.M | re.I,
)
_NAGIOS_SEVERITY_MAP = {
    "ok": Severity.LOW, "up": Severity.LOW,
    "warning": Severity.MEDIUM, "degraded": Severity.MEDIUM,
    "critical": Severity.CRITICAL, "down": Severity.CRITICAL,
    "unknown": Severity.MEDIUM,
}

# Zabbix subject
_ZABBIX_SUBJECT_RE = re.compile(
    r"^(?:PROBLEM|RESOLVED|UPDATED):\s+(?P<trigger>.+?)"
    r"(?:\s+on\s+(?P<host>\S+))?$",
    re.I,
)
# Zabbix body KV
_ZABBIX_KV_RE = re.compile(
    r"^(?P<key>Host|Host IP|Trigger|Trigger status|Trigger severity|"
    r"Trigger URL|Item values|Original problem ID|Event ID|Event date)"
    r"\s*:\s*(?P<value>.+)$",
    re.M | re.I,
)
_ZABBIX_SEVERITY_MAP = {
    "not classified": Severity.LOW,  "information": Severity.LOW,
    "warning": Severity.MEDIUM,      "average": Severity.MEDIUM,
    "high": Severity.HIGH,           "disaster": Severity.CRITICAL,
}

# Generic structured body: "key: value" pairs
_GENERIC_KV_RE = re.compile(r"^(?P<key>[\w\s]{2,30})\s*[:=]\s*(?P<value>.+)$", re.M)


# ---------------------------------------------------------------------------
# Body extraction helpers
# ---------------------------------------------------------------------------

def _extract_plain_body(msg: Message) -> str:
    """Return the first plain-text body part, falling back to HTML-stripped."""
    plain: Optional[str] = None
    html:  Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ct == "text/plain" and plain is None:
                plain = text
            elif ct == "text/html" and html is None:
                html = text
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace") if payload else ""
        if msg.get_content_type() == "text/html":
            html = text
        else:
            plain = text

    if plain:
        return plain.strip()
    if html:
        return _strip_html(html).strip()
    return ""


def _parse_email_date(msg: Message) -> datetime:
    date_str = msg.get("Date", "")
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Format-specific parsers
# ---------------------------------------------------------------------------

def _parse_nagios(subject: str, body: str, timestamp: datetime) -> dict:
    """Extract fields from a Nagios/Icinga formatted email."""
    m = _NAGIOS_SUBJECT_RE.match(subject)
    raw: dict = {"timestamp": timestamp}

    if m:
        raw["hostname"] = (m.group("host") or "").strip()
        raw["fault_category"] = m.group("service") or "host_check"
        nagios_state = (m.group("nagios_state") or "unknown").lower()
        raw["severity"] = _NAGIOS_SEVERITY_MAP.get(nagios_state, Severity.MEDIUM).value

    # Parse body KV pairs
    for kv in _NAGIOS_KV_RE.finditer(body):
        key   = kv.group("key").lower().strip()
        value = kv.group("value").strip()
        if key == "host":
            raw.setdefault("hostname", value)
        elif key == "service":
            raw.setdefault("fault_category", value)
        elif key == "state":
            sev = _NAGIOS_SEVERITY_MAP.get(value.lower(), Severity.MEDIUM)
            raw.setdefault("severity", sev.value)
        elif key in ("additional info", "output", "plugin output"):
            raw["description"] = value
        elif key == "date/time":
            raw.setdefault("timestamp", value)

    raw.setdefault("description", body[:600])
    return raw


def _parse_zabbix(subject: str, body: str, timestamp: datetime) -> dict:
    """Extract fields from a Zabbix formatted email."""
    m = _ZABBIX_SUBJECT_RE.match(subject)
    raw: dict = {"timestamp": timestamp}

    if m:
        raw["description"] = m.group("trigger") or subject
        raw["hostname"] = (m.group("host") or "").strip()

    for kv in _ZABBIX_KV_RE.finditer(body):
        key   = kv.group("key").lower().strip()
        value = kv.group("value").strip()
        if key == "host":
            raw.setdefault("hostname", value)
        elif key == "trigger":
            raw.setdefault("description", value)
        elif key == "trigger severity":
            sev_key = value.lower()
            sev = _ZABBIX_SEVERITY_MAP.get(sev_key, Severity.MEDIUM)
            raw["severity"] = sev.value
        elif key == "item values":
            raw["alarm_text"] = value

    raw.setdefault("description", body[:600])
    return raw


def _parse_generic(subject: str, body: str, timestamp: datetime) -> dict:
    """
    Generic parser: attempts key:value extraction, then falls back to
    using subject as summary and body as description.
    """
    raw: dict = {"timestamp": timestamp, "description": body or subject}

    # Try structured KV pairs
    kv_pairs = {
        kv.group("key").strip().lower(): kv.group("value").strip()
        for kv in _GENERIC_KV_RE.finditer(body)
    }
    # Merge KV pairs — keys stay as-is for TelcoNormalizer alias lookup
    raw.update(kv_pairs)

    # Always preserve subject as summary fallback
    if subject:
        raw.setdefault("summary", subject)

    return raw


# ---------------------------------------------------------------------------
# Format detector
# ---------------------------------------------------------------------------

def _detect_format(subject: str, body: str) -> str:
    if _NAGIOS_SUBJECT_RE.search(subject):
        return "nagios"
    if _ZABBIX_SUBJECT_RE.match(subject) and ("Trigger" in body or "Host IP" in body):
        return "zabbix"
    return "generic"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TelcoEmailIngester:
    """
    Parses RFC-2822 email bytes into a TelcoTicketCreate.

    Supports Nagios, Zabbix, and generic NOC alert formats.

    Example::

        ingester = TelcoEmailIngester()
        ticket = ingester.ingest_bytes(eml_bytes)
        print(ticket.fault_type, ticket.affected_node)
    """

    def __init__(self) -> None:
        self._normalizer = TelcoNormalizer()

    def ingest_bytes(self, raw_email: bytes) -> TelcoTicketCreate:
        """Parse raw .eml bytes into a TelcoTicketCreate."""
        msg       = email.message_from_bytes(raw_email)
        subject   = msg.get("Subject", "").strip()
        timestamp = _parse_email_date(msg)
        body      = _extract_plain_body(msg)
        sender    = msg.get("From", "")

        fmt = _detect_format(subject, body)
        log.debug("Email format detected: %s | subject=%r", fmt, subject[:80])

        if fmt == "nagios":
            raw = _parse_nagios(subject, body, timestamp)
        elif fmt == "zabbix":
            raw = _parse_zabbix(subject, body, timestamp)
        else:
            raw = _parse_generic(subject, body, timestamp)

        # Inject sender as metadata so normaliser can use it
        raw["_email_sender"] = sender
        raw["_email_subject"] = subject

        return self._normalizer.normalize(raw, source="email")

    def ingest_text(self, raw_email: str, encoding: str = "utf-8") -> TelcoTicketCreate:
        return self.ingest_bytes(raw_email.encode(encoding))
