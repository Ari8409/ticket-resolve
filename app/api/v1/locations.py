"""
Location summary endpoint — geographic distribution of network tickets.

GET /telco-tickets/location-summary
  - Aggregates tickets grouped by the site code embedded in affected_node
    (e.g. LTE_ENB_780321 → site code "780321")
  - Resolves each 6-digit site code to Singapore coordinates via a static
    district lookup table (first 2 digits = district → district centroid +
    deterministic jitter so markers spread within the district)
  - No external API calls; all resolution is offline and instant

RAI: EU AI Act Art.13 — transparency on geographic fault distribution.
     GSMA-SAFE-01 — no PII; only internal site codes used for mapping.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "tickets.db"

# ── Site-code extraction ───────────────────────────────────────────────────────

_SITE_CODE_RE = re.compile(r"(\d{6})$")          # exactly 6 digits at end of node ID


def _extract_site_key(node_id: str) -> str | None:
    """Return the 6-digit site code suffix from a node ID, or None."""
    m = _SITE_CODE_RE.search(node_id or "")
    return m.group(1) if m else None


# ── Singapore district → (lat, lng, name) lookup ─────────────────────────────
#
#  Key = first 2 digits of a 6-digit Singapore site/postal code.
#  Values are the district centroid coordinates + a readable name.
#  Covers all 82 Singapore postal districts; codes > 82 fall back to Central.

_SG_DISTRICTS: dict[str, tuple[float, float, str]] = {
    "01": (1.2801, 103.8485, "Raffles Place / Cecil"),
    "02": (1.2792, 103.8455, "Tanjong Pagar"),
    "03": (1.2700, 103.8330, "Queenstown"),
    "04": (1.2699, 103.8290, "Telok Blangah / Harbourfront"),
    "05": (1.2942, 103.7978, "Pasir Panjang / Clementi"),
    "06": (1.2936, 103.8520, "High Street / Beach Road"),
    "07": (1.2966, 103.8520, "Middle Road / Golden Mile"),
    "08": (1.3010, 103.8570, "Little India"),
    "09": (1.3059, 103.8329, "Orchard / River Valley"),
    "10": (1.3150, 103.8199, "Ardmore / Bukit Timah"),
    "11": (1.3238, 103.8275, "Novena / Thomson"),
    "12": (1.3290, 103.8480, "Toa Payoh"),
    "13": (1.3285, 103.8576, "Macpherson / Braddell"),
    "14": (1.3187, 103.8978, "Geylang / Eunos"),
    "15": (1.3035, 103.9007, "Katong / Joo Chiat"),
    "16": (1.3190, 103.9268, "Bedok / Upper East Coast"),
    "17": (1.3673, 103.9915, "Loyang / Changi"),
    "18": (1.3520, 103.9455, "Tampines"),
    "19": (1.3800, 103.8940, "Serangoon Gardens / Hougang"),
    "20": (1.3690, 103.8730, "Bishan / Ang Mo Kio"),
    "21": (1.3420, 103.7720, "Upper Bukit Timah"),
    "22": (1.3268, 103.7462, "Jurong"),
    "23": (1.3775, 103.7650, "Bukit Panjang / Dairy Farm"),
    "24": (1.4350, 103.7810, "Lim Chu Kang / Tengah"),
    "25": (1.4450, 103.8180, "Kranji / Woodgrove"),
    "26": (1.4300, 103.8250, "Upper Thomson / Springleaf"),
    "27": (1.4510, 103.8280, "Yishun / Sembawang"),
    "28": (1.3720, 103.8400, "Seletar"),
    "29": (1.3810, 103.8680, "Serangoon North"),
    "30": (1.3870, 103.8750, "Hougang"),
    "31": (1.3900, 103.8770, "Hougang East"),
    "32": (1.3980, 103.9050, "Punggol"),
    "33": (1.4360, 103.7862, "Woodlands"),
    "34": (1.4500, 103.8180, "Admiralty / Sembawang"),
    "35": (1.3849, 103.7453, "Choa Chu Kang"),
    "36": (1.3860, 103.7460, "Choa Chu Kang North"),
    "37": (1.3690, 103.8490, "Ang Mo Kio"),
    "38": (1.3520, 103.8490, "Bishan"),
    "39": (1.3560, 103.8730, "Toa Payoh East"),
    "40": (1.3500, 103.8700, "Macpherson East"),
    "41": (1.3428, 103.8393, "Thomson"),
    "42": (1.3290, 103.8700, "Aljunied"),
    "43": (1.3200, 103.8810, "Macpherson"),
    "44": (1.2951, 103.7983, "Queenstown West"),
    "45": (1.3004, 103.7950, "Queenstown South"),
    "46": (1.3070, 103.7920, "Buona Vista"),
    "47": (1.3207, 103.8079, "Holland"),
    "48": (1.3300, 103.8050, "Holland Village"),
    "49": (1.3670, 103.7710, "Bukit Panjang"),
    "50": (1.3680, 103.7720, "Bukit Batok"),
    "51": (1.3930, 103.8935, "Seng Kang"),
    "52": (1.3940, 103.8940, "Seng Kang East"),
    "53": (1.3780, 103.8700, "Serangoon Ave"),
    "54": (1.3860, 103.8720, "Serangoon North Ave"),
    "55": (1.3800, 103.8850, "Hougang Central"),
    "56": (1.3850, 103.8900, "Hougang Upper"),
    "57": (1.3520, 103.9400, "Tampines East"),
    "58": (1.3480, 103.9300, "Tampines West"),
    "59": (1.3560, 103.9600, "Loyang"),
    "60": (1.3160, 103.7640, "Jurong East"),
    "61": (1.3040, 103.7500, "Jurong West"),
    "62": (1.2952, 103.7330, "Jurong Industrial"),
    "63": (1.2980, 103.7290, "Jurong Port"),
    "64": (1.3000, 103.6960, "Tuas South"),
    "65": (1.3150, 103.6930, "Tuas"),
    "66": (1.3320, 103.6980, "Tuas North"),
    "67": (1.3500, 103.7020, "Tuas North Upper"),
    "68": (1.3650, 103.7100, "Lim Chu Kang"),
    "69": (1.3100, 103.7190, "Jurong Island"),
    "70": (1.3350, 103.7470, "Jurong East Central"),
    "71": (1.3400, 103.7450, "Jurong East"),
    "72": (1.3480, 103.7300, "Boon Lay"),
    "73": (1.3330, 103.7410, "Jurong West Ave"),
    "74": (1.3200, 103.7090, "Tuas Ave"),
    "75": (1.3140, 103.6900, "Tuas Link"),
    "76": (1.3050, 103.6880, "Tuas West"),
    "77": (1.3030, 103.6850, "Tuas South"),
    "78": (1.3380, 103.7010, "Jurong West Upper"),
    "79": (1.3400, 103.6950, "Tuas Bay"),
    "80": (1.3450, 103.7050, "Tuas North"),
    "81": (1.4000, 103.9900, "Changi Village"),
    "82": (1.3920, 103.9960, "Changi Business Park"),
}

_SG_FALLBACK = (1.3521, 103.8198, "Singapore")  # island centroid for unknown codes


def _site_code_to_coords(code: str) -> tuple[float, float, str]:
    """
    Map a 6-digit site code to Singapore (lat, lng, area_name).

    Uses the first 2 digits as the district key, then applies a small
    deterministic jitter (±0.018°) based on a hash of the full code so
    that nodes in the same district don't stack.
    """
    district = code[:2] if len(code) >= 2 else "01"
    base_lat, base_lng, area = _SG_DISTRICTS.get(district, _SG_FALLBACK)

    # Deterministic jitter: hash the full site code → spread ±0.018 degrees
    h = int(hashlib.sha256(code.encode()).hexdigest(), 16)
    lat_jitter = ((h % 3600) - 1800) / 100_000   # ±0.018°  (~2 km)
    lng_jitter = ((h // 3600 % 3600) - 1800) / 100_000

    return base_lat + lat_jitter, base_lng + lng_jitter, area


# ── Response models ───────────────────────────────────────────────────────────

class LocationSummaryItem(BaseModel):
    address: str
    lat: float
    lng: float
    display_name: str
    ticket_count: int
    pending_count: int
    open_count: int
    resolved_count: int


class LocationSummaryResponse(BaseModel):
    locations: list[LocationSummaryItem]
    geocoded: int
    pending_geocode: int
    total_tickets_with_location: int


# ── Main endpoint ──────────────────────────────────────────────────────────────

@router.get("/telco-tickets/location-summary", response_model=LocationSummaryResponse)
def get_location_summary() -> LocationSummaryResponse:
    """
    Return aggregated ticket counts grouped by node site location.

    Each ticket's affected_node (e.g. LTE_ENB_780321) contains a 6-digit
    site code. The first 2 digits identify one of 82 Singapore postal
    districts; deterministic jitter spreads markers within each district.
    """
    db_path = str(_DB_PATH)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        raw_rows: list[dict[str, Any]] = [
            dict(r) for r in conn.execute(
                "SELECT location_details, affected_node, status FROM telco_tickets"
            ).fetchall()
        ]
    finally:
        conn.close()

    # Bucket tickets by site key
    from collections import defaultdict
    site_buckets: dict[str, dict[str, int]] = defaultdict(lambda: {
        "ticket_count": 0, "pending_count": 0, "open_count": 0, "resolved_count": 0,
    })

    total_with_location = 0
    for row in raw_rows:
        loc = (row.get("location_details") or "").strip()
        key = loc if loc else _extract_site_key(row.get("affected_node") or "")
        if not key:
            continue
        total_with_location += 1
        b = site_buckets[key]
        b["ticket_count"] += 1
        status = row.get("status", "")
        if status == "pending_review":
            b["pending_count"] += 1
        elif status in ("open", "in_progress", "assigned", "escalated"):
            b["open_count"] += 1
        elif status in ("resolved", "closed", "cleared"):
            b["resolved_count"] += 1

    if not site_buckets:
        return LocationSummaryResponse(
            locations=[], geocoded=0, pending_geocode=0, total_tickets_with_location=0
        )

    locations: list[LocationSummaryItem] = []
    for code, counts in sorted(site_buckets.items(), key=lambda x: -x[1]["ticket_count"]):
        lat, lng, area = _site_code_to_coords(code)
        locations.append(LocationSummaryItem(
            address=code,
            lat=round(lat, 6),
            lng=round(lng, 6),
            display_name=f"Site {code} — {area}",
            **counts,  # type: ignore[arg-type]
        ))

    return LocationSummaryResponse(
        locations=locations,
        geocoded=len(locations),
        pending_geocode=0,
        total_tickets_with_location=total_with_location,
    )
