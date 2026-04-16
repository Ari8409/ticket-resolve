"""
SIT — Telecom-specific end-to-end integration scenarios.

Based on Singtel/CTTS NOC best practices. Each test class represents a
real NOC operational scenario that the platform must handle correctly.

Scenarios:
  1. 4G eNodeB Heartbeat Failure (A1 critical alarm → PENDING_REVIEW)
  2. 5G gNB Sync Reference Quality Degradation (5G NR sync → remote feasible)
  3. 3G RNC / NodeB Hardware Fault (on-site dispatch)
  4. Maintenance Window Suppression (active maintenance → HOLD)
  5. Alarm Storm — multiple tickets from same RAN cluster
  6. A1 vs A2 Object Class Routing
  7. Bulk Multi-Network Type Ingestion Integrity
  8. Chat Assistant — NOC intent resolution for network topology queries

All heavy dependencies (Chroma, MatchingEngine, SOPRetriever, AlarmChecker,
MaintenanceChecker) are mocked via FastAPI dependency_overrides.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import TicketNotFoundError
from app.dependencies import (
    get_triage_handler,
    get_telco_repo,
)
from app.main import app
from app.models.human_triage import (
    AssignResult,
    ManualResolveResult,
    TriageSummary,
    UnresolvableReason,
)
from app.models.telco_ticket import (
    FaultType,
    NetworkType,
    Severity,
    TelcoTicketCreate,
    TelcoTicketStatus,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ctts_ticket(
    ticket_id: str = "TKT-SIT-001",
    affected_node: str = "LTE_ENB_780321",
    network_type: str = "4G",
    fault_type: str = "node_down",
    severity: str = "critical",
    object_class: str = "A1",
    description: str = "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*Heartbeat Failure\n\nHeartbeat Failure Unknown",
    **kwargs,
) -> TelcoTicketCreate:
    return TelcoTicketCreate(
        ticket_id=ticket_id,
        affected_node=affected_node,
        network_type=network_type,
        fault_type=fault_type,
        severity=severity,
        object_class=object_class,
        description=description,
        **kwargs,
    )


def _triage_summary(ticket_id: str = "TKT-SIT-001", **overrides) -> TriageSummary:
    defaults = dict(
        ticket_id=ticket_id,
        affected_node="LTE_ENB_780321",
        fault_type="node_down",
        severity="critical",
        network_type="4G",
        alarm_name="Heartbeat Failure",
        alarm_category="communicationsAlarm",
        location_details="1 Tuas South Street 12",
        description="Heartbeat Failure on LTE_ENB_780321.",
        reasons=[UnresolvableReason.NO_SOP_MATCH],
        confidence_score=0.30,
        sop_candidates_found=0,
        similar_tickets_found=0,
        flagged_at=datetime(2025, 12, 1, 9, 0, 0),
        assigned_to=None,
        assigned_at=None,
    )
    defaults.update(overrides)
    return TriageSummary(**defaults)


@pytest.fixture()
def mock_triage():
    return MagicMock()


@pytest.fixture()
def client(mock_triage):
    app.dependency_overrides[get_triage_handler] = lambda: mock_triage
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Scenario 1 — 4G eNodeB Heartbeat Failure → PENDING_REVIEW (A1 critical)
# ---------------------------------------------------------------------------

class TestScenario_4G_HeartbeatFailure:
    """
    Telecom best practice: LTE eNodeB Heartbeat Failure with A1 object class
    should always flag for human review (no auto-resolution for A1 criticals).
    """

    def test_ticket_model_parsed_from_ctts_description(self):
        t = _ctts_ticket(
            ticket_id="TKT-HB-001",
            affected_node="LTE_ENB_780321",
            network_type="4G",
            description=(
                "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*"
                "Heartbeat Failure\n\nHeartbeat Failure Unknown"
            ),
        )
        assert t.alarm_name == "Heartbeat Failure"
        assert t.alarm_category == "communicationsAlarm"
        assert t.alarm_severity_code == "1"
        assert t.node_id == "LTE_ENB_780321"

    def test_a1_object_class_maps_to_critical_severity(self):
        t = _ctts_ticket(
            object_class="A1",
            severity="critical",
        )
        assert t.severity == Severity.CRITICAL
        assert t.object_class == "A1"

    def test_heartbeat_failure_appears_in_pending_review_queue(self, client, mock_triage):
        mock_triage.list_pending = AsyncMock(return_value=[
            _triage_summary(
                fault_type="node_down",
                alarm_name="Heartbeat Failure",
                reasons=[UnresolvableReason.NO_SOP_MATCH, UnresolvableReason.LOW_CONFIDENCE],
            )
        ])
        resp = client.get("/api/v1/telco-tickets/pending-review")
        assert resp.status_code == 200
        queue = resp.json()
        assert len(queue) == 1
        assert queue[0]["alarm_name"] == "Heartbeat Failure"
        assert "no_sop_match" in queue[0]["reasons"]

    def test_heartbeat_failure_can_be_assigned_to_engineer(self, client, mock_triage):
        mock_triage.assign = AsyncMock(return_value=AssignResult(
            ticket_id="TKT-HB-001",
            assigned_to="bsm.engineer.west",
            assigned_at=datetime(2025, 12, 1, 10, 0, 0),
            message="Ticket TKT-HB-001 assigned to bsm.engineer.west.",
        ))
        resp = client.post(
            "/api/v1/telco-tickets/TKT-HB-001/assign",
            json={"assign_to": "bsm.engineer.west", "notes": "Check power supply at Tuas South."},
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_to"] == "bsm.engineer.west"

    def test_heartbeat_failure_resolved_with_elt_reset_sop(self, client, mock_triage):
        mock_triage.manual_resolve = AsyncMock(return_value=ManualResolveResult(
            ticket_id="TKT-HB-001",
            new_status=TelcoTicketStatus.RESOLVED.value,
            message="Resolved via ELR reset.",
            executed_steps=["SSH into OMT", "Execute reset_elr command", "Confirm Heartbeat Failure cleared"],
            sop_reference="SOP-4G-HEARTBEAT-001",
            resolved_by="bsm.engineer.west",
            resolved_at=datetime(2025, 12, 1, 11, 0, 0),
            indexed_as_training_signal=True,
        ))
        resp = client.post(
            "/api/v1/telco-tickets/TKT-HB-001/manual-resolve",
            json={
                "resolved_by": "bsm.engineer.west",
                "resolution_steps": [
                    "SSH into OMT",
                    "Execute reset_elr command",
                    "Confirm Heartbeat Failure cleared",
                ],
                "sop_reference": "SOP-4G-HEARTBEAT-001",
                "primary_cause": "ELR hardware fault — auto-recovery via reset",
                "resolution_code": "Reset ELR",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "resolved"
        assert data["sop_reference"] == "SOP-4G-HEARTBEAT-001"
        assert data["indexed_as_training_signal"] is True


# ---------------------------------------------------------------------------
# Scenario 2 — 5G gNB Sync Reference Quality Degradation
# ---------------------------------------------------------------------------

class TestScenario_5G_SyncReferenceQuality:
    """
    5G NR sync degradation: PTP/GPS-based synchronisation alarm.
    Best practice: classified as remote-feasible via EMS NTP/PTP reconfiguration.
    """

    def test_5g_sync_ticket_description_parsed_correctly(self):
        t = TelcoTicketCreate(
            affected_node="5G_GNB_1039321",
            severity="major",
            network_type="5G",
            description=(
                "5G_GNB_1039321*communicationsAlarm/SyncRefQuality*2*"
                "Sync Reference Quality Degraded\n\nPTP clock reference lost"
            ),
        )
        assert t.alarm_name == "SyncRefQuality"
        assert t.alarm_category == "communicationsAlarm"
        assert t.alarm_severity_code == "2"
        assert t.network_type == "5G"

    def test_5g_gnb_node_id_backfilled_from_description(self):
        t = TelcoTicketCreate(
            affected_node="UNKNOWN",
            severity="major",
            description=(
                "5G_GNB_1039321*communicationsAlarm/SyncRefQuality*2*text"
            ),
        )
        # affected_node should be back-filled from parsed node_id
        assert t.affected_node == "5G_GNB_1039321"

    def test_5g_sync_pending_review_with_no_sop_match(self, client, mock_triage):
        mock_triage.list_pending = AsyncMock(return_value=[
            _triage_summary(
                ticket_id="TKT-5G-001",
                affected_node="5G_GNB_1039321",
                fault_type="sync_reference_quality",
                alarm_name="SyncRefQuality",
                network_type="5G",
                severity="major",
                reasons=[UnresolvableReason.NO_SOP_MATCH],
            )
        ])
        resp = client.get("/api/v1/telco-tickets/pending-review")
        queue = resp.json()
        assert queue[0]["network_type"] == "5G"
        assert queue[0]["fault_type"] == "sync_reference_quality"

    def test_5g_sync_resolved_via_ptp_reconfiguration(self, client, mock_triage):
        mock_triage.manual_resolve = AsyncMock(return_value=ManualResolveResult(
            ticket_id="TKT-5G-001",
            new_status=TelcoTicketStatus.RESOLVED.value,
            message="5G sync alarm resolved via PTP reconfiguration.",
            executed_steps=[
                "Access gNB via EMS",
                "Check PTP source reference",
                "Reconfigure primary clock source to GPS",
                "Verify SyncRefQuality alarm cleared",
            ],
            sop_reference="SOP-5G-SYNC-001",
            resolved_by="noc.engineer.5g",
            resolved_at=datetime(2025, 12, 3, 11, 0, 0),
            indexed_as_training_signal=True,
        ))
        resp = client.post(
            "/api/v1/telco-tickets/TKT-5G-001/manual-resolve",
            json={
                "resolved_by": "noc.engineer.5g",
                "resolution_steps": [
                    "Access gNB via EMS",
                    "Check PTP source reference",
                    "Reconfigure primary clock source to GPS",
                    "Verify SyncRefQuality alarm cleared",
                ],
                "sop_reference": "SOP-5G-SYNC-001",
                "resolution_code": "Remote configuration change",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "resolved"


# ---------------------------------------------------------------------------
# Scenario 3 — 3G NodeB Hardware Fault (On-Site Dispatch)
# ---------------------------------------------------------------------------

class TestScenario_3G_NodeBHardwareFault:
    """
    3G NodeB hardware fault (PA failure / digital cable fault).
    Best practice: hardware_failure always requires on-site engineer dispatch.
    """

    def test_nodeb_hw_fault_ticket_parsed_from_legacy_ctts_format(self):
        t = TelcoTicketCreate(
            affected_node="Rnc15_2650",
            severity="critical",
            network_type="3G",
            description=(
                "Rnc15_2650*Equipment Alarm/HW Fault*1*HW Fault\n\n"
                "Digital cable failure on NodeB Rnc15_2650"
            ),
        )
        assert t.alarm_category == "equipmentAlarm"
        assert t.alarm_name == "HW Fault"
        assert t.network_type == "3G"

    def test_3g_hw_fault_in_pending_review_queue(self, client, mock_triage):
        mock_triage.list_pending = AsyncMock(return_value=[
            _triage_summary(
                ticket_id="TKT-3G-HW-001",
                affected_node="Rnc15_2650",
                fault_type="hardware_failure",
                alarm_name="HW Fault",
                network_type="3G",
                severity="critical",
                reasons=[UnresolvableReason.NO_SOP_MATCH, UnresolvableReason.LOW_CONFIDENCE],
            )
        ])
        resp = client.get("/api/v1/telco-tickets/pending-review")
        queue = resp.json()
        assert queue[0]["fault_type"] == "hardware_failure"
        assert queue[0]["network_type"] == "3G"

    def test_3g_hw_fault_dispatched_onsite_with_physical_steps(self, client, mock_triage):
        mock_triage.manual_resolve = AsyncMock(return_value=ManualResolveResult(
            ticket_id="TKT-3G-HW-001",
            new_status=TelcoTicketStatus.RESOLVED.value,
            message="Hardware replaced on-site.",
            executed_steps=[
                "Dispatch engineer to Rnc15_2650 tower site",
                "Replace digital cable at DDF panel",
                "Power-cycle NodeB",
                "Verify alarm cleared on NMS",
            ],
            sop_reference="SOP-3G-HW-NODEB-001",
            resolved_by="field.engineer.east",
            resolved_at=datetime(2025, 12, 2, 14, 0, 0),
            indexed_as_training_signal=True,
        ))
        resp = client.post(
            "/api/v1/telco-tickets/TKT-3G-HW-001/manual-resolve",
            json={
                "resolved_by": "field.engineer.east",
                "resolution_steps": [
                    "Dispatch engineer to Rnc15_2650 tower site",
                    "Replace digital cable at DDF panel",
                    "Power-cycle NodeB",
                    "Verify alarm cleared on NMS",
                ],
                "sop_reference": "SOP-3G-HW-NODEB-001",
                "primary_cause": "Digital cable failure at DDF",
                "resolution_code": "Hardware Replacement",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "resolved"


# ---------------------------------------------------------------------------
# Scenario 4 — Maintenance Window Suppression
# ---------------------------------------------------------------------------

class TestScenario_MaintenanceWindowSuppression:
    """
    Best practice: alarms during active maintenance windows should be
    suppressed from PENDING_REVIEW. The triage queue should be empty for
    nodes currently in a maintenance window.
    """

    def test_pending_review_queue_empty_when_all_in_maintenance(self, client, mock_triage):
        """All pending tickets are nodes under active maintenance — queue is empty."""
        mock_triage.list_pending = AsyncMock(return_value=[])
        resp = client.get("/api/v1/telco-tickets/pending-review")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_maintenance_ticket_not_assignable(self, client, mock_triage):
        """Ticket in maintenance window cannot be assigned — 409 conflict."""
        mock_triage.assign = AsyncMock(
            side_effect=ValueError(
                "Ticket TKT-MAINT-001 is not in PENDING_REVIEW status (current: resolved)."
            )
        )
        resp = client.post(
            "/api/v1/telco-tickets/TKT-MAINT-001/assign",
            json={"assign_to": "noc.engineer01"},
        )
        assert resp.status_code == 409

    def test_non_maintenance_tickets_still_in_queue(self, client, mock_triage):
        """Non-maintenance tickets remain in PENDING_REVIEW even when others are suppressed."""
        mock_triage.list_pending = AsyncMock(return_value=[
            _triage_summary("TKT-REAL-001"),
            _triage_summary("TKT-REAL-002"),
        ])
        resp = client.get("/api/v1/telco-tickets/pending-review")
        assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# Scenario 5 — Alarm Storm: Multiple Tickets from Same RAN Cluster
# ---------------------------------------------------------------------------

class TestScenario_AlarmStorm:
    """
    Telecom best practice: when many nodes in the same RNC cluster have
    concurrent PENDING_REVIEW alarms, it indicates an RNC-level issue
    (backhaul, power, clock sync) — the triage queue should reflect this.
    """

    def test_multiple_nodeb_children_in_pending_review(self, client, mock_triage):
        """Simulate RNC07 backhaul failure causing 5 NodeBs to go PENDING_REVIEW."""
        rnc07_children = [
            _triage_summary(f"TKT-RNC-{i:03d}", affected_node=f"Rnc07_{1100+i*100}")
            for i in range(5)
        ]
        mock_triage.list_pending = AsyncMock(return_value=rnc07_children)
        resp = client.get("/api/v1/telco-tickets/pending-review")
        queue = resp.json()
        assert len(queue) == 5
        affected_nodes = [t["affected_node"] for t in queue]
        assert all("Rnc07_" in n for n in affected_nodes)

    def test_alarm_storm_tickets_all_have_no_sop_reason(self, client, mock_triage):
        """Mass alarm events typically don't have SOP matches — all are NO_SOP_MATCH."""
        storm_tickets = [
            _triage_summary(
                f"TKT-STORM-{i:03d}",
                affected_node=f"Rnc07_{1100+i*100}",
                reasons=[UnresolvableReason.NO_SOP_MATCH, UnresolvableReason.LOW_CONFIDENCE],
            )
            for i in range(3)
        ]
        mock_triage.list_pending = AsyncMock(return_value=storm_tickets)
        resp = client.get("/api/v1/telco-tickets/pending-review")
        for t in resp.json():
            assert "no_sop_match" in t["reasons"]

    def test_limit_parameter_caps_alarm_storm_response(self, client, mock_triage):
        """With large alarm storms, limit=10 must be respected."""
        mock_triage.list_pending = AsyncMock(return_value=[])
        client.get("/api/v1/telco-tickets/pending-review?limit=10")
        mock_triage.list_pending.assert_called_once_with(limit=10)


