# Accessibility Compliance Report — [FILL: Feature/Release Name]

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

## 1. Scope

Components and pages added or modified in this release:

| Component / Page | File Path | Change Type |
|---|---|---|
| [FILL: e.g., HotNodesWidget] | `frontend/src/components/HotNodesWidget.tsx` | New |
| [FILL: e.g., TicketLocationMapWidget] | `frontend/src/components/TicketLocationMapWidget.tsx` | New |
| [FILL: e.g., DashboardPage] | `frontend/src/pages/DashboardPage.tsx` | Modified |
| [FILL: add rows] | | |

---

## 2. Standard [PRE-FILLED]

Target: **WCAG 2.1 AA**

This is an internal NOC workstation tool. Minimum bar is AA compliance; AAA is aspirational where feasible without significant development overhead.

---

## 3. Keyboard Navigation

| Component | Tab-reachable | Enter/Space activates | Focus ring visible | Notes |
|---|---|---|---|---|
| [FILL: e.g., NodeRow leaderboard item] | [FILL: Yes / No] | [FILL: Yes / No / N/A] | [FILL: Yes / No] | [FILL: e.g., Non-interactive — display only; not tab-focusable by design] |
| [FILL: e.g., Leaflet CircleMarker] | [FILL: Yes / No] | [FILL: Yes / No] | [FILL: Yes / No] | [FILL: e.g., react-leaflet markers are keyboard accessible via arrow keys within map focus] |
| [FILL: e.g., Chat input field] | Yes | N/A (text input) | Yes | — |
| [FILL: add rows] | | | | |

---

## 4. Screen Reader

| Component | `aria-label` / `role` added | Landmark region | Notes |
|---|---|---|---|
| [FILL: e.g., HotNodesWidget container] | `aria-label="High-Volume Ticket Nodes"` | `<section>` | [FILL] |
| [FILL: e.g., Progress bar segments] | `aria-label="Pending: X tickets"` | — | [FILL: e.g., Each coloured bar segment has an aria-label describing its value] |
| [FILL: e.g., Map container] | `aria-label="Ticket location map of Singapore"` `role="application"` | — | [FILL: e.g., Leaflet map announces zoom level on focus] |
| [FILL: add rows] | | | |

---

## 5. Colour Contrast

Platform palette reference [PRE-FILLED]:

| Element | Foreground | Background | Ratio | WCAG AA |
|---|---|---|---|---|
| Body text on card | `#ffffff` | `#1e293b` (slate-800) | 14.7 : 1 | Pass |
| RED accent `#E60028` on slate-800 | `#E60028` | `#1e293b` | 4.8 : 1 | Pass (large text / UI components) |
| Subtext `text-slate-400` (`#94a3b8`) on slate-800 | `#94a3b8` | `#1e293b` | 5.9 : 1 | Pass |

Release-specific elements [FILL]:

| Element | Foreground | Background | Ratio | WCAG AA |
|---|---|---|---|---|
| [FILL: e.g., Network type badge — 5G emerald text] | [FILL: `#6ee7b7`] | [FILL: `#065f46`] | [FILL] | [FILL: Pass / Fail] |
| [FILL: add rows] | | | | |

---

## 6. Responsive Design

| Breakpoint | Tested | Minimum Viewport | Notes |
|---|---|---|---|
| 1920 × 1080 (NOC workstation) | [FILL: Yes / No] | — | Primary target |
| 1440 × 900 (laptop) | [FILL: Yes / No] | — | Secondary target |
| 768 px (tablet) | [FILL: Yes / No] | — | [FILL: e.g., Layout reflows to single column — acceptable for internal tool] |
| < 640 px | Not tested | 640 px minimum | Mobile not a use case for NOC platform |

---

## 7. Motion & Animation

| Component | Animation Used | `prefers-reduced-motion` respected | Notes |
|---|---|---|---|
| [FILL: e.g., Loading skeleton] | `animate-pulse` (Tailwind) | [FILL: Yes / No] | [FILL: e.g., Tailwind's animate-pulse honours `prefers-reduced-motion: reduce` by default in Tailwind v3] |
| [FILL: e.g., Chart bars] | Recharts default transition | [FILL: Yes / No] | [FILL: e.g., `isAnimationActive={!prefersReducedMotion}` added] |
| [FILL: "None" if no animation] | — | — | — |

---

## 8. Issues & Remediation

<!-- Delete this section if no accessibility issues were found. -->

| Issue ID | Component | Severity | Description | Fix Applied | Verified |
|---|---|---|---|---|---|
| A11Y-01 | [FILL] | [FILL: Critical / High / Medium / Low] | [FILL: e.g., Map container had no `aria-label`] | [FILL: e.g., Added `aria-label="Ticket location map of Singapore"` to MapContainer wrapper] | [FILL: Yes / No] |
| [FILL: add rows] | | | | | |
