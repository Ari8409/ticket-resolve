"""
import_to_db.py — Import bulk-processed tickets into the SQLite database.

Reads:
  - ticket_resolution_results.csv  (resolution outcomes from bulk processor)
  - Tickets.xlsx                   (original descriptions)

Writes to:
  - data/tickets.db                (telco_tickets + telco_dispatch_decisions tables)
"""
import csv
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent          # ticket-resolve/
DB_PATH     = Path("C:/Users/aritra.e.chatterjee/R&D/data/tickets.db")
CSV_PATH    = ROOT / "ticket_resolution_results.csv"
XLSX_PATH   = Path("C:/Users/aritra.e.chatterjee/Downloads/Tickets.xlsx")

# ── Install check ─────────────────────────────────────────────────────────────
try:
    import sqlite3
    import pandas as pd
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)

# ── CTTS description parser (same logic as process_tickets_bulk.py) ────────────
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
_SEV_MAP = {1: "critical", 2: "high", 3: "medium", 4: "low"}

def parse_raw_description(raw: str):
    """Extract structured fields from CTTS description. Returns dict or None."""
    raw = raw.replace("_x000D_", "").replace("\\n", "\n").strip()
    m = _DESC_RE.match(raw)
    if not m:
        return None
    cat_raw = m.group("alarm_category").strip()
    alarm_name_raw = re.sub(r"^[A-Z_]+/", "", m.group("alarm_name").strip())
    return {
        "node_id":             m.group("node").strip(),
        "alarm_category":      _ALARM_CAT_MAP.get(cat_raw.lower(), cat_raw),
        "alarm_name":          alarm_name_raw,
        "alarm_severity_code": m.group("severity"),
        "severity":            _SEV_MAP.get(int(m.group("severity")), "medium"),
        "clean_desc":          (m.group("node").strip() + "*" +
                                _ALARM_CAT_MAP.get(cat_raw.lower(), cat_raw) + "/" +
                                alarm_name_raw + "*" +
                                m.group("severity") + "*" +
                                m.group("description").strip().replace("\n", " ")[:450]),
    }

# ── Dispatch mode normaliser ──────────────────────────────────────────────────
_DISPATCH_MAP = {
    "ON_SITE":           "on_site",
    "REMOTE":            "remote",
    "ESCALATE":          "escalate",
    "HOLD_HUMAN_REVIEW": "hold",
    "-":                 "hold",
}

def dispatch_mode(raw: str) -> str:
    return _DISPATCH_MAP.get(raw.strip(), "remote")

# ── Resolution steps generator ───────────────────────────────────────────────
def build_resolution_steps(outcome: str, dispatch: str, alarm: str, fault_type: str,
                            best_sim_ticket: str, best_sop_id: str, reason: str) -> list:
    if outcome == "HELD":
        return []
    mode = dispatch_mode(dispatch)
    if mode == "on_site":
        steps = [
            "Verify alarm on NMS — confirm not auto-cleared.",
            "Dispatch field engineer to site.",
            "Inspect hardware components and power supply.",
            "Replace or reseat faulty unit if identified.",
            "Restore service and verify alarm clearance on NMS.",
            "Update ticket with findings and close.",
        ]
    elif mode == "remote":
        steps = [
            "Check alarm status on NMS; confirm it is active.",
            "Review recent configuration changes on the node.",
            "Attempt remote restart / reset of affected process.",
            "Monitor for 15 minutes; confirm alarm clears.",
            "Escalate to field team if alarm persists after remote action.",
        ]
    elif mode == "escalate":
        steps = [
            "Verify alarm on NMS — confirm persistent.",
            "Escalate to Tier-2 / vendor support.",
            "Provide alarm details, node ID, and recent change history.",
            "Monitor pending Tier-2 feedback.",
        ]
    else:
        steps = ["Hold for human review — no SOP/history match found."]

    if best_sim_ticket:
        steps.append(f"Reference similar resolved ticket: {best_sim_ticket}")
    if best_sop_id:
        steps.append(f"Apply SOP: {best_sop_id.split('_chunk')[0]}")
    return steps