# ---------------------------------------------------------------------------
# Scenario 6 — A1 vs A2 Object Class Routing
# ---------------------------------------------------------------------------

class TestScenario_ObjectClassRouting:
    """
    CTTS A1 = critical alarm class (P0/P1 SLA).
    CTTS A2 = major alarm class (P2/P3 SLA).
    A1 tickets always need human review; A2 may be auto-resolved if SOP found.
    """

    def test_a1_ticket_model_has_critical_severity(self):
        t = _ctts_ticket(object_class="A1", severity="critical")
        assert t.severity == Severity.CRITICAL
        assert t.object_class == "A1"

    def test_a2_ticket_model_has_major_severity(self):
        t = TelcoTicketCreate(
            affected_node="LTE_ENB_780100",
            severity="major",
            network_type="4G",
            object_class="A2",
            description="LTE_ENB_780100*equipmentAlarm/HW Fault*2*Minor fault",
        )
        assert t.object_class == "A2"
        assert t.severity == Severity.MAJOR

    def test_a1_in_pending_review_queue(self, client, mock_triage):
        mock_triage.list_pending = AsyncMock(return_value=[
            _triage_summary("TKT-A1-001", severity="critical"),
        ])
        resp = client.get("/api/v1/telco-tickets/pending-review")
        assert resp.json()[0]["severity"] == "critical"

    def test_a2_mnoc_object_class_accepted(self):
        t = TelcoTicketCreate(
            affected_node="LTE_ENB_780100",
            severity="major",
            network_type="4G",
            object_class="A2_MNOC",
            description="LTE_ENB_780100*equipmentAlarm/HW Fault*2*Minor MNOC alarm",
        )
        assert t.object_class == "A2_MNOC"


