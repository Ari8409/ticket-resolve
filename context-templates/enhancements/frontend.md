# Frontend Enhancement Request — [FILL: Feature Name]

## 1. Platform Context [PRE-FILLED]

- **Stack:** React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5 · react-leaflet
- **File conventions:**
  - New page → `frontend/src/pages/<Name>Page.tsx`
  - New widget/component → `frontend/src/components/<Name>Widget.tsx` or `<Name>Panel.tsx`
  - API type interfaces → `frontend/src/api/client.ts`
  - Navigation routes → `frontend/src/App.tsx`
  - Sidebar nav entries → `frontend/src/components/Navigation.tsx`
- **State & caching pattern:**
  ```typescript
  const { data, isLoading, error } = useQuery({
    queryKey: ['<key>'],
    queryFn: api.<method>,
    staleTime: 5 * 60_000,
  })
  ```
- **Design system:**
  - Backgrounds: `bg-slate-900` (page) · `bg-slate-800` (card) · `bg-slate-700` (row hover)
  - Borders: `border-slate-700`
  - Accent colours: RED `#E60028` · BLUE `#0078D4` · GREEN `#22c55e` · AMBER `#f59e0b`
  - Widget wrapper: `bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg`
  - Section header: `text-lg font-semibold text-white flex items-center gap-2`
  - Subtext / labels: `text-slate-400 text-sm`
- **Icon library:** `lucide-react` — import named icons e.g. `import { TrendingUp } from 'lucide-react'`
- **Loading skeleton:** `animate-pulse bg-slate-700 rounded` divs matching the shape of the loaded content
- **Error state:** `<div className="text-red-400 text-sm">...</div>` within the widget boundary

---

## 2. Feature Description [FILL]

<!-- Describe what the user sees and does.
     Cover all of:
       - Overall layout (full-width card? split columns? table? chart?)
       - Data displayed per row/cell/segment
       - User interactions: click, hover tooltip, filter dropdown, search input, pagination
       - Empty state message
       - Loading state appearance
       - Error state appearance
-->

---

## 3. Data Source [FILL]

<!-- Specify where data comes from:
     Option A — Existing endpoint (reuse React Query cache):
       - Endpoint: GET /api/v1/<path>
       - queryKey: ['<existing-key>']          ← must match the key used elsewhere to share cache
       - Response type: <ExistingInterface> (already in client.ts)

     Option B — New endpoint required:
       - See integration.md template for backend spec
       - New queryKey: ['<new-key>']
       - New interface to add to client.ts: <NewInterface>

     If multiple endpoints, list all with their queryKeys.
-->

---

## 4. Component Breakdown [FILL]

<!-- List each component to create or modify, with props and shadcn/ui primitives used.
     Format:
       - <ComponentName props="..."> — purpose, data shape it consumes
         Uses: Badge, Button, Tooltip, etc. from shadcn/ui

     Example:
       - <FaultTypeChart data={stats.by_fault_type}> — Recharts BarChart
         data shape: Record<string, number>  (keys = fault type, value = count)

       - <StatusBadge status="pending_review"> — colour-coded pill
         Uses: shadcn/ui Badge with variant mapped to status string

       - <NodeRow node={node} rank={i}> — single leaderboard row with stacked bar
         Rendered inside a .map() in <HotNodesWidget>
-->

---

## 5. RICEF Classification [FILL]

- **Type:** F (Form / UI Feature)
- **RICEF ID:** [FILL: R-xx]
- **Release:** [FILL: e.g., Release 15 — Feature Name]
- **Depends on:** [FILL: list any other RICEF IDs this feature builds on, or "none"]

---

## 6. Acceptance Criteria [FILL]

<!-- Each criterion must be independently testable. Use checkbox format. -->

- [ ] [FILL: e.g., Widget renders within 200 ms of page load using React Query cache]
- [ ] [FILL: e.g., Empty state message shown when API returns an empty array]
- [ ] [FILL: e.g., Loading skeleton matches layout of loaded content]
- [ ] [FILL: e.g., Clicking a row navigates to /tickets?filter=<id>]
- [ ] [FILL: add more as needed]

---

## 7. Integration Points [FILL]

<!-- List every existing file that needs updating to wire in this feature. -->

- `frontend/src/pages/DashboardPage.tsx` — [FILL: e.g., import + render `<NewWidget />` after `<ExistingWidget />`]
- `frontend/src/api/client.ts` — [FILL: add interface `<NewInterface>` and `api.<newMethod>` function]
- `frontend/src/App.tsx` — [FILL: add route `<Route path="/new-page" element={<NewPage />} />` if new page]
- `frontend/src/components/Navigation.tsx` — [FILL: add nav link if new top-level page]
- `frontend/src/pages/SDLCDashboard.tsx` — mark RICEF ID [FILL: R-xx] status as `delivered`

---

## 8. Testing Requirements [FILL]

<!-- Manual smoke-test steps. No automated test framework is configured on this project. -->

1. Start dev server: `cd frontend && npm run dev -- --host 0.0.0.0`
2. Navigate to [FILL: route, e.g., `/` or `/tickets`]
3. [FILL: specific check — e.g., "Confirm 'High-Volume Ticket Nodes' heading is visible"]
4. [FILL: interaction check — e.g., "Hover over a bar segment — tooltip shows count"]
5. [FILL: edge case — e.g., "Disconnect network, reload — error state renders without crash"]
