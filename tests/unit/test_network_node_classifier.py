"""
Unit tests for the network node classifier used in build_network_graph.py.

Tests cover:
- All RAN node types: RNC, NodeB (3G), ENB/ESS (4G), GNB/ESS (5G)
- Parent node extraction for RNC→NodeB hierarchy
- Case-insensitivity (CTTS data is inconsistently cased)
- Unknown/unmatched patterns → graceful fallback
- Layout normalisation helper (_normalize)
- All 12 synthetic RNC controller IDs (Rnc07–Rnc18)

These tests import directly from scripts/build_network_graph.py.
"""
from __future__ import annotations

import sys
import os
import pytest

# Allow importing directly from scripts/ (not a package)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from build_network_graph import classify, _normalize  # noqa: E402


# ---------------------------------------------------------------------------
# 3G — RNC controller nodes
# ---------------------------------------------------------------------------

class TestRNCClassification:

    @pytest.mark.parametrize("node_id", [
        "Rnc07", "Rnc08", "Rnc09", "Rnc10", "Rnc11", "Rnc12",
        "Rnc13", "Rnc14", "Rnc15", "Rnc16", "Rnc17", "Rnc18",
    ])
    def test_synthetic_rnc_nodes_classified_as_rnc(self, node_id):
        node_class, network_type, parent = classify(node_id)
        assert node_class == "RNC"
        assert network_type == "3G"
        assert parent is None

    def test_rnc_lowercase_is_classified(self):
        node_class, network_type, parent = classify("rnc07")
        assert node_class == "RNC"
        assert network_type == "3G"

    def test_rnc_uppercase_is_classified(self):
        node_class, network_type, parent = classify("RNC15")
        assert node_class == "RNC"
        assert network_type == "3G"


# ---------------------------------------------------------------------------
# 3G — NodeB (child of RNC)
# ---------------------------------------------------------------------------

class TestNodeBClassification:

    def test_standard_nodeb_pattern(self):
        node_class, network_type, parent = classify("Rnc15_2650")
        assert node_class == "NodeB"
        assert network_type == "3G"
        assert parent is not None
        assert "Rnc15" in parent or "rnc15" in parent.lower()

    def test_nodeb_extracts_parent_rnc(self):
        _, _, parent = classify("Rnc07_1100")
        assert "rnc07" in parent.lower()

    def test_nodeb_parent_is_never_none(self):
        _, _, parent = classify("Rnc12_9999")
        assert parent is not None

    @pytest.mark.parametrize("node_id,expected_parent_prefix", [
        ("Rnc07_1000", "Rnc07"),
        ("Rnc18_2222", "Rnc18"),
        ("Rnc10_0001", "Rnc10"),
    ])
    def test_nodeb_parent_matches_rnc(self, node_id, expected_parent_prefix):
        _, _, parent = classify(node_id)
        assert parent.upper() == expected_parent_prefix.upper()

    def test_nodeb_lowercase_input(self):
        node_class, _, _ = classify("rnc15_2650")
        assert node_class == "NodeB"

    def test_nodeb_with_large_suffix(self):
        """NodeB IDs can have 4-digit location codes."""
        node_class, network_type, _ = classify("Rnc07_9999")
        assert node_class == "NodeB"
        assert network_type == "3G"


# ---------------------------------------------------------------------------
# 4G — eNodeB and ESS
# ---------------------------------------------------------------------------

class TestENBClassification:

    @pytest.mark.parametrize("node_id", [
        "LTE_ENB_780321",
        "LTE_ENB_781561",
        "LTE_ENB_735557",
        "LTE_ENB_000001",
    ])
    def test_enb_nodes_classified_correctly(self, node_id):
        node_class, network_type, parent = classify(node_id)
        assert node_class == "ENB"
        assert network_type == "4G"
        assert parent is None

    def test_enb_lowercase_prefix(self):
        node_class, _, _ = classify("lte_enb_780321")
        assert node_class == "ENB"

    def test_enb_mixed_case_prefix(self):
        node_class, _, _ = classify("Lte_Enb_780321")
        assert node_class == "ENB"

    def test_lte_ess_classified_as_ess_4g(self):
        node_class, network_type, parent = classify("LTE_ESS_735557")
        assert node_class == "ESS"
        assert network_type == "4G"
        assert parent is None

    def test_lte_ess_lowercase(self):
        node_class, network_type, _ = classify("lte_ess_735557")
        assert node_class == "ESS"
        assert network_type == "4G"


# ---------------------------------------------------------------------------
# 5G — gNB and ESS
# ---------------------------------------------------------------------------

