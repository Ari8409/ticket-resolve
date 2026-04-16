# Low-Level Design — SLA Tracking Table & Dashboard Widget

## Document Metadata

| Field      | Value                                           |
|------------|-------------------------------------------------|
| Release    | Release 15 — SLA Tracking Table & Dashboard Widget |
| RICEF ID   | R-15                                            |
| RICEF Type | C                                               |
| Author     | NOC Platform Team                               |
| Date       | 2026-04-14                                      |
| Version    | 1.0                                             |
| Status     | Approved                                        |

## Platform Reference [PRE-FILLED]

- Backend: FastAPI 0.115 · Python 3.12 · SQLite (`data/tickets.db`) · LangChain 0.3 · ChromaDB
- Frontend: React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5
- Repository path: `ticket-resolve/`

---

## 1. Module Breakdown

### Backend

**`app/api/v1/sla.py`** *(new — 200 lines)*

```python
# Constants
DEFAULT_TARGETS: list[tuple[str, int, str]]   # 8 fault-type seed rows

# Pydantic models
class SLAFaultSummary(BaseModel)              # per-fault compliance breakdown
class SLASummaryResponse(BaseModel)           # endpoint response for /summary
class SLATarget(BaseModel)                    # single target row
class SLATargetsResponse(BaseModel)           # endpoint response for /targets
class SLATargetUpdateRequest(BaseModel)       # PUT request body

# DB helper
async def ensure_sla_table() -> None
    # CREATE TABLE IF NOT EXISTS sla_targets + INSERT OR IGNORE seed rows

# Startup hook
async def _startup() -> None                  # calls ensure_sla_table()

# Endpoints
async def get_sla_summary() -> SLASummaryResponse
    # SELECT telco_tickets LEFT JOIN sla_targets GROUP BY fault_type
    # JULIANDAY arithmetic for breach detection

async def get_sla_targets() -> SLATargetsResponse
    # SELECT * FROM sla_targets ORDER BY fault_type

async def update_sla_target(fault_type, payload) -> SLATarget
    # 404 if fault_type not found
    # UPDATE sla_targets SET target_hours = ?, updated_at = ? WHERE fault_type = ?
```

**`app/api/v1/router.py`** *(modified — 2 lines)*

```python
from app.api.v1 import ..., sla, ...
v1_router.include_router(sla.router)    # inserted before stats.router
```

### Frontend

**`frontend/src/components/SLAWidget.tsx`** *(new — 195 lines)*

```typescript
function complianceColour(rate: number): string   // green/amber/red threshold
function SLATooltip({ active, payload })          // custom Recharts tooltip

export function SLAWidget(): JSX.Element          // main widget
  // useQuery(['sla-summary'], api.getSLASummary, staleTime=5*60_000)
  // States: isLoading → skeleton | error → error msg | total=0 → empty | data → render
  // KPI row: compliance_rate %, breached count, avg_resolution_hours
  // Recharts BarChart (horizontal) — compliance_rate per fault_type
  // Cell fill = complianceColour(row.compliance_rate)
  // ReferenceLine at x=90 (target threshold)
```

**`frontend/src/api/client.ts`** *(modified — added interfaces + 3 methods)*

```typescript
export interface SLAFaultSummary { ... }
export interface SLASummaryResponse { ... }
export interface SLATarget { ... }
export interface SLATargetsResponse { ... }

api.getSLASummary()       // GET /sla/summary
api.getSLATargets()       // GET /sla/targets
api.updateSLATarget()     // PUT /sla/targets/{fault_type}
```

**`frontend/src/pages/DashboardPage.tsx`** *(modified — 2 lines)*

```typescript
import { SLAWidget } from '../components/SLAWidget'   // line 25
<SLAWidget />   // rendered after <TicketLocationMapWidget />, before Recent Tickets table
```

---

## 2. Database Schema DDL

