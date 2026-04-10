"""
SOPMarkdownParser — parses structured SOPs from markdown files.

Markdown schema
---------------
SOPs are written with YAML frontmatter (between ``---`` delimiters) for
structured metadata, and markdown sections for human-readable content.
The parser supports two extraction strategies, tried in order:

Strategy 1 — YAML frontmatter (preferred)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    ---
    sop_id: SOP-RF-001
    fault_category: signal_loss
    estimated_resolution_time: "30–90 minutes"
    escalation_path: "L1 NOC → L2 RF Engineer → Vendor TAC"
    preconditions:
      - NMS access confirmed
      - Alarm verified active (not cleared)
    ---

    # Title of the SOP

    ## Resolution Steps
    1. Step one text.
    2. Step two text.

    ## Escalation Path
    ...

Frontmatter values take precedence over section-parsed values for the
same field.  This lets authors put short-form metadata in frontmatter
and the detailed procedure in markdown sections.

Strategy 2 — section headers (fallback / supplement)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If frontmatter is absent or a field is missing, the parser looks for
section headers (case-insensitive):

  * ``## Preconditions`` / ``## Prerequisites``  → list items → preconditions
  * ``## Resolution Steps`` / ``## Steps`` / ``## Procedure``  → numbered/bullet list → resolution_steps
  * ``## Escalation`` / ``## Escalation Path``  → first paragraph → escalation_path
  * ``## Estimated Resolution Time`` / ``## Time Estimate``  → first line → estimated_resolution_time
  * ``## Overview`` / ``## Summary``  → used to enrich raw_content

ParseError
----------
Raised when a file is missing a required field after both strategies have
been attempted.  The error message names the missing field(s) and the
source file path so callers can surface actionable feedback.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from app.models.sop import SOPRecord

log = logging.getLogger(__name__)


class SOPParseError(Exception):
    """Raised when a required SOP field cannot be extracted from a file."""


# ---------------------------------------------------------------------------
# Section header aliases (case-insensitive)
# ---------------------------------------------------------------------------

_SECTION_PRECONDITIONS   = re.compile(r"^#+\s*(preconditions?|prerequisites?)\s*$", re.I)
_SECTION_STEPS           = re.compile(r"^#+\s*(resolution\s+steps?|steps?|procedure)\s*$", re.I)
_SECTION_ESCALATION      = re.compile(r"^#+\s*(escalation(\s+path)?)\s*$", re.I)
_SECTION_TIME            = re.compile(r"^#+\s*(estimated\s+resolution\s+time|time\s+estim\w+)\s*$", re.I)
_SECTION_TITLE           = re.compile(r"^#\s+(.+)$")

# List item patterns — ordered (1. text) or unordered (- text / * text)
_LIST_ITEM               = re.compile(r"^\s*(?:\d+[.)]\s+|[-*]\s+)(.+)$")

# YAML frontmatter block
_FRONTMATTER_RE          = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SOPMarkdownParser:
    """
    Parses a single SOP markdown file into an ``SOPRecord``.

    Usage::

        parser = SOPMarkdownParser()
        record = parser.parse(Path("data/sops/telco/signal_loss.md"))
    """

    def parse(self, path: Path) -> SOPRecord:
        """
        Parse ``path`` and return a fully-populated ``SOPRecord``.

        Raises
        ------
        SOPParseError
            If any required field (sop_id, fault_category, escalation_path,
            estimated_resolution_time) is missing after both extraction
            strategies have been attempted.
        FileNotFoundError
            If ``path`` does not exist.
        """
        content = path.read_text(encoding="utf-8")
        fm, body = self._split_frontmatter(content)

        title        = self._extract_title(body) or path.stem.replace("-", " ").replace("_", " ").title()
        sections     = self._split_sections(body)

        preconditions      = self._extract_list_items(sections.get("preconditions", ""))
        resolution_steps   = self._extract_list_items(sections.get("steps", ""))
        escalation_path    = self._extract_first_paragraph(sections.get("escalation", ""))
        est_time           = self._extract_first_line(sections.get("time", ""))

        # Frontmatter overrides / supplements section-parsed values
        sop_id       = str(fm.get("sop_id", "")).strip() or self._infer_sop_id(path)
        fault_cat    = str(fm.get("fault_category", "")).strip().lower() or self._infer_category(path, title)

        if "preconditions" in fm:
            preconditions = self._coerce_list(fm["preconditions"])
        if "resolution_steps" in fm:
            resolution_steps = self._coerce_list(fm["resolution_steps"])
        if "escalation_path" in fm:
            escalation_path = str(fm["escalation_path"]).strip()
        if "estimated_resolution_time" in fm:
            est_time = str(fm["estimated_resolution_time"]).strip()

        # RAN / Ericsson OPI optional fields — read straight from frontmatter
        managed_object          = str(fm.get("managed_object", "")).strip()
        additional_text         = str(fm.get("additional_text", "")).strip()
        alarm_severity          = str(fm.get("alarm_severity", "primary")).strip().lower()
        on_site_required        = bool(fm.get("on_site_required", False))
        secondary_alarm_pointer = str(fm.get("secondary_alarm_pointer", "")).strip()

        # Validate required fields
        missing = [
            name for name, val in [
                ("sop_id",                    sop_id),
                ("fault_category",            fault_cat),
                ("escalation_path",           escalation_path),
                ("estimated_resolution_time", est_time),
            ]
            if not val
        ]
        if missing:
            raise SOPParseError(
                f"{path}: missing required field(s): {', '.join(missing)}. "
                "Add them to the YAML frontmatter or the corresponding markdown section."
            )

        log.debug(
            "Parsed SOP %s — category=%s mo=%s severity=%s steps=%d preconditions=%d",
            sop_id, fault_cat, managed_object or "—", alarm_severity,
            len(resolution_steps), len(preconditions),
        )
        return SOPRecord(
            sop_id=sop_id,
            fault_category=fault_cat,
            preconditions=preconditions,
            resolution_steps=resolution_steps,
            escalation_path=escalation_path,
            estimated_resolution_time=est_time,
            managed_object=managed_object,
            additional_text=additional_text,
            alarm_severity=alarm_severity,
            on_site_required=on_site_required,
            secondary_alarm_pointer=secondary_alarm_pointer,
            title=title,
            source_path=str(path),
            raw_content=content,
        )

    # ------------------------------------------------------------------
    # Frontmatter
    # ------------------------------------------------------------------

    @staticmethod
    def _split_frontmatter(content: str) -> tuple[dict, str]:
        """Return (frontmatter_dict, body_without_frontmatter)."""
        match = _FRONTMATTER_RE.match(content)
        if not match:
            return {}, content

        try:
            import yaml  # optional dependency; gracefully fall back if absent
            fm = yaml.safe_load(match.group(1)) or {}
        except Exception as exc:
            log.warning("Failed to parse YAML frontmatter: %s — treating as empty", exc)
            fm = {}

        body = content[match.end():]
        return (fm if isinstance(fm, dict) else {}), body

    # ------------------------------------------------------------------
    # Section splitting
    # ------------------------------------------------------------------

    @staticmethod
    def _split_sections(body: str) -> dict[str, str]:
        """
        Split markdown body into named sections keyed by canonical name.

        Keys: ``preconditions``, ``steps``, ``escalation``, ``time``, ``other``
        Values: the raw text content beneath that header.
        """
        sections: dict[str, str] = {}
        current_key   = "other"
        current_lines: list[str] = []

        def _flush():
            if current_lines:
                sections[current_key] = sections.get(current_key, "") + "\n".join(current_lines)
            current_lines.clear()

        for line in body.splitlines():
            if _SECTION_PRECONDITIONS.match(line):
                _flush(); current_key = "preconditions"
            elif _SECTION_STEPS.match(line):
                _flush(); current_key = "steps"
            elif _SECTION_ESCALATION.match(line):
                _flush(); current_key = "escalation"
            elif _SECTION_TIME.match(line):
                _flush(); current_key = "time"
            elif re.match(r"^#+\s", line):
                _flush(); current_key = "other"
            else:
                current_lines.append(line)

        _flush()
        return sections

    # ------------------------------------------------------------------
    # Content extractors
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_title(body: str) -> str:
        for line in body.splitlines():
            m = _SECTION_TITLE.match(line)
            if m:
                return m.group(1).strip()
        return ""

    @staticmethod
    def _extract_list_items(text: str) -> list[str]:
        items = []
        for line in text.splitlines():
            m = _LIST_ITEM.match(line)
            if m:
                items.append(m.group(1).strip())
        return items

    @staticmethod
    def _extract_first_paragraph(text: str) -> str:
        """Return all consecutive non-blank lines at the start of ``text``."""
        lines = []
        for line in text.lstrip("\n").splitlines():
            if not line.strip():
                if lines:
                    break
            else:
                lines.append(line.strip())
        return " ".join(lines)

    @staticmethod
    def _extract_first_line(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""

    # ------------------------------------------------------------------
    # Inference helpers (used when fields are absent)
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_sop_id(path: Path) -> str:
        """Derive a SOP ID from the filename, e.g. signal_loss.md → SOP-SIGNAL-LOSS."""
        stem = path.stem.upper().replace("-", "_")
        return f"SOP-{stem}"

    @staticmethod
    def _infer_category(path: Path, title: str) -> str:
        """Best-effort fault_category from filename or title keywords."""
        text = (path.stem + " " + title).lower()
        for keyword in (
            "signal_loss", "signal",
            "node_down", "node",
            "hardware_failure", "hardware",
            "configuration_error", "config",
            "packet_loss", "packet",
            "congestion",
            "latency",
        ):
            if keyword.replace("_", " ") in text or keyword in text:
                return keyword.replace(" ", "_")
        return "unknown"

    # ------------------------------------------------------------------
    # Coercion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [s.strip() for s in value.splitlines() if s.strip()]
        return []