# ── Main import ──────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*65}")
    print(f"  DB Import: ticket_resolution_results.csv -> SQLite")
    print(f"{'='*65}")

    # Load inputs
    print("[1/4] Loading CSV results and Excel descriptions...")
    df_csv  = pd.read_csv(CSV_PATH)
    df_xlsx = pd.read_excel(XLSX_PATH)
    raw_descs = df_xlsx.iloc[:, 0].astype(str).tolist()
    print(f"      CSV rows  : {len(df_csv)}")
    print(f"      Excel rows: {len(raw_descs)}")

    # Connect to SQLite
    print("[2/4] Connecting to database...")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()

    # Clear existing tickets (re-import is idempotent)
    existing = cur.execute("SELECT COUNT(*) FROM telco_tickets").fetchone()[0]
    if existing > 0:
        print(f"      Clearing {existing} existing tickets...")
        cur.execute("DELETE FROM telco_dispatch_decisions")
        cur.execute("DELETE FROM telco_tickets")
        conn.commit()

    # Batch insert
    print("[3/4] Inserting tickets and dispatch decisions...")
    now = datetime.utcnow().isoformat()

    ticket_rows   = []
    dispatch_rows = []
    skipped       = 0
    resolved_cnt  = 0
    held_cnt      = 0

    for _, row in df_csv.iterrows():
        row_idx  = int(row["row"]) - 1           # 0-based Excel index
        outcome  = str(row["outcome"]).strip()

        if outcome == "PARSE_FAILED":
            skipped += 1
            continue

        # Get raw description from Excel
        raw_desc = raw_descs[row_idx] if row_idx < len(raw_descs) else ""
        parsed   = parse_raw_description(raw_desc)

        ticket_id   = str(row["ticket_id"])
        node        = str(row["node"])
        alarm       = str(row["alarm"])
        network     = str(row["network"])
        fault_type  = str(row["fault_type"])
        dispatch    = str(row["dispatch"])
        best_sim    = float(row["best_sim_score"])
        best_sim_id = str(row["best_sim_ticket"]) if pd.notna(row["best_sim_ticket"]) else ""
        best_sop    = float(row["best_sop_score"])
        best_sop_id = str(row["best_sop_id"]) if pd.notna(row["best_sop_id"]) else ""
        reason      = str(row["reason"])

        status = "resolved"     if outcome == "RESOLVED" else "pending_review"
        severity = parsed["severity"] if parsed else "major"
        alarm_category = parsed["alarm_category"] if parsed else None
        alarm_name = parsed["alarm_name"] if parsed else alarm
        alarm_sev_code = parsed["alarm_severity_code"] if parsed else None
        node_id = parsed["node_id"] if parsed else node
        description = parsed["clean_desc"] if parsed else raw_desc[:4000].replace("_x000D_", "")

        steps = build_resolution_steps(outcome, dispatch, alarm, fault_type,
                                       best_sim_id, best_sop_id, reason)
        pending_reasons = json.dumps(["no_similar_ticket", "no_sop_match"]) if outcome == "HELD" else None

        ticket_rows.append((
            ticket_id, None, now, None, None, None,
            fault_type, node, severity, status,
            description, json.dumps(steps),
            node_id, alarm_category, alarm_name, alarm_sev_code,
            None, None, None, None, None, None, None, None, None,
            None, None, network, None, None, None,
            None, None, None, None, None,
            pending_reasons, None, None,
            now, now,
        ))

        # Dispatch decision for every processed ticket
        d_mode = dispatch_mode(dispatch)
        escalation = 1 if d_mode == "escalate" else 0
        similar_ids = json.dumps([best_sim_id]) if best_sim_id else json.dumps([])
        sop_refs    = json.dumps([best_sop_id.split("_chunk")[0]]) if best_sop_id else json.dumps([])
        conf        = round(max(best_sim, best_sop), 4)
        reasoning   = reason

        dispatch_rows.append((
            ticket_id, d_mode, conf,
            json.dumps(steps), reasoning,
            escalation, sop_refs, similar_ids,
            1,                             # short_circuited (vector-only, no LLM)
            "vector_similarity_gate",      # short_circuit_reason
            None, None, None, None,
            now,
        ))

        if outcome == "RESOLVED":
            resolved_cnt += 1
        else:
            held_cnt += 1

    # Bulk insert tickets
    cur.executemany("""
        INSERT OR REPLACE INTO telco_tickets (
            ticket_id, ctts_ticket_number, timestamp,
            event_start_time, event_end_time, modified_date,
            fault_type, affected_node, severity, status,
            description, resolution_steps,
            node_id, alarm_category, alarm_name, alarm_severity_code,
            title, assignment_profile, "group", object_class,
            owner_profile, owner_profile_group, resolved_group,
            last_ack_by, resolved_person,
            source, category_group, network_type, mobile_or_fixed,
            location_details, location_id,
            primary_cause, remarks, resolution, resolution_code, sop_id,
            pending_review_reasons, assigned_to, assigned_at,
            created_at, updated_at
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """, ticket_rows)

    # Bulk insert dispatch decisions
    cur.executemany("""
        INSERT OR REPLACE INTO telco_dispatch_decisions (
            ticket_id, dispatch_mode, confidence_score,
            recommended_steps, reasoning,
            escalation_required, relevant_sops, similar_ticket_ids,
            short_circuited, short_circuit_reason,
            alarm_status, maintenance_active, remote_feasible, remote_confidence,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, dispatch_rows)

    conn.commit()
    conn.close()

    # Summary
    print(f"[4/4] Done.")
    print(f"\n  {'='*55}")
    print(f"  Tickets inserted  : {resolved_cnt + held_cnt}")
    print(f"    RESOLVED        : {resolved_cnt}")
    print(f"    PENDING REVIEW  : {held_cnt}")
    print(f"    Skipped (parse) : {skipped}")
    print(f"  Dispatch decisions: {len(dispatch_rows)}")
    print(f"  Database          : {DB_PATH}")
    print(f"  {'='*55}\n")
    print("  Dashboard will now reflect all processed tickets.")
    print("  Refresh the frontend to see updated stats.\n")


if __name__ == "__main__":
    main()
