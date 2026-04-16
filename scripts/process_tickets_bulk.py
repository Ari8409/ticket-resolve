"""
Bulk ticket processor for Tickets.xlsx.

Resolution gate (strictly enforced):
  A ticket is RESOLVABLE only if:
    (a) A historically resolved similar ticket is found (cosine score >= threshold), OR
    (b) A matching SOP document is found (cosine score >= threshold).

  Otherwise the ticket is held for HUMAN REVIEW.

For resolvable tickets a dispatch mode is determined from fault type:
  hardware_failure / equipment → ON_SITE
  connectivity / comms         → REMOTE first, escalate if no SOP
  env / temperature            → REMOTE (alert + check NMS)
  else                         → REMOTE attempt

Output:
  - Console summary table
  - CSV: ticket_resolution_results.csv
"""
import asyncio
import csv
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from app.config import get_settings
from app.matching.engine import MatchingEngine
from app.matching.st_embedder import SentenceTransformerEmbedder
from app.matching.ticket_store import TicketStore
from app.models.telco_ticket import TelcoTicketCreate, FaultType, Severity
from app.sop.retriever import SOPRetriever
from app.sop.sop_store import SOPStore
from app.storage.chroma_client import ensure_collections

import chromadb
import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bulk_processor")

# ─── Resolution thresholds ──────────────────────────────────────────────────────
TICKET_SCORE_THRESHOLD = 0.60   # cosine similarity for historical ticket match
SOP_SCORE_THRESHOLD    = 0.45   # SOP chunks tend to be shorter, allow slightly lower
TOP_K_TICKETS          = 5
TOP_K_SOPS             = 3

# ─── Parser: CTTS description → ticket fields ──────────────────────────────────
_DESC_RE = re.compile(
    r"^(?P<node>[^\*]+)\*"
    r"(?P<alarm_category>[^/]+)/"
    r"(?P<alarm_name>[^\*]+)\*"
    r"(?P<severity>\d)\*"
    r"(?P<description>.+)$",
    re.DOTALL,
)
_ALARM_CAT_MAP = {
    "equipment alarm":          "equipmentAlarm",
    "environmental alarm":      "environmentalAlarm",
    "communications alarm":     "communicationsAlarm",
    "processing error alarm":   "processingErrorAlarm",
    "quality of service alarm": "qualityOfServiceAlarm",
}

def _infer_fault_type(alarm_name: str, alarm_category: str) -> FaultType:
    name = alarm_name.lower()
    cat  = alarm_category.lower()
    if any(k in name for k in ["hw fault", "equipment", "hardware", "cablefailure", "cable_failure",
                                 "digitalcable", "link failure", "antennabranchproblem",
                                 "antennabranch", "txbranchfailure", "vswr"]):
        return FaultType.HARDWARE_FAILURE
    if any(k in name for k in ["heartbeat", "no connection", "connection", "indoor rap",
                                 "inconsistent config"]):
        return FaultType.SIGNAL_LOSS
    if any(k in name for k in ["sync", "timing", "ptp", "sync reference", "sync time"]):
        return FaultType.SYNC_REFERENCE_QUALITY
    if any(k in name for k in ["temperature", "devicegroup_temperature", "battery", "input power",
                                 "running on battery", "power failure"]):
        return FaultType.NODE_DOWN   # power/env issues → treat as node down
    if any(k in name for k in ["sw error", "software", "license"]):
        return FaultType.SW_ERROR
    if any(k in name for k in ["resource activation"]):
        return FaultType.RESOURCE_ACTIVATION_TIMEOUT
    if any(k in name for k in ["service unavailable"]):
        return FaultType.SERVICE_UNAVAILABLE
    if any(k in name for k in ["carrier", "radio", "configuration"]):
        return FaultType.CONFIGURATION_ERROR
    if "equipment" in cat:
        return FaultType.HARDWARE_FAILURE
    if "environment" in cat:
        return FaultType.NODE_DOWN
    if "communication" in cat:
        return FaultType.SIGNAL_LOSS
    if "processing" in cat:
        return FaultType.SW_ERROR
    return FaultType.SIGNAL_LOSS

def _infer_network(node: str) -> str:
    n = node.upper()
    if n.startswith("5G") or n.startswith("NR") or n.startswith("SCS"):
        return "5G"
    if n.startswith("RNC") or node.upper().startswith("RNC"):
        return "3G"
    if n.startswith("LTE") or n.startswith("ENB"):
        return "4G"
    return "4G"

