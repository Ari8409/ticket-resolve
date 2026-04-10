"""
API / webhook ingester for telco alert tickets.

Handles four payload formats:
  • Generic REST JSON   — any dict with field names TelcoNormalizer understands
  • Prometheus          — AlertManager webhook (groups of alerts)
  • PagerDuty           — PDV2 webhook (incident / alert payloads)
  • Grafana             — Unified alerting webhook (v1 schema)

Format is auto-detected from payload structure. Unknown payloads fall
through to the generic path which relies entirely on TelcoNormalizer's
alias lookup + inference logic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.ingestion.telco.normalizer import TelcoNormalizer
from app.models.telco_ticket import FaultType, Severity, TelcoTicketCreate

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prometheus AlertManager webhook adapter
# Spec: https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
# ---------------------------------------------------------------------------

_PROMETHEUS_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL, "page": Severity.CRITICAL,
    "high":     Severity.HIGH,     "error": Severity.HIGH,
    "warning":  Severity.MEDIUM,   "warn":  Severity.MEDIUM,
    "info":     Severity.LOW,      "none":  Severity.LOW,
}


def _parse_prometheus_alert(alert: dict) -> dict:
    """Flatten a single Prometheus alert object into a raw normaliser dict."""
    labels   = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    raw: dict = {}

    raw["alert_name"]   = labels.get("alertname", "")
    raw["hostname"]     = labels.get("instance") or labels.get("node") or labels.get("host", "")
    raw["fault_category"] = labels.get("job") or labels.get("category", "")
    raw["description"]  = (
        annotations.get("description") or annotations.get("summary") or raw["alert_name"]
    )
    raw["alarm_text"]   = annotations.get("summary", "")

    sev_label = labels.get("severity", "warning").lower()
    raw["severity"] = _PROMETHEUS_SEVERITY_MAP.get(sev_label, Severity.MEDIUM).value

    # Parse ISO timestamp
    starts_at = alert.get("startsAt", "")
    raw["timestamp"] = starts_at or datetime.now(tz=timezone.utc).isoformat()

    # Preserve all labels/annotations as extra context
    raw.update({f"lbl_{k}": v for k, v in labels.items()})
    raw["runbook_id"] = annotations.get("runbook_url", "")
    return raw


def _adapt_prometheus(payload: dict) -> list[dict]:
    """Return a list of raw dicts from a Prometheus AlertManager webhook body."""
    alerts = payload.get("alerts", [])
    return [_parse_prometheus_alert(a) for a in alerts if a]


# ---------------------------------------------------------------------------
# PagerDuty V2 webhook adapter
# Spec: https://developer.pagerduty.com/docs/db0fa8c8984fc-overview
# ---------------------------------------------------------------------------

_PD_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "error":    Severity.HIGH,
    "warning":  Severity.MEDIUM,
    "info":     Severity.LOW,
}

_PD_STATUS_FAULT_MAP: dict[str, FaultType] = {
    "triggered": FaultType.UNKNOWN,
    "acknowledged": FaultType.UNKNOWN,
    "resolved": FaultType.UNKNOWN,
}


def _adapt_pagerduty(payload: dict) -> list[dict]:
    """Extract telco fields from a PagerDuty PDV2 webhook payload."""
    results: list[dict] = []

    for message in payload.get("messages", []):
        incident = message.get("incident", {})
        service  = incident.get("service", {})
        body     = incident.get("body", {})

        raw: dict = {
            "ticket_id":     incident.get("incident_number", ""),
            "description":   body.get("details", incident.get("title", "")),
            "summary":       incident.get("title", ""),
            "hostname":      service.get("name", ""),
            "severity":      _PD_SEVERITY_MAP.get(
                                 incident.get("urgency", "low"), Severity.LOW
                             ).value,
            "timestamp":     incident.get("created_at", ""),
            "sop_id":        incident.get("escalation_policy", {}).get("id", ""),
        }
        results.append(raw)

    return results


# ---------------------------------------------------------------------------
# Grafana Unified Alerting webhook adapter
# ---------------------------------------------------------------------------

_GRAFANA_STATE_MAP: dict[str, Severity] = {
    "alerting": Severity.HIGH,
    "pending":  Severity.MEDIUM,
    "ok":       Severity.LOW,
    "nodata":   Severity.LOW,
    "error":    Severity.CRITICAL,
}


def _adapt_grafana(payload: dict) -> list[dict]:
    alerts = payload.get("alerts", [])
    results: list[dict] = []
    for alert in alerts:
        labels  = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        raw: dict = {
            "alert_name":     alert.get("name", labels.get("alertname", "")),
            "hostname":       labels.get("host") or labels.get("instance", ""),
            "description":    annotations.get("description") or annotations.get("summary", ""),
            "severity":       _GRAFANA_STATE_MAP.get(alert.get("state", ""), Severity.MEDIUM).value,
            "timestamp":      alert.get("startsAt", ""),
            "runbook_id":     annotations.get("runbook", ""),
        }
        results.append(raw)
    return results


# ---------------------------------------------------------------------------
# Format detector
# ---------------------------------------------------------------------------

def _detect_api_format(payload: dict) -> str:
    if "alerts" in payload and "receiver" in payload and "groupLabels" in payload:
        return "prometheus"
    if "messages" in payload and payload.get("messages") and "incident" in (payload["messages"][0] if payload["messages"] else {}):
        return "pagerduty"
    if "alerts" in payload and "title" in payload and "orgId" in payload:
        return "grafana"
    return "generic"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TelcoAPIIngester:
    """
    Normalises JSON payloads from REST endpoints or monitoring webhooks
    into TelcoTicketCreate records.

    Supports auto-detection of Prometheus, PagerDuty, Grafana, and
    generic REST JSON formats.

    Example — single generic alert::

        ingester = TelcoAPIIngester()
        tickets = ingester.ingest({"fault_type": "node_down", "affected_node": "NODE-01", ...})

    Example — Prometheus webhook batch::

        tickets = ingester.ingest(prometheus_webhook_body)
    """

    def __init__(self) -> None:
        self._normalizer = TelcoNormalizer()

    def ingest(self, payload: dict | list) -> list[TelcoTicketCreate]:
        """
        Parse a JSON payload into one or more TelcoTicketCreate records.

        Accepts:
          - A single dict (one ticket / alert)
          - A list of dicts (batch)
          - A Prometheus / PagerDuty / Grafana webhook envelope
        """
        # Normalise input to list of raw dicts
        if isinstance(payload, list):
            raw_items = payload
            fmt = "generic"
        else:
            fmt = _detect_api_format(payload)
            if fmt == "prometheus":
                raw_items = _adapt_prometheus(payload)
            elif fmt == "pagerduty":
                raw_items = _adapt_pagerduty(payload)
            elif fmt == "grafana":
                raw_items = _adapt_grafana(payload)
            else:
                raw_items = [payload]

        log.debug("API ingest: format=%s items=%d", fmt, len(raw_items))

        tickets: list[TelcoTicketCreate] = []
        for i, raw in enumerate(raw_items):
            try:
                ticket = self._normalizer.normalize(raw, source=f"api:{fmt}")
                tickets.append(ticket)
            except Exception as exc:
                log.warning("API item %d skipped — %s: %s", i, type(exc).__name__, exc)

        return tickets

    def ingest_one(self, payload: dict) -> TelcoTicketCreate:
        """Parse a single JSON object. Raises if normalisation fails."""
        return self._normalizer.normalize(payload, source="api")