```sql
-- sla_targets — created lazily on first /sla/* endpoint call
CREATE TABLE IF NOT EXISTS sla_targets (
    fault_type    TEXT    PRIMARY KEY,
    target_hours  INTEGER NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

-- Seed rows (INSERT OR IGNORE — safe to re-run)
INSERT OR IGNORE INTO sla_targets (fault_type, target_hours, description, created_at, updated_at)
VALUES
    ('node_down',           4,  'Complete node outage',          '<now>', '<now>'),
    ('signal_loss',         8,  'Partial signal degradation',    '<now>', '<now>'),
    ('latency',             6,  'Network latency spike',         '<now>', '<now>'),
    ('packet_loss',         6,  'Packet loss event',             '<now>', '<now>'),
    ('congestion',          8,  'Network congestion',            '<now>', '<now>'),
    ('hardware_failure',    12, 'Physical hardware fault',       '<now>', '<now>'),
    ('configuration_error', 6,  'Config or firmware issue',      '<now>', '<now>'),
    ('unknown',             24, 'Unclassified fault',            '<now>', '<now>');
```

---

## 3. Pydantic Models

```python
class SLAFaultSummary(BaseModel):
    fault_type: str
    target_hours: int
    description: str
    total_resolved: int
    within_sla: int
    breached: int
    compliance_rate: float        # rounded to 1 decimal
    avg_resolution_hours: float   # rounded to 2 decimals

class SLASummaryResponse(BaseModel):
    total_resolved: int
    within_sla: int
    breached: int
    compliance_rate: float
    avg_resolution_hours: float
    by_fault_type: list[SLAFaultSummary]

class SLATarget(BaseModel):
    fault_type: str
    target_hours: int
    description: str
    updated_at: str

class SLATargetsResponse(BaseModel):
    targets: list[SLATarget]

class SLATargetUpdateRequest(BaseModel):
    target_hours: int
    description: Optional[str] = None
```

---

## 4. React Component Tree

```
DashboardPage
└── SLAWidget                     ← self-contained, no props
    ├── Header bar                 (ShieldCheck icon + title)
    ├── KPI row (3 × bg-slate-900 cards)
    │   ├── compliance_rate %      (colour = complianceColour())
    │   ├── breached count         (text-red-400)
    │   └── avg_resolution_hours   (text-blue-400)
    ├── Legend row                 (green / amber / red dots)
    └── ResponsiveContainer
        └── BarChart (layout="vertical")
            ├── XAxis (0–100%, tickFormatter)
            ├── YAxis (fault_type labels)
            ├── Tooltip → SLATooltip
            ├── ReferenceLine x=90 (dashed green)
            └── Bar dataKey="compliance_rate"
                └── Cell × N     (fill = complianceColour per row)
```

---

## 5. React Query Keys & Cache Strategy

| queryKey | staleTime | refetchInterval | Source fn |
|---|---|---|---|
| `['sla-summary']` | `5 * 60_000` ms | none | `api.getSLASummary` |

---

## 6. State Transitions

```
SLAWidget
  isLoading=true   → render animated skeleton (3 KPI skeletons + bar placeholder)
  isError=true     → render "SLA data unavailable — backend may be offline."
  total_resolved=0 → render "No resolved tickets found to compute SLA metrics."
  data present     → render KPI row + horizontal bar chart
```

---

## 7. Error Handling Matrix

| Scenario | HTTP Status | UI Message | Recovery |
|---|---|---|---|
| Backend offline | Network error | "SLA data unavailable — backend may be offline." | React Query retries ×3 |
| No resolved tickets in DB | 200 (empty `by_fault_type`) | "No resolved tickets found to compute SLA metrics." | No action needed |
| Unknown fault_type on PUT | 404 | FastAPI JSON `{"detail": "SLA target not found ..."}` | Fix fault_type value |
| Invalid `target_hours` (e.g., string) | 422 | FastAPI auto-generated validation error | Fix request body |
