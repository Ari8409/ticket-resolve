# System Integration Test Report — [FILL: Feature/Release Name]

## Document Metadata

| Field | Value |
|---|---|
| Release | [FILL: e.g., Release 15 — Feature Name] |
| RICEF ID | [FILL: R-xx] |
| RICEF Type | [FILL: R / I / C / E / F] |
| Author | NOC Platform Team |
| Date | [FILL: YYYY-MM-DD] |
| Version | [FILL: e.g., 1.0] |
| Status | [FILL: Draft / Review / Approved] |

## Platform Reference [PRE-FILLED]

- Backend: FastAPI 0.115 · Python 3.12 · SQLite (`data/tickets.db`) · LangChain 0.3 · ChromaDB
- Frontend: React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5
- Repository path: `ticket-resolve/`

---

## 1. Integration Scenarios Tested

<!-- Number each end-to-end flow that was executed. -->

1. [FILL: e.g., Dashboard page load → React Query fetches `/network/graph` → HotNodesWidget renders top-10 node leaderboard with stacked bars]
2. [FILL: e.g., Location map cold load → backend queries `telco_tickets` → geocaches missing addresses via Nominatim → returns `LocationSummaryResponse` → map renders CircleMarker per location]
3. [FILL: e.g., Location map warm load (all addresses cached) → endpoint returns instantly → spinner not shown]
4. [FILL: e.g., User clicks CircleMarker → Leaflet Popup shows address, ticket counts, status breakdown]
5. [FILL: add more as needed]

---

## 2. Test Execution Results

| Scenario | Status | Evidence |
|---|---|---|
| 1. [FILL: short name] | [FILL: Pass / Fail] | [FILL: e.g., Screenshot `screenshots/sit_hotnode_widget.png` · DevTools shows single `/network/graph` call] |
| 2. [FILL: short name] | [FILL] | [FILL: e.g., Backend log excerpt: `INFO: Geocoding 4 addresses via Nominatim`] |
| 3. [FILL: short name] | [FILL] | [FILL] |
| 4. [FILL: short name] | [FILL] | [FILL] |
| [FILL: add rows] | | |

---

## 3. Defects Found

<!-- Delete this section if no defects were found. -->

| Defect ID | Severity | Description | Status |
|---|---|---|---|
| DEF-01 | [FILL: Critical / High / Medium / Low] | [FILL: description] | [FILL: Open / Fixed / Deferred] |
| [FILL: add rows] | | | |

---

## 4. Regression Check

<!-- Confirm that features from previous releases still work after this release's changes. -->

| Feature | Release | Re-tested? | Result |
|---|---|---|---|
| KPI Stats Dashboard | R-1 | [FILL: Yes / No] | [FILL: Pass / Not tested] |
| Triage Queue | R-4 | [FILL] | [FILL] |
| Chat Assistant | R-6 | [FILL] | [FILL] |
| Dispatch Dashboard | R-7 | [FILL] | [FILL] |
| SDLC Dashboard | R-8 | [FILL] | [FILL] |
| Network Topology Widget | R-11 | [FILL] | [FILL] |
| [FILL: add previous releases affected] | | | |

---

## 5. Environment Details

| Item | Value |
|---|---|
| OS | Windows 11 Enterprise |
| Browser | Chrome [FILL: version] |
| Node version | [FILL: e.g., 20.x] |
| Python version | [FILL: e.g., 3.12.x] |
| DB row count | [FILL: e.g., 1 592 tickets, 156 dispatch records] |
| Backend URL | `http://localhost:8000` |
| Frontend URL | `http://localhost:5173` |
| External services reachable | [FILL: Yes / No — Nominatim, etc.] |

---

## 6. Sign-off

| Field | Value |
|---|---|
| Tester | [FILL: name] |
| Test date | [FILL: YYYY-MM-DD] |
| Defects outstanding | [FILL: count — 0 = clean] |
| Recommendation | [FILL: **Go** — ready to merge / **No-Go** — defects must be resolved first] |
