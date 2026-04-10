"""
Domain models for the fault classifier.

AffectedLayer maps network faults to the OSI layer where they originate:

  physical   (L1) — cable cuts, antenna misalignment, hardware failure,
                     power loss, signal degradation.
                     Fault types: signal_loss, hardware_failure,
                     node_down (physical power/hardware root-cause)

  transport  (L2/L3) — packet forwarding, routing, switching, QoS,
                        congestion on backbone links.
                        Fault types: latency, packet_loss, congestion,
                        node_down (routing/switching root-cause)

  service    (L4–L7) — misconfiguration, DNS, BGP policy, application
                        service degradation, provisioning errors.
                        Fault types: configuration_error,
                        node_down (software/service root-cause)
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.models.telco_ticket import FaultType


class AffectedLayer(str, Enum):
    PHYSICAL  = "physical"   # OSI L1 — cables, antennas, hardware
    TRANSPORT = "transport"  # OSI L2/L3 — routing, switching, QoS
    SERVICE   = "service"    # OSI L4-L7 — config, DNS, BGP policy, apps


class ClassificationRequest(BaseModel):
    """Input to POST /classify."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=4000,
        description="Raw ticket text (description, subject, or concatenated fields).",
        examples=[
            "High packet loss on backbone RTR-LON-CORE-03. BGP session flapping "
            "between AS64512 and AS64513. 15% drop rate for the last 20 minutes."
        ],
    )


class ClassificationResult(BaseModel):
    """
    Structured output of FaultClassifier.classify().

    fault_type          — one of the FaultType enum values
    affected_layer      — physical / transport / service
    confidence_score    — 0.0 (uncertain) to 1.0 (certain)
    reasoning           — one-sentence justification from the model
    similar_ticket_ids  — up to 3 IDs of resolved historical tickets
                          ranked by cosine similarity to the input text
    model               — Anthropic model ID used for classification
    latency_ms          — wall-clock time for the full classify() call
    """
    fault_type:          FaultType
    affected_layer:      AffectedLayer
    confidence_score:    float          = Field(ge=0.0, le=1.0)
    reasoning:           str
    similar_ticket_ids:  list[str]      = Field(default_factory=list)
    model:               str
    latency_ms:          int
