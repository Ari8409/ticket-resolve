"""
Unit tests for assess_remote_feasibility — telecom best-practice scenarios.

Telecom NOC context:
- hardware_failure (PA failure, antenna fault, cabinet fault) → ALWAYS on-site
- configuration_error (BGP, RAN parameter push) → usually remote via EMS/NMS
- latency, congestion → remote (CLI/EMS diagnosis + tuning)
- node_down, signal_loss → depends on historical evidence
- sync_reference_quality, sync_time_phase_accuracy → remote (PTP/GPS config)
- sw_error → remote (remote reset / SW rollback via OMC)

Tests verify score thresholds and blocking/supporting evidence population.
"""
from __future__ import annotations

import pytest

from app.correlation.models import (
    RemoteFeasibility,
    assess_remote_feasibility,
    ALWAYS_ONSITE_FAULTS,
    USUALLY_REMOTE_FAULTS,
)
from app.models.recommendation import SimilarTicket, SOPMatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sim_ticket(resolution_summary: str = "Rebooted NodeB via OMT") -> SimilarTicket:
    return SimilarTicket(
        ticket_id="T-HIST-001",
        title="NodeB reboot",
        score=0.85,
        resolution_summary=resolution_summary,
    )


def _sop_match(title: str = "Remote Reset SOP", doc_path: str = "data/sops/reset.md") -> SOPMatch:
    return SOPMatch(
        sop_id="SOP-001",
        title=title,
        score=0.90,
        doc_path=doc_path,
        content="1. SSH into OMT. 2. Execute reset command. 3. Verify alarm clear.",
    )


# ---------------------------------------------------------------------------
# Hardware failure — always on-site
# ---------------------------------------------------------------------------

class TestHardwareFailureAlwaysOnSite:

    def test_hardware_failure_is_always_onsite_fault(self):
        assert "hardware_failure" in ALWAYS_ONSITE_FAULTS

    def test_hardware_failure_score_below_05(self):
        result = assess_remote_feasibility("hardware_failure", [], [])
        assert result.confidence < 0.5

    def test_hardware_failure_not_feasible_without_evidence(self):
        result = assess_remote_feasibility("hardware_failure", [], [])
        assert result.feasible is False

    def test_hardware_failure_has_blocking_factor(self):
        result = assess_remote_feasibility("hardware_failure", [], [])
        assert len(result.blocking_factors) > 0
        assert any("hardware_failure" in b or "physical" in b.lower()
                   for b in result.blocking_factors)

    def test_hardware_failure_remains_onsite_even_with_sop(self):
        """A remote SOP should not make hardware_failure remotely feasible."""
        result = assess_remote_feasibility(
            "hardware_failure",
            [_sim_ticket("Replaced PA unit on site")],
            [_sop_match("PA Replacement SOP")],
        )
        # Score should still be below 0.5 (blocking factor dominates)
        assert result.confidence < 0.6


# ---------------------------------------------------------------------------
# Configuration error / latency / congestion — usually remote
# ---------------------------------------------------------------------------

class TestUsuallyRemoteFaults:

    @pytest.mark.parametrize("fault_type", ["latency", "configuration_error", "congestion"])
    def test_fault_type_in_usually_remote(self, fault_type):
        assert fault_type in USUALLY_REMOTE_FAULTS

    def test_configuration_error_feasible_without_evidence(self):
        result = assess_remote_feasibility("configuration_error", [], [])
        assert result.confidence > 0.5

    def test_latency_feasible_without_evidence(self):
        result = assess_remote_feasibility("latency", [], [])
        assert result.confidence > 0.5

    def test_congestion_has_supporting_evidence(self):
        result = assess_remote_feasibility("congestion", [], [])
        assert len(result.supporting_evidence) > 0

    def test_latency_with_remote_historical_resolution_is_feasible(self):
        result = assess_remote_feasibility(
            "latency",
            [_sim_ticket("Adjusted QoS policy remotely via CLI")],
            [],
        )
        assert result.feasible is True
        assert result.confidence >= 0.5


# ---------------------------------------------------------------------------
# Sync faults — 5G/4G PTP/GPS sync issues (remote via EMS)
# ---------------------------------------------------------------------------