def parse_description(raw: str, index: int):
    raw = raw.replace("_x000D_", "").strip()
    m = _DESC_RE.match(raw)
    if not m:
        return None
    node     = m.group("node").strip()
    cat_raw  = m.group("alarm_category").strip()
    alarm    = re.sub(r"^[A-Z_]+/", "", m.group("alarm_name").strip())  # strip UNKNOWN/ prefix
    sev_int  = int(m.group("severity"))
    desc     = m.group("description").strip().replace("\n", " ")[:500]

    cat = _ALARM_CAT_MAP.get(cat_raw.lower(), cat_raw)
    fault_type   = _infer_fault_type(alarm, cat)
    network_type = _infer_network(node)

    sev_map = {1: Severity.CRITICAL, 2: Severity.HIGH, 3: Severity.MEDIUM, 4: Severity.LOW}
    severity = sev_map.get(sev_int, Severity.MEDIUM)

    return TelcoTicketCreate(
        ticket_id   = f"XLS-{index:04d}",
        affected_node = node,
        fault_type  = fault_type,
        severity    = severity,
        description = desc,
        network_type = network_type,
        alarm_name  = alarm,
        alarm_category = cat,
        timestamp   = __import__("datetime").datetime.utcnow(),
    )


# ─── Dispatch logic (no LLM) ───────────────────────────────────────────────────
def determine_dispatch(fault_type: FaultType, has_sop: bool, has_similar: bool) -> str:
    ft = fault_type
    if ft == FaultType.HARDWARE_FAILURE:
        return "ON_SITE"
    if ft == FaultType.NODE_DOWN:
        return "ON_SITE"
    if ft in (FaultType.SIGNAL_LOSS, FaultType.SYNC_REFERENCE_QUALITY,
              FaultType.SYNC_TIME_PHASE_ACCURACY):
        return "REMOTE" if (has_sop or has_similar) else "ESCALATE"
    if ft in (FaultType.SW_ERROR, FaultType.RESOURCE_ACTIVATION_TIMEOUT,
              FaultType.SERVICE_UNAVAILABLE, FaultType.CONFIGURATION_ERROR):
        return "REMOTE"
    return "REMOTE"

def resolution_reason(has_similar: bool, best_sim: float,
                       has_sop: bool, best_sop: float) -> str:
    parts = []
    if has_similar:
        parts.append(f"similar_ticket(score={best_sim:.2f})")
    if has_sop:
        parts.append(f"sop_match(score={best_sop:.2f})")
    return " + ".join(parts) if parts else "no_match"


