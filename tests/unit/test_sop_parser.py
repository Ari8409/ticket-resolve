"""
Unit tests for SOPMarkdownParser.

Covers:
  - YAML frontmatter extraction (happy path and edge cases)
  - Section-header fallback parsing
  - Mixed strategy (frontmatter + sections)
  - SOPParseError on missing required fields
  - Inference helpers (_infer_sop_id, _infer_category)
  - Coercion helpers (_coerce_list)
  - Title extraction from markdown H1
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.sop.parser import SOPMarkdownParser, SOPParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_sop(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


FULL_FRONTMATTER = """
    ---
    sop_id: SOP-RF-001
    fault_category: signal_loss
    estimated_resolution_time: "30–90 minutes"
    escalation_path: "L1 NOC → L2 RF Engineer"
    preconditions:
      - NMS access confirmed
      - Alarm verified active
    resolution_steps:
      - Check RSSI values in NMS
      - Power cycle the ODU
      - Dispatch field engineer
    ---

    # Signal Loss SOP

    Some overview text.
"""

FULL_SECTIONS = """
    # Node Down SOP

    ## Preconditions
    - OOB access available
    - Spare hardware on standby

    ## Resolution Steps
    1. Confirm node is down via SNMP.
    2. Access via OOB management.
    3. Reload the node.

    ## Escalation Path
    L1 NOC → L2 Network Engineer → Vendor TAC

    ## Estimated Resolution Time
    15–120 minutes
"""


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def parser() -> SOPMarkdownParser:
    return SOPMarkdownParser()


# ---------------------------------------------------------------------------
# Happy path — YAML frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatterParsing:
    def test_all_fields_from_frontmatter(self, parser, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", FULL_FRONTMATTER)
        record = parser.parse(path)

        assert record.sop_id == "SOP-RF-001"
        assert record.fault_category == "signal_loss"
        assert record.estimated_resolution_time == "30–90 minutes"
        assert "L1 NOC" in record.escalation_path
        assert "NMS access confirmed" in record.preconditions
        assert len(record.preconditions) == 2
        assert len(record.resolution_steps) == 3
        assert record.title == "Signal Loss SOP"

    def test_source_path_stored(self, parser, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", FULL_FRONTMATTER)
        record = parser.parse(path)
        assert record.source_path == str(path)

    def test_raw_content_stored(self, parser, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", FULL_FRONTMATTER)
        record = parser.parse(path)
        assert "SOP-RF-001" in record.raw_content

    def test_fault_category_normalised_to_lowercase(self, parser, tmp_path):
        content = FULL_FRONTMATTER.replace("signal_loss", "Signal_Loss")
        path = _write_sop(tmp_path, "sig.md", content)
        record = parser.parse(path)
        assert record.fault_category == "signal_loss"

    def test_step_count_matches_list(self, parser, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", FULL_FRONTMATTER)
        record = parser.parse(path)
        assert record.step_count == 3

    def test_precondition_count_matches_list(self, parser, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", FULL_FRONTMATTER)
        record = parser.parse(path)
        assert record.precondition_count == 2


# ---------------------------------------------------------------------------
# Happy path — Section header fallback
# ---------------------------------------------------------------------------

class TestSectionHeaderParsing:
    def _make_section_sop(self, tmp_path, content=FULL_SECTIONS):
        """Write a sections-only SOP that needs an inferred sop_id."""
        path = _write_sop(tmp_path, "node_down.md", content)
        return path

    def test_title_extracted_from_h1(self, parser, tmp_path):
        path = self._make_section_sop(tmp_path)
        record = parser.parse(path)
        assert record.title == "Node Down SOP"

    def test_preconditions_from_section(self, parser, tmp_path):
        path = self._make_section_sop(tmp_path)
        record = parser.parse(path)
        assert "OOB access available" in record.preconditions

    def test_resolution_steps_from_section(self, parser, tmp_path):
        path = self._make_section_sop(tmp_path)
        record = parser.parse(path)
        assert len(record.resolution_steps) == 3
        assert "Confirm node is down via SNMP." in record.resolution_steps

    def test_escalation_from_section(self, parser, tmp_path):
        path = self._make_section_sop(tmp_path)
        record = parser.parse(path)
        assert "L1 NOC" in record.escalation_path

    def test_estimated_time_from_section(self, parser, tmp_path):
        path = self._make_section_sop(tmp_path)
        record = parser.parse(path)
        assert record.estimated_resolution_time == "15–120 minutes"

    def test_sop_id_inferred_from_filename(self, parser, tmp_path):
        path = self._make_section_sop(tmp_path)
        record = parser.parse(path)
        assert record.sop_id == "SOP-NODE_DOWN"

    def test_fault_category_inferred_from_filename(self, parser, tmp_path):
        path = self._make_section_sop(tmp_path)
        record = parser.parse(path)
        assert record.fault_category == "node_down"


# ---------------------------------------------------------------------------
# Mixed strategy — frontmatter + sections
# ---------------------------------------------------------------------------

class TestMixedStrategy:
    def test_frontmatter_overrides_section_fields(self, parser, tmp_path):
        """When both frontmatter and section have a field, frontmatter wins."""
        content = """\
