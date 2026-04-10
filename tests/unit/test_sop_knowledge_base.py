"""
Unit tests for SOPKnowledgeBase.

Covers:
  - load_file() / load_directory() — happy path + failures
  - In-memory lookups: get_by_id, get_by_category, all_records, all_categories
  - Keyword search()
  - _build_chunks() — semantic chunking layout
  - index_all() — async embed + upsert, chunk counts, report population
  - SOPLoadReport.summary()
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.sop import SOPRecord
from app.sop.knowledge_base import SOPKnowledgeBase, SOPLoadReport
from app.sop.parser import SOPParseError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_sop(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _make_record(
    sop_id: str = "SOP-RF-001",
    fault_category: str = "signal_loss",
    title: str = "Signal Loss SOP",
    steps: list[str] | None = None,
    preconditions: list[str] | None = None,
) -> SOPRecord:
    return SOPRecord(
        sop_id=sop_id,
        fault_category=fault_category,
        title=title,
        preconditions=preconditions or ["NMS access confirmed"],
        resolution_steps=steps or ["Check RSSI", "Power cycle ODU", "Dispatch engineer"],
        escalation_path="L1 NOC → L2 RF Engineer",
        estimated_resolution_time="30–90 minutes",
        source_path=f"/data/{sop_id}.md",
    )


SIGNAL_LOSS_MD = """\
---
sop_id: SOP-RF-001
fault_category: signal_loss
estimated_resolution_time: "30 minutes"
escalation_path: "L1 NOC → L2 RF"
preconditions:
  - NMS access confirmed
---

# Signal Loss SOP

## Resolution Steps
1. Check RSSI.
2. Power cycle ODU.
"""

NODE_DOWN_MD = """\
---
sop_id: SOP-NET-002
fault_category: node_down
estimated_resolution_time: "1 hour"
escalation_path: "L1 NOC → L2 Network"
---

# Node Down SOP

## Resolution Steps
1. Confirm via SNMP.
2. Reload the node.
"""

BAD_MD = """\
# Incomplete SOP

No frontmatter and no required section values here.
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def kb() -> SOPKnowledgeBase:
    return SOPKnowledgeBase()


@pytest.fixture()
def two_sop_dir(tmp_path: Path) -> Path:
    _write_sop(tmp_path, "signal_loss.md", SIGNAL_LOSS_MD)
    _write_sop(tmp_path, "node_down.md", NODE_DOWN_MD)
    return tmp_path


@pytest.fixture()
def populated_kb(two_sop_dir: Path) -> SOPKnowledgeBase:
    kb = SOPKnowledgeBase()
    kb.load_directory(two_sop_dir)
    return kb


# ---------------------------------------------------------------------------
# load_file()
# ---------------------------------------------------------------------------