# ─── Main async worker ─────────────────────────────────────────────────────────
async def main():
    settings = get_settings()

    # Build Chroma client + collections
    from chromadb.config import Settings as ChromaSettings
    client = await chromadb.AsyncHttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    await ensure_collections(client, settings.TICKET_COLLECTION, settings.SOP_COLLECTION)
    ticket_col = await client.get_collection(settings.TICKET_COLLECTION)
    sop_col    = await client.get_collection(settings.SOP_COLLECTION)

    embedder      = SentenceTransformerEmbedder(model_name=settings.ST_MODEL, device=settings.ST_DEVICE)
    ticket_store  = TicketStore(ticket_col)
    sop_store     = SOPStore(sop_col)

    matching = MatchingEngine(
        embedder=embedder,
        ticket_store=ticket_store,
        top_k=TOP_K_TICKETS,
        score_threshold=TICKET_SCORE_THRESHOLD,
    )
    sop_retriever = SOPRetriever(
        embedder=embedder,
        sop_store=sop_store,
        top_k=TOP_K_SOPS,
    )

    # ── Load Excel ────────────────────────────────────────────────────────────
    path = Path(r"C:\Users\aritra.e.chatterjee\Downloads\Tickets.xlsx")
    df   = pd.read_excel(path)
    raw_descriptions = df.iloc[:, 0].astype(str).tolist()
    print(f"\n{'='*70}")
    print(f"  Bulk Ticket Processor — {len(raw_descriptions)} rows from {path.name}")
    print(f"{'='*70}")

    results = []
    counters = Counter()
    alarm_stats = defaultdict(lambda: Counter())

    total = len(raw_descriptions)
    t0 = time.time()

    for i, raw in enumerate(raw_descriptions):
        ticket = parse_description(raw, i + 1)
        if ticket is None:
            counters["parse_failed"] += 1
            results.append({
                "row": i + 1, "ticket_id": f"XLS-{i+1:04d}",
                "node": "", "alarm": "", "network": "", "fault_type": "",
                "outcome": "PARSE_FAILED", "dispatch": "-",
                "best_sim_score": 0, "best_sim_ticket": "",
                "best_sop_score": 0, "best_sop_id": "",
                "reason": "parse_failed",
            })
            continue

        query = f"{ticket.alarm_name} {ticket.fault_type.value} {ticket.affected_node} {ticket.description[:200]}"

        # ── Vector searches (no LLM) ────────────────────────────────────────
        sim_matches = await matching.find_similar(query)
        sop_matches = await sop_retriever.retrieve(query)

        # Filter SOP results by threshold
        sop_matches = [s for s in sop_matches if s.score >= SOP_SCORE_THRESHOLD]

        has_similar = len(sim_matches) > 0
        best_sim    = sim_matches[0].score if sim_matches else 0.0
        best_sim_id = sim_matches[0].ticket_id if sim_matches else ""

        has_sop     = len(sop_matches) > 0
        best_sop    = sop_matches[0].score if sop_matches else 0.0
        best_sop_id = sop_matches[0].sop_id if sop_matches else ""

        # ── Resolution gate ─────────────────────────────────────────────────
        gate_pass = has_similar or has_sop

        if gate_pass:
            dispatch = determine_dispatch(ticket.fault_type, has_sop, has_similar)
            outcome  = "RESOLVED"
            counters["resolved"] += 1
        else:
            dispatch = "HOLD_HUMAN_REVIEW"
            outcome  = "HELD"
            counters["held"] += 1

        reason = resolution_reason(has_similar, best_sim, has_sop, best_sop)
        alarm_stats[ticket.alarm_name][outcome] += 1

        results.append({
            "row":              i + 1,
            "ticket_id":        ticket.ticket_id,
            "node":             ticket.affected_node,
            "alarm":            ticket.alarm_name,
            "network":          ticket.network_type,
            "fault_type":       ticket.fault_type.value,
            "outcome":          outcome,
            "dispatch":         dispatch,
            "best_sim_score":   round(best_sim, 4),
            "best_sim_ticket":  best_sim_id,
            "best_sop_score":   round(best_sop, 4),
            "best_sop_id":      best_sop_id,
            "reason":           reason,
        })

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate    = (i + 1) / elapsed
            eta     = (total - i - 1) / rate
            print(f"  [{i+1:4d}/{total}] resolved={counters['resolved']}  "
                  f"held={counters['held']}  failed={counters['parse_failed']}  "
                  f"rate={rate:.1f}/s  ETA={eta:.0f}s")

    elapsed = time.time() - t0

    # ── Write CSV ─────────────────────────────────────────────────────────────
    out_path = Path("ticket_resolution_results.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_parsed  = counters["resolved"] + counters["held"]
    pct_resolved  = 100 * counters["resolved"] / total_parsed if total_parsed else 0
    pct_held      = 100 * counters["held"] / total_parsed if total_parsed else 0

    print(f"\n{'='*70}")
    print(f"  RESULTS SUMMARY  ({elapsed:.1f}s for {total} tickets)")
    print(f"{'='*70}")
    print(f"  Total rows         : {total}")
    print(f"  Parse failures     : {counters['parse_failed']}")
    print(f"  Successfully parsed: {total_parsed}")
    print(f"  [OK]  RESOLVED     : {counters['resolved']}  ({pct_resolved:.1f}%)")
    print(f"  [!!]  HELD (human) : {counters['held']}  ({pct_held:.1f}%)")

    # Dispatch breakdown for resolved
    dispatch_counts = Counter(r["dispatch"] for r in results if r["outcome"] == "RESOLVED")
    print(f"\n  Dispatch breakdown (resolved tickets):")
    for mode, cnt in dispatch_counts.most_common():
        print(f"    {mode:<25} {cnt:4d}")

    # Top 15 alarm types
    print(f"\n  Top alarm types (resolved / held):")
    print(f"  {'Alarm':<45} {'Resolved':>8} {'Held':>8}")
    print(f"  {'-'*45} {'-'*8} {'-'*8}")
    sorted_alarms = sorted(alarm_stats.items(), key=lambda x: -(x[1]["RESOLVED"]+x[1]["HELD"]))
    for alarm, counts in sorted_alarms[:20]:
        print(f"  {alarm[:44]:<45} {counts['RESOLVED']:>8} {counts['HELD']:>8}")

    print(f"\n  [CSV] Full results written to: {out_path.resolve()}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