---
sop_id: SOP-MIXED-001
fault_category: hardware_failure
estimated_resolution_time: "2 hours"
escalation_path: "L1 → L2 → Vendor"
---

# Hardware SOP

## Escalation Path
This section value should be ignored.

## Estimated Resolution Time
This section value should be ignored.
"""
        path = _write_sop(tmp_path, "hw.md", content)
        record = parser.parse(path)
        assert record.escalation_path == "L1 → L2 → Vendor"
        assert record.estimated_resolution_time == "2 hours"

    def test_frontmatter_supplements_missing_section_field(self, parser, tmp_path):
        """Frontmatter provides sop_id while steps come from the section."""
        content = """\
---
sop_id: SOP-TEST-001
fault_category: latency
estimated_resolution_time: "1 hour"
escalation_path: "L1 NOC"
---

# Latency SOP

## Resolution Steps
1. Run MTR.
2. Check queue drops.
"""
        path = _write_sop(tmp_path, "lat.md", content)
        record = parser.parse(path)
        assert record.sop_id == "SOP-TEST-001"
        assert len(record.resolution_steps) == 2

    def test_preconditions_from_frontmatter_list(self, parser, tmp_path):
        content = """\
---
sop_id: SOP-TEST-002
fault_category: congestion
estimated_resolution_time: "45 minutes"
escalation_path: "L1 NOC → L2"
preconditions:
  - NetFlow enabled
  - Baseline captured
---

# Congestion SOP
"""
        path = _write_sop(tmp_path, "cong.md", content)
        record = parser.parse(path)
        assert record.preconditions == ["NetFlow enabled", "Baseline captured"]


# ---------------------------------------------------------------------------
# SOPParseError — missing required fields
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_missing_escalation_path_raises(self, parser, tmp_path):
        content = """\
---
sop_id: SOP-ERR-001
fault_category: latency
estimated_resolution_time: "1 hour"
---

# No Escalation SOP
"""
        path = _write_sop(tmp_path, "err.md", content)
        with pytest.raises(SOPParseError, match="escalation_path"):
            parser.parse(path)

    def test_missing_estimated_time_raises(self, parser, tmp_path):
        content = """\
---
sop_id: SOP-ERR-002
fault_category: latency
escalation_path: "L1 NOC"
---

# No Time SOP
"""
        path = _write_sop(tmp_path, "err2.md", content)
        with pytest.raises(SOPParseError, match="estimated_resolution_time"):
            parser.parse(path)

    def test_multiple_missing_fields_all_named(self, parser, tmp_path):
        """Error message should list every missing field."""
        content = """\
---
sop_id: SOP-ERR-003
---

