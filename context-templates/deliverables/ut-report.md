# Unit Test Report — [FILL: Feature/Release Name]

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

## 1. Test Execution Summary

| Test ID | Component | Status | Notes |
|---|---|---|---|
| UT-01 | [FILL: e.g., GET /api/v1/location-summary — happy path] | [FILL: Pass / Fail / Skip] | [FILL: e.g., Returned 12 locations with correct counts] |
| UT-02 | [FILL] | [FILL] | [FILL] |
| UT-03 | [FILL] | [FILL] | [FILL] |
| [FILL: add rows for all TDD test IDs] | | | |

---

## 2. Pass Rate

**[FILL: X] / [FILL: Y] tests passed ([FILL: Z]%)**

| Category | Total | Passed | Failed | Skipped |
|---|---|---|---|---|
| Backend (API) | [FILL] | [FILL] | [FILL] | [FILL] |
| Frontend (component) | [FILL] | [FILL] | [FILL] | [FILL] |
| **Total** | [FILL] | [FILL] | [FILL] | [FILL] |

---

## 3. Failures & Root Causes

<!-- Complete one block per failing test. Delete section if all tests passed. -->

### [FILL: Test ID] — [FILL: one-line description]

- **Observed:** [FILL: what actually happened]
- **Expected:** [FILL: what should have happened]
- **Root cause:** [FILL: e.g., Pydantic model missing `Optional` on `display_name` field]
- **Fix applied:** [FILL: e.g., Changed `display_name: str` to `display_name: str | None` in `locations.py:34`]
- **Verified:** [FILL: Yes / No — re-run result after fix]

---

## 4. Coverage Notes

| Code Area | Exercised | Known Gaps |
|---|---|---|
| [FILL: e.g., `locations.py` — geocache miss path] | Yes | [FILL: e.g., `failed=1` branch not explicitly tested] |
| [FILL: e.g., HotNodesWidget empty state] | Yes | — |
| [FILL: e.g., NetworkType badge colours] | Partial | [FILL: e.g., Only 4G and 5G tested; 3G badge not verified] |
| [FILL: add rows] | | |

---

## 5. Sign-off

| Field | Value |
|---|---|
| Tester | [FILL: name] |
| Test date | [FILL: YYYY-MM-DD] |
| Environment | Windows 11 · Chrome [FILL: version] · Python 3.12 · Node 20 |
| DB row count at test time | [FILL: e.g., 1 592 tickets] |
| Recommendation | [FILL: Ready for SIT / Blocked — see failures above] |