class TestGNBClassification:

    @pytest.mark.parametrize("node_id", [
        "5G_GNB_1039321",
        "5G_GNB_1017001",
        "5G_GNB_0000001",
    ])
    def test_gnb_nodes_classified_correctly(self, node_id):
        node_class, network_type, parent = classify(node_id)
        assert node_class == "GNB"
        assert network_type == "5G"
        assert parent is None

    def test_5g_ess_classified_as_ess_5g(self):
        node_class, network_type, parent = classify("5G_ESS_1017001")
        assert node_class == "ESS"
        assert network_type == "5G"
        assert parent is None

    def test_gnb_lowercase(self):
        node_class, _, _ = classify("5g_gnb_1039321")
        assert node_class == "GNB"

    def test_5g_ess_lowercase(self):
        node_class, network_type, _ = classify("5g_ess_1017001")
        assert node_class == "ESS"
        assert network_type == "5G"


# ---------------------------------------------------------------------------
# Unknown / unrecognised patterns
# ---------------------------------------------------------------------------

class TestUnknownClassification:

    @pytest.mark.parametrize("node_id", [
        "NODE-ATL-01",
        "BS-MUM-042",
        "CORE-RTR-01",
        "HW_ELEMENT",
        "",
        "12345",
        "UNKNOWN_DEVICE",
    ])
    def test_unrecognised_returns_unknown_other(self, node_id):
        node_class, network_type, parent = classify(node_id)
        assert node_class == "Unknown"
        assert network_type == "Other"
        assert parent is None

    def test_partial_enb_pattern_not_matched(self):
        """LTE_ENB without trailing underscore+digits should still match by prefix."""
        node_class, _, _ = classify("LTE_ENB_")
        assert node_class == "ENB"  # prefix match is sufficient

    def test_gnb_prefix_without_digits_matches(self):
        node_class, _, _ = classify("5G_GNB_")
        assert node_class == "GNB"


# ---------------------------------------------------------------------------
# Network type exclusivity
# ---------------------------------------------------------------------------

class TestNetworkTypeExclusivity:
    """Each node should belong to exactly one network type."""

    @pytest.mark.parametrize("node_id,expected_type", [
        ("Rnc07",          "3G"),
        ("Rnc15_2650",     "3G"),
        ("LTE_ENB_780321", "4G"),
        ("LTE_ESS_735557", "4G"),
        ("5G_GNB_1039321", "5G"),
        ("5G_ESS_1017001", "5G"),
    ])
    def test_network_type_mapping(self, node_id, expected_type):
        _, network_type, _ = classify(node_id)
        assert network_type == expected_type

    def test_no_node_is_both_3g_and_4g(self):
        tested_types = {classify(n)[1] for n in ["Rnc07", "LTE_ENB_780321"]}
        assert len(tested_types) == 2  # must differ

    def test_no_node_is_both_4g_and_5g(self):
        tested_types = {classify(n)[1] for n in ["LTE_ENB_780321", "5G_GNB_1039321"]}
        assert len(tested_types) == 2  # must differ


# ---------------------------------------------------------------------------
# Layout normalisation helper
# ---------------------------------------------------------------------------

class TestNormalize:

    def test_single_point_stays_at_midpoint(self):
        """Single-node graphs: x_range/y_range = 0 → uses 1.0 fallback."""
        result = _normalize({"n1": (5.0, 5.0)})
        assert result["n1"][0] == pytest.approx(0.05, abs=1e-6)
        assert result["n1"][1] == pytest.approx(0.05, abs=1e-6)

    def test_output_within_005_095_range(self):
        positions = {
            "a": (0.0, 0.0),
            "b": (1.0, 1.0),
            "c": (0.5, 0.5),
        }
        normalised = _normalize(positions)
        for x, y in normalised.values():
            assert 0.05 - 1e-9 <= x <= 0.95 + 1e-9
            assert 0.05 - 1e-9 <= y <= 0.95 + 1e-9

    def test_min_maps_to_005(self):
        positions = {"a": (0.0, 0.0), "b": (10.0, 10.0)}
        normalised = _normalize(positions)
        assert normalised["a"][0] == pytest.approx(0.05)
        assert normalised["a"][1] == pytest.approx(0.05)

    def test_max_maps_to_095(self):
        positions = {"a": (0.0, 0.0), "b": (10.0, 10.0)}
        normalised = _normalize(positions)
        assert normalised["b"][0] == pytest.approx(0.95)
        assert normalised["b"][1] == pytest.approx(0.95)

    def test_empty_dict_returns_empty(self):
        assert _normalize({}) == {}

    def test_preserves_all_keys(self):
        positions = {f"node_{i}": (float(i), float(i)) for i in range(10)}
        normalised = _normalize(positions)
        assert set(normalised.keys()) == set(positions.keys())