# Incomplete SOP
"""
        path = _write_sop(tmp_path, "err3.md", content)
        with pytest.raises(SOPParseError) as exc_info:
            parser.parse(path)
        msg = str(exc_info.value)
        assert "fault_category" in msg
        assert "escalation_path" in msg
        assert "estimated_resolution_time" in msg

    def test_file_not_found_raises(self, parser, tmp_path):
        with pytest.raises(FileNotFoundError):
            parser.parse(tmp_path / "nonexistent.md")

    def test_empty_sop_id_in_frontmatter_infers_from_filename(self, parser, tmp_path):
        """A blank sop_id in frontmatter falls back to filename inference."""
        content = """\
---
sop_id: ""
fault_category: node_down
estimated_resolution_time: "1 hour"
escalation_path: "L1 NOC"
---

# Node Down
"""
        path = _write_sop(tmp_path, "node_down.md", content)
        record = parser.parse(path)
        assert record.sop_id == "SOP-NODE_DOWN"


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

class TestInferenceHelpers:
    def test_infer_sop_id_from_stem(self):
        p = Path("data/sops/signal-loss.md")
        assert SOPMarkdownParser._infer_sop_id(p) == "SOP-SIGNAL-LOSS"

    def test_infer_sop_id_underscored(self):
        p = Path("data/sops/node_down.md")
        assert SOPMarkdownParser._infer_sop_id(p) == "SOP-NODE_DOWN"

    @pytest.mark.parametrize("filename,expected_cat", [
        ("signal_loss.md",        "signal_loss"),
        ("node_down.md",          "node_down"),
        ("hardware_failure.md",   "hardware_failure"),
        ("configuration_error.md","config"),
        ("latency_check.md",      "latency"),
        ("congestion_mgmt.md",    "congestion"),
        ("unknown_thing.md",      "unknown"),
    ])
    def test_infer_category_from_filename(self, filename, expected_cat):
        p = Path(f"data/sops/{filename}")
        result = SOPMarkdownParser._infer_category(p, "")
        assert result == expected_cat


# ---------------------------------------------------------------------------
# Section aliases (case-insensitive header variants)
# ---------------------------------------------------------------------------

class TestSectionAliases:
    def _sop_with_headers(self, tmp_path, precond_header, steps_header):
        content = f"""\
---
sop_id: SOP-ALIAS-001
fault_category: latency
estimated_resolution_time: "1 hour"
escalation_path: "L1 NOC"
---

# Alias SOP

## {precond_header}
- Access confirmed

## {steps_header}
1. Step one.
2. Step two.
"""
        return _write_sop(tmp_path, "alias.md", content)

    @pytest.mark.parametrize("precond_header", [
        "Preconditions", "preconditions", "Prerequisites", "PREREQUISITES"
    ])
    def test_preconditions_header_aliases(self, parser, tmp_path, precond_header):
        path = self._sop_with_headers(tmp_path, precond_header, "Resolution Steps")
        record = parser.parse(path)
        assert "Access confirmed" in record.preconditions

    @pytest.mark.parametrize("steps_header", [
        "Resolution Steps", "Steps", "Procedure", "PROCEDURE"
    ])
    def test_steps_header_aliases(self, parser, tmp_path, steps_header):
        path = self._sop_with_headers(tmp_path, "Preconditions", steps_header)
        record = parser.parse(path)
        assert len(record.resolution_steps) == 2


# ---------------------------------------------------------------------------
# List item parsing
# ---------------------------------------------------------------------------

class TestListItemParsing:
    @pytest.mark.parametrize("item_text,expected", [
        ("- Unordered bullet",     "Unordered bullet"),
        ("* Star bullet",          "Star bullet"),
        ("1. Ordered item",        "Ordered item"),
        ("2) Ordered paren item",  "Ordered paren item"),
        ("  - Indented bullet",    "Indented bullet"),
    ])
    def test_list_item_formats(self, item_text, expected):
        items = SOPMarkdownParser._extract_list_items(item_text)
        assert items == [expected]

    def test_non_list_lines_ignored(self):
        text = "Plain paragraph\nNo list here"
        items = SOPMarkdownParser._extract_list_items(text)
        assert items == []