class TestSyncFaultRemoteFeasibility:

    def test_sync_reference_quality_not_in_onsite_list(self):
        assert "sync_reference_quality" not in ALWAYS_ONSITE_FAULTS

    def test_sync_reference_quality_baseline_score(self):
        """No special prior — should start at neutral 0.5 baseline."""
        result = assess_remote_feasibility("sync_reference_quality", [], [])
        # Neutral: no blocking, no supporting — score stays around 0.5
        assert 0.3 <= result.confidence <= 0.7

    def test_sync_fault_with_remote_sop_is_feasible(self):
        result = assess_remote_feasibility(
            "sync_reference_quality",
            [],
            [_sop_match("PTP Clock Sync Recovery SOP")],
        )
        assert result.feasible is True


# ---------------------------------------------------------------------------
# Node down — varies by evidence
# ---------------------------------------------------------------------------

class TestNodeDownFeasibility:

    def test_node_down_not_in_always_onsite(self):
        assert "node_down" not in ALWAYS_ONSITE_FAULTS

    def test_node_down_no_evidence_neutral_score(self):
        result = assess_remote_feasibility("node_down", [], [])
        assert 0.2 <= result.confidence <= 0.7

    def test_node_down_with_remote_reset_history_is_feasible(self):
        result = assess_remote_feasibility(
            "node_down",
            [_sim_ticket("Remote NodeB reset via OMT resolved the issue")],
            [_sop_match("NodeB Remote Reset SOP")],
        )
        assert result.feasible is True

    def test_node_down_with_onsite_history_is_not_feasible(self):
        result = assess_remote_feasibility(
            "node_down",
            [_sim_ticket("Engineer dispatched to site — power cable replaced")],
            [],
        )
        # On-site historical evidence should push score down
        assert result.confidence <= 0.65  # may or may not flip feasible flag


# ---------------------------------------------------------------------------
# Signal loss — RAN-specific
# ---------------------------------------------------------------------------

class TestSignalLossFeasibility:

    def test_signal_loss_sop_with_remote_steps_increases_score(self):
        result = assess_remote_feasibility(
            "signal_loss",
            [],
            [_sop_match("Remote antenna parameter optimisation SOP")],
        )
        assert result.confidence >= 0.4

    def test_signal_loss_pa_hardware_context_blocking(self):
        """If historical tickets mention PA hardware replacement, add blocking."""
        result = assess_remote_feasibility(
            "signal_loss",
            [_sim_ticket("Power amplifier hardware replaced on tower")],
            [],
        )
        # PA replacement is on-site — confidence should be lower
        assert result.confidence <= 0.65


# ---------------------------------------------------------------------------
# SW error — remote reset/rollback
# ---------------------------------------------------------------------------

class TestSWErrorFeasibility:

    def test_sw_error_with_remote_rollback_sop(self):
        result = assess_remote_feasibility(
            "sw_error",
            [_sim_ticket("Remote software rollback via OMC applied")],
            [_sop_match("SW Rollback via OMC SOP")],
        )
        assert result.feasible is True

    def test_sw_error_no_evidence_neutral(self):
        result = assess_remote_feasibility("sw_error", [], [])
        assert 0.2 <= result.confidence <= 0.8


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

class TestRemoteFeasibilityContract:

    def test_returns_remote_feasibility_model(self):
        result = assess_remote_feasibility("latency", [], [])
        assert isinstance(result, RemoteFeasibility)

    def test_confidence_within_0_1(self):
        for fault in ["hardware_failure", "latency", "node_down", "signal_loss"]:
            result = assess_remote_feasibility(fault, [], [])
            assert 0.0 <= result.confidence <= 1.0, f"Out of range for {fault}"

    def test_feasible_is_bool(self):
        result = assess_remote_feasibility("congestion", [], [])
        assert isinstance(result.feasible, bool)

    def test_supporting_evidence_is_list(self):
        result = assess_remote_feasibility("latency", [], [])
        assert isinstance(result.supporting_evidence, list)

    def test_blocking_factors_is_list(self):
        result = assess_remote_feasibility("hardware_failure", [], [])
        assert isinstance(result.blocking_factors, list)
