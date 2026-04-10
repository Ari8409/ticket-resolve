"""
Prompts and tool schema for the Claude-powered fault classifier.

Design decisions
----------------
Tool use (function calling) is used instead of free-text prompting because:
  1. Claude is forced to emit a validated JSON structure — no regex parsing.
  2. `tool_choice={"type": "tool", "name": "classify_fault"}` guarantees
     the tool is always called, even when the input is ambiguous.
  3. The input_schema acts as a contract that the model must satisfy,
     reducing hallucinated or out-of-enum values.

Layer classification guidelines baked into the system prompt:
  physical   → L1 symptoms: no signal, hardware alarm, power fault,
               antenna degradation, fibre cut, RRU offline
  transport  → L2/L3 symptoms: packet loss, latency spike, BGP flap,
               route churn, congestion, QoS violation
  service    → L4-L7 symptoms: config error, DNS failure, AAA issue,
               provisioning mismatch, software crash, API timeout
"""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are an expert NOC (Network Operations Centre) analyst specialising in \
telco network fault classification.

Your task is to classify an incoming network fault ticket by:
  1. Identifying the FAULT TYPE from the provided taxonomy.
  2. Identifying the AFFECTED OSI LAYER (physical / transport / service).
  3. Providing a CONFIDENCE SCORE (0.0–1.0) reflecting certainty.
  4. Writing a concise one-sentence REASONING for your decision.

--- FAULT TYPE TAXONOMY ---
signal_loss        Physical signal degradation (RSSI drop, Rx power below threshold)
latency            RTT or jitter elevated above baseline
node_down          Node, base-station, or router completely unreachable
packet_loss        Elevated frame/packet drop rate (>1% sustained)
congestion         Bandwidth saturation causing queuing / throttling
hardware_failure   Physical component failure (PSU, line-card, SFP, RRU)
configuration_error  Misconfiguration causing service disruption (BGP policy, VLAN, ACL)
unknown            Cannot determine fault type from available information

--- LAYER CLASSIFICATION RULES ---
physical   (L1) — Cable cuts, antenna misalignment, hardware failure, power loss,
                  signal below threshold, RRU offline, ODU fault.
                  Common fault types: signal_loss, hardware_failure, node_down (when
                  caused by physical/power failure).

transport  (L2/L3) — Packet forwarding, routing protocol issues, switching loops,
                      QoS/queuing, congestion on backbone links, BGP session flapping,
                      MPLS label errors.
                      Common fault types: latency, packet_loss, congestion, node_down
                      (when caused by routing/switching failure).

service    (L4–L7) — Misconfiguration of network services, DNS resolution, AAA/RADIUS,
                     provisioning errors, API timeouts, software crashes, firewall rules.
                     Common fault types: configuration_error, node_down (when caused by
                     a service/software crash with hardware healthy).

--- SCORING GUIDANCE ---
0.90–1.00 : Unambiguous — multiple strong signal keywords present.
0.70–0.89 : Likely — primary indicators present, minor ambiguity.
0.50–0.69 : Uncertain — limited detail, could fit multiple categories.
0.30–0.49 : Weak signal — mostly inferred; missing key diagnostic data.
0.00–0.29 : Very uncertain — use fault_type = "unknown".

Always call the `classify_fault` tool. Never respond with plain text.
"""

# ---------------------------------------------------------------------------
# Tool schema — passed to the Anthropic messages API
# ---------------------------------------------------------------------------

CLASSIFY_TOOL: dict = {
    "name": "classify_fault",
    "description": (
        "Classify a telco network fault ticket into a fault type and affected "
        "OSI layer, with a confidence score and brief reasoning."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "fault_type": {
                "type": "string",
                "enum": [
                    "signal_loss",
                    "latency",
                    "node_down",
                    "packet_loss",
                    "congestion",
                    "hardware_failure",
                    "configuration_error",
                    "unknown",
                ],
                "description": "The classified fault type from the taxonomy.",
            },
            "affected_layer": {
                "type": "string",
                "enum": ["physical", "transport", "service"],
                "description": (
                    "OSI layer where the fault originates: "
                    "'physical' (L1), 'transport' (L2/L3), or 'service' (L4-L7)."
                ),
            },
            "confidence_score": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence in the classification (0.0 = uncertain, 1.0 = certain).",
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "One concise sentence explaining why this fault type and layer "
                    "were chosen. Cite specific keywords from the ticket."
                ),
            },
        },
        "required": ["fault_type", "affected_layer", "confidence_score", "reasoning"],
    },
}

# Force the model to always invoke classify_fault, never reply in plain text
TOOL_CHOICE: dict = {"type": "tool", "name": "classify_fault"}