class TestLoadFile:
    def test_returns_sop_record(self, kb, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", SIGNAL_LOSS_MD)
        record = kb.load_file(path)
        assert record.sop_id == "SOP-RF-001"

    def test_registers_in_by_id(self, kb, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", SIGNAL_LOSS_MD)
        kb.load_file(path)
        assert kb.get_by_id("SOP-RF-001") is not None

    def test_registers_in_by_category(self, kb, tmp_path):
        path = _write_sop(tmp_path, "signal_loss.md", SIGNAL_LOSS_MD)
        kb.load_file(path)
        results = kb.get_by_category("signal_loss")
        assert len(results) == 1

    def test_propagates_parse_error(self, kb, tmp_path):
        path = _write_sop(tmp_path, "bad.md", BAD_MD)
        with pytest.raises(SOPParseError):
            kb.load_file(path)

    def test_propagates_file_not_found(self, kb, tmp_path):
        with pytest.raises(FileNotFoundError):
            kb.load_file(tmp_path / "nonexistent.md")


# ---------------------------------------------------------------------------
# load_directory()
# ---------------------------------------------------------------------------

class TestLoadDirectory:
    def test_returns_records_and_report(self, kb, two_sop_dir):
        records, report = kb.load_directory(two_sop_dir)
        assert len(records) == 2
        assert isinstance(report, SOPLoadReport)

    def test_all_valid_files_loaded(self, kb, two_sop_dir):
        records, report = kb.load_directory(two_sop_dir)
        assert report.total_loaded == 2
        assert report.total_failed == 0

    def test_bad_file_does_not_block_others(self, kb, tmp_path):
        _write_sop(tmp_path, "signal_loss.md", SIGNAL_LOSS_MD)
        _write_sop(tmp_path, "bad.md", BAD_MD)
        records, report = kb.load_directory(tmp_path)
        assert len(records) == 1
        assert report.total_failed == 1

    def test_failed_entry_contains_path_and_error(self, kb, tmp_path):
        _write_sop(tmp_path, "bad.md", BAD_MD)
        _, report = kb.load_directory(tmp_path)
        path_str, error_msg = report.failed[0]
        assert "bad.md" in path_str
        assert len(error_msg) > 0

    def test_categories_populated_in_report(self, kb, two_sop_dir):
        _, report = kb.load_directory(two_sop_dir)
        assert "signal_loss" in report.categories
        assert "node_down" in report.categories

    def test_empty_directory_returns_empty_report(self, kb, tmp_path):
        records, report = kb.load_directory(tmp_path)
        assert records == []
        assert report.total_loaded == 0


# ---------------------------------------------------------------------------
# In-memory lookups
# ---------------------------------------------------------------------------

class TestLookups:
    def test_get_by_id_found(self, populated_kb):
        record = populated_kb.get_by_id("SOP-RF-001")
        assert record is not None
        assert record.fault_category == "signal_loss"

    def test_get_by_id_not_found(self, populated_kb):
        assert populated_kb.get_by_id("SOP-MISSING") is None

    def test_get_by_category_returns_all_matching(self, populated_kb):
        results = populated_kb.get_by_category("node_down")
        assert len(results) == 1
        assert results[0].sop_id == "SOP-NET-002"

    def test_get_by_category_case_insensitive(self, populated_kb):
        results = populated_kb.get_by_category("SIGNAL_LOSS")
        assert len(results) == 1

    def test_get_by_category_unknown_returns_empty(self, populated_kb):
        assert populated_kb.get_by_category("alien_invasion") == []

    def test_all_records_sorted_by_id(self, populated_kb):
        records = populated_kb.all_records()
        ids = [r.sop_id for r in records]
        assert ids == sorted(ids)

    def test_all_categories_sorted(self, populated_kb):
        cats = populated_kb.all_categories()
        assert cats == sorted(cats)
        assert "signal_loss" in cats
        assert "node_down" in cats


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

class TestSearch:
    def test_finds_by_title_keyword(self, populated_kb):
        results = populated_kb.search("Signal")
        assert any(r.sop_id == "SOP-RF-001" for r in results)

    def test_finds_by_step_keyword(self, populated_kb):
        results = populated_kb.search("RSSI")
        assert any(r.sop_id == "SOP-RF-001" for r in results)

    def test_no_match_returns_empty(self, populated_kb):
        assert populated_kb.search("quantum_tunnelling") == []

    def test_empty_query_returns_empty(self, populated_kb):
        assert populated_kb.search("") == []

    def test_top_k_limits_results(self, tmp_path):
        kb = SOPKnowledgeBase()
        for i in range(5):
            content = f"""\
---
sop_id: SOP-T-{i:03d}
fault_category: latency
estimated_resolution_time: "1 hour"
escalation_path: "NOC"
---

# Latency SOP {i}

## Resolution Steps
1. Check latency on link.
"""
            _write_sop(tmp_path, f"sop_{i}.md", content)
        kb.load_directory(tmp_path)
        results = kb.search("latency", top_k=2)
        assert len(results) <= 2

    def test_search_is_case_insensitive(self, populated_kb):
        results_lower = populated_kb.search("rssi")
        results_upper = populated_kb.search("RSSI")
        assert len(results_lower) == len(results_upper)


# ---------------------------------------------------------------------------
# _build_chunks()
# ---------------------------------------------------------------------------

class TestBuildChunks:
    def test_chunk_count(self):
        record = _make_record(steps=["Step A", "Step B", "Step C"])
        chunks = SOPKnowledgeBase._build_chunks(record)
        # 1 overview + 3 steps + 1 escalation = 5
        assert len(chunks) == 5

    def test_chunk_count_no_steps(self):
        record = _make_record(steps=[])
        chunks = SOPKnowledgeBase._build_chunks(record)
        # 1 overview + 0 steps + 1 escalation = 2
        assert len(chunks) == 2

    def test_overview_chunk_is_first(self):
        record = _make_record()
        chunks = SOPKnowledgeBase._build_chunks(record)
        assert chunks[0]["type"] == "overview"
        assert chunks[0]["index"] == 0

    def test_overview_chunk_id(self):
        record = _make_record(sop_id="SOP-RF-001")
        chunks = SOPKnowledgeBase._build_chunks(record)
        assert chunks[0]["chunk_id"] == "SOP-RF-001_overview"

    def test_step_chunks_have_correct_type(self):
        record = _make_record(steps=["Step A", "Step B"])
        chunks = SOPKnowledgeBase._build_chunks(record)
        step_chunks = [c for c in chunks if c["type"] == "step"]
        assert len(step_chunks) == 2

    def test_step_chunk_ids(self):
        record = _make_record(sop_id="SOP-RF-001", steps=["Step A", "Step B"])
        chunks = SOPKnowledgeBase._build_chunks(record)
        step_ids = [c["chunk_id"] for c in chunks if c["type"] == "step"]
        assert step_ids == ["SOP-RF-001_step_1", "SOP-RF-001_step_2"]

    def test_step_chunk_indices_sequential(self):
        record = _make_record(steps=["A", "B", "C"])
        chunks = SOPKnowledgeBase._build_chunks(record)
        step_indices = [c["index"] for c in chunks if c["type"] == "step"]
        assert step_indices == [1, 2, 3]

    def test_step_text_contains_step_number(self):
        record = _make_record(sop_id="SOP-RF-001", steps=["Check RSSI"])
        chunks = SOPKnowledgeBase._build_chunks(record)
        step_chunk = next(c for c in chunks if c["type"] == "step")
        assert "Step 1" in step_chunk["text"]
        assert "Check RSSI" in step_chunk["text"]

    def test_escalation_chunk_is_last(self):
        record = _make_record(steps=["A", "B"])
        chunks = SOPKnowledgeBase._build_chunks(record)
        assert chunks[-1]["type"] == "escalation"

    def test_escalation_chunk_id(self):
        record = _make_record(sop_id="SOP-RF-001")
        chunks = SOPKnowledgeBase._build_chunks(record)
        assert chunks[-1]["chunk_id"] == "SOP-RF-001_escalation"

    def test_escalation_text_contains_path(self):
        record = _make_record()
        chunks = SOPKnowledgeBase._build_chunks(record)
        esc = chunks[-1]
        assert "L1 NOC" in esc["text"]

    def test_overview_contains_preconditions(self):
        record = _make_record(preconditions=["Step 0a", "Step 0b"])
        chunks = SOPKnowledgeBase._build_chunks(record)
        assert "Step 0a" in chunks[0]["text"]

    def test_overview_no_preconditions_text(self):
        record = _make_record(preconditions=[])
        chunks = SOPKnowledgeBase._build_chunks(record)
        assert "No specific preconditions" in chunks[0]["text"]


# ---------------------------------------------------------------------------
# index_all() — async
# ---------------------------------------------------------------------------

class TestIndexAll:
    def _mock_embedder(self, dim: int = 4) -> MagicMock:
        embedder = MagicMock()
        embedder.embed_batch = AsyncMock(
            side_effect=lambda texts: [[0.1] * dim for _ in texts]
        )
        return embedder

    def _mock_store(self) -> MagicMock:
        store = MagicMock()
        store.upsert_structured_chunk = AsyncMock(return_value=None)
        return store

    @pytest.mark.asyncio
    async def test_index_all_returns_report(self):
        kb = SOPKnowledgeBase()
        record = _make_record(steps=["A", "B"])
        report = await kb.index_all([record], self._mock_embedder(), self._mock_store())
        assert isinstance(report, SOPLoadReport)

    @pytest.mark.asyncio
    async def test_indexed_chunk_count(self):
        kb = SOPKnowledgeBase()
        record = _make_record(steps=["A", "B", "C"])
        store = self._mock_store()
        report = await kb.index_all([record], self._mock_embedder(), store)
        # 1 overview + 3 steps + 1 escalation = 5
        assert report.indexed == 5

    @pytest.mark.asyncio
    async def test_upsert_called_per_chunk(self):
        kb = SOPKnowledgeBase()
        record = _make_record(steps=["A", "B"])
        store = self._mock_store()
        await kb.index_all([record], self._mock_embedder(), store)
        # 1 overview + 2 steps + 1 escalation = 4 calls
        assert store.upsert_structured_chunk.call_count == 4

    @pytest.mark.asyncio
    async def test_categories_populated(self):
        kb = SOPKnowledgeBase()
        record = _make_record(sop_id="SOP-RF-001", fault_category="signal_loss")
        report = await kb.index_all([record], self._mock_embedder(), self._mock_store())
        assert "signal_loss" in report.categories

    @pytest.mark.asyncio
    async def test_multiple_records(self):
        kb = SOPKnowledgeBase()
        r1 = _make_record(sop_id="SOP-RF-001", fault_category="signal_loss", steps=["S1"])
        r2 = _make_record(sop_id="SOP-NET-002", fault_category="node_down", steps=["N1", "N2"])
        store = self._mock_store()
        report = await kb.index_all([r1, r2], self._mock_embedder(), store)
        # r1: 1+1+1=3, r2: 1+2+1=4 → total 7
        assert report.indexed == 7

    @pytest.mark.asyncio
    async def test_embed_error_goes_to_failed(self):
        kb = SOPKnowledgeBase()
        record = _make_record()
        embedder = MagicMock()
        embedder.embed_batch = AsyncMock(side_effect=RuntimeError("embed failed"))
        report = await kb.index_all([record], embedder, self._mock_store())
        assert report.total_failed == 1

    @pytest.mark.asyncio
    async def test_chunk_type_passed_to_upsert(self):
        kb = SOPKnowledgeBase()
        record = _make_record(steps=["Only step"])
        store = self._mock_store()
        await kb.index_all([record], self._mock_embedder(), store)
        chunk_types = [
            call.kwargs["chunk_type"]
            for call in store.upsert_structured_chunk.call_args_list
        ]
        assert "overview" in chunk_types
        assert "step" in chunk_types
        assert "escalation" in chunk_types

    @pytest.mark.asyncio
    async def test_fault_category_passed_to_upsert(self):
        kb = SOPKnowledgeBase()
        record = _make_record(fault_category="signal_loss", steps=["A"])
        store = self._mock_store()
        await kb.index_all([record], self._mock_embedder(), store)
        categories = [
            call.kwargs["fault_category"]
            for call in store.upsert_structured_chunk.call_args_list
        ]
        assert all(c == "signal_loss" for c in categories)


# ---------------------------------------------------------------------------
# SOPLoadReport
# ---------------------------------------------------------------------------

class TestSOPLoadReport:
    def test_total_loaded(self):
        report = SOPLoadReport(loaded=["A", "B", "C"])
        assert report.total_loaded == 3

    def test_total_failed(self):
        report = SOPLoadReport(failed=[("a.md", "err1"), ("b.md", "err2")])
        assert report.total_failed == 2

    def test_summary_contains_counts(self):
        report = SOPLoadReport(
            loaded=["SOP-RF-001", "SOP-NET-002"],
            failed=[("bad.md", "missing field")],
            indexed=10,
            categories={"signal_loss": ["SOP-RF-001"], "node_down": ["SOP-NET-002"]},
        )
        summary = report.summary()
        assert "loaded=2" in summary
        assert "failed=1" in summary
        assert "chunks_indexed=10" in summary
        assert "signal_loss" in summary
        assert "node_down" in summary