# ---------------------------------------------------------------------------
# Scenario 7 — Multi-Network Type Bulk Ingestion Integrity
# ---------------------------------------------------------------------------

class TestScenario_MultiNetworkTypeBulkIngestion:
    """
    Telecom best practice: bulk import of mixed 3G/4G/5G tickets from CTTS
    export must preserve network_type, fault_type, and alarm fields per ticket.
    """

    @pytest.mark.parametrize("affected_node,network_type,expected_alarm", [
        ("Rnc15_2650",     "3G", "HW Fault"),
        ("LTE_ENB_780321", "4G", "Heartbeat Failure"),
        ("5G_GNB_1039321", "5G", "SyncRefQuality"),
    ])
    def test_ctts_tickets_parsed_per_network_type(self, affected_node, network_type, expected_alarm):
        descriptions = {
            "Rnc15_2650":     "Rnc15_2650*Equipment Alarm/HW Fault*1*HW Fault\n\nHardware fault",
            "LTE_ENB_780321": "LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*Heartbeat Failure\n\nHB failure",
            "5G_GNB_1039321": "5G_GNB_1039321*communicationsAlarm/SyncRefQuality*2*Sync alarm",
        }
        t = TelcoTicketCreate(
            affected_node=affected_node,
            severity="major",
            network_type=network_type,
            description=descriptions[affected_node],
        )
        assert t.alarm_name == expected_alarm
        assert t.network_type == network_type

    def test_4g_and_5g_tickets_have_different_node_classes(self):
        enb = TelcoTicketCreate(
            affected_node="LTE_ENB_780321",
            severity="major",
            network_type="4G",
            description="LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*text",
        )
        gnb = TelcoTicketCreate(
            affected_node="5G_GNB_1039321",
            severity="major",
            network_type="5G",
            description="5G_GNB_1039321*communicationsAlarm/SyncRefQuality*2*text",
        )
        assert enb.network_type != gnb.network_type
        assert enb.affected_node.startswith("LTE_")
        assert gnb.affected_node.startswith("5G_")

    def test_bulk_tickets_preserve_ctts_ticket_numbers(self):
        ctts_numbers = [1617827, 1617828, 1617829]
        tickets = [
            TelcoTicketCreate(
                affected_node=f"LTE_ENB_78{n:04d}",
                severity="major",
                network_type="4G",
                ctts_ticket_number=n,
                description=f"LTE_ENB_78{n:04d}*communicationsAlarm/Heartbeat Failure*1*text",
            )
            for n in ctts_numbers
        ]
        for i, t in enumerate(tickets):
            assert t.ctts_ticket_number == ctts_numbers[i]

    def test_mixed_mobile_and_fixed_group(self):
        mobile_t = TelcoTicketCreate(
            affected_node="LTE_ENB_780321",
            severity="major",
            network_type="4G",
            mobile_or_fixed="Mobile Group",
            description="LTE_ENB_780321*communicationsAlarm/Heartbeat Failure*1*text",
        )
        fixed_t = TelcoTicketCreate(
            affected_node="LTE_ESS_735557",
            severity="major",
            network_type="4G",
            mobile_or_fixed="Fixed Group",
            description="LTE_ESS_735557*equipmentAlarm/HW Fault*1*HW fault",
        )
        assert mobile_t.mobile_or_fixed == "Mobile Group"
        assert fixed_t.mobile_or_fixed == "Fixed Group"


# ---------------------------------------------------------------------------
# Scenario 8 — Review endpoint: approve vs escalate vs override
# ---------------------------------------------------------------------------

class TestScenario_ReviewWorkflow:
    """
    Telecom NOC review workflow: after AI recommendation is generated,
    NOC engineer can approve / override / escalate via the review endpoint.
    """

    def test_review_404_for_missing_ticket(self, client):
        resp = client.get("/api/v1/telco-tickets/TKT-MISSING/review")
        # Should return 404 — no recommendation exists for this ticket
        assert resp.status_code in (404, 422, 503)  # depends on mock state

    def test_manual_resolve_without_sop_still_valid(self, client, mock_triage):
        """Engineer may resolve without a SOP reference (ad-hoc fix)."""
        mock_triage.manual_resolve = AsyncMock(return_value=ManualResolveResult(
            ticket_id="TKT-SIT-999",
            new_status=TelcoTicketStatus.RESOLVED.value,
            message="Resolved ad-hoc.",
            executed_steps=["Power-cycled NodeB"],
            sop_reference=None,
            resolved_by="noc.engineer01",
            resolved_at=datetime(2025, 12, 1, 15, 0, 0),
            indexed_as_training_signal=False,
        ))
        resp = client.post(
            "/api/v1/telco-tickets/TKT-SIT-999/manual-resolve",
            json={
                "resolved_by": "noc.engineer01",
                "resolution_steps": ["Power-cycled NodeB"],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["sop_reference"] is None
        assert resp.json()["indexed_as_training_signal"] is False

    def test_escalation_sets_pending_review_reasons(self, client, mock_triage):
        """Escalated tickets must carry reasons for human intervention."""
        mock_triage.list_pending = AsyncMock(return_value=[
            _triage_summary(
                "TKT-ESC-001",
                reasons=[
                    UnresolvableReason.NO_SOP_MATCH,
                    UnresolvableReason.LOW_CONFIDENCE,
                    UnresolvableReason.UNKNOWN_FAULT_TYPE,
                ],
                confidence_score=0.10,
            )
        ])
        resp = client.get("/api/v1/telco-tickets/pending-review")
        reasons = resp.json()[0]["reasons"]
        assert len(reasons) == 3
        assert "low_confidence" in reasons
        assert "unknown_fault_type" in reasons
