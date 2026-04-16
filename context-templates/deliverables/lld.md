# Low-Level Design — [FILL: Feature/Release Name]

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

## 1. Module Breakdown

<!-- File-by-file listing. For each file: list every function/class with its signature. -->

### Backend

**`app/api/v1/[FILL: feature].py`** *(new)*

```python
# Pydantic models
class [FILL]Item(BaseModel): ...
class [FILL]Response(BaseModel): ...

# Table initialisation
async def ensure_[FILL]_table() -> None:
    """CREATE TABLE IF NOT EXISTS [FILL: table_name] ..."""

# Router
router = APIRouter()

@router.get("/[FILL: path]", response_model=[FILL]Response)
async def get_[FILL](...) -> [FILL]Response:
    """[FILL: one-line description]"""
```

**`app/api/v1/router.py`** *(modified — 2 lines)*

```python
from app.api.v1 import [FILL: feature]   # add to imports
v1_router.include_router([FILL: feature].router)  # add after stats.router line
```

### Frontend

**`frontend/src/components/[FILL]Widget.tsx`** *(new)*

```typescript
// Props
interface [FILL]WidgetProps { /* [FILL: if any, else empty] */ }

// Main component
export function [FILL]Widget(): JSX.Element

// Internal helpers (if any)
function [FILL]Colour(item: [FILL]Item): string
function [FILL]Radius(count: number, max: number): number
```

**`frontend/src/api/client.ts`** *(modified)*

```typescript
// Interfaces added:
export interface [FILL]Item { ... }
export interface [FILL]Response { ... }

// Method added to `api` object:
get[FILL]: async (): Promise<[FILL]Response> => { ... }
```

---

## 2. Database Schema DDL

```sql
-- [FILL: table name] — created lazily on first endpoint call
CREATE TABLE IF NOT EXISTS [FILL: table_name] (
    [FILL: column]  [FILL: type]  [FILL: constraints],
    -- e.g.:
    -- address       TEXT PRIMARY KEY,
    -- lat           REAL,
    -- lng           REAL,
    -- display_name  TEXT,
    -- failed        INTEGER NOT NULL DEFAULT 0,
    -- geocoded_at   TEXT
);

-- Optional index:
-- CREATE INDEX IF NOT EXISTS idx_[FILL: table_name]_[FILL: column]
--   ON [FILL: table_name]([FILL: column]);
```

---

## 3. Pydantic Models

```python
from pydantic import BaseModel
from typing import Optional

class [FILL]Item(BaseModel):
    [FILL: field]: [FILL: type]         # e.g., address: str
    [FILL: field]: [FILL: type]         # e.g., lat: float
    # ... add all fields

class [FILL]Response(BaseModel):
    [FILL: field]: list[[FILL]Item]     # e.g., locations: list[LocationSummaryItem]
    [FILL: field]: int                  # e.g., geocoded: int
    [FILL: field]: int                  # e.g., total_tickets_with_location: int
```

---

## 4. React Component Tree

```
[FILL: PageName]Page
└── [FILL: WidgetName]Widget
    ├── Header (title + subtitle + legend)
    ├── [FILL: sub-component, e.g., NodeRow × 10]
    │   ├── RankLabel
    │   ├── NodeIdLabel + NetworkTypeBadge
    │   └── StackedProgressBar (pending/open/resolved segments)
    └── EmptyState | LoadingSkeleton | ErrorMessage
```

*Props flow:*

| Component | Props received | Source |
|---|---|---|
| [FILL: WidgetName]Widget | none (self-contained) | React Query cache |
| [FILL: sub-component] | `[FILL: prop]: [FILL: type]` | parent `.map()` |

---

## 5. React Query Keys & Cache Strategy

| queryKey | staleTime | refetchInterval | Source fn |
|---|---|---|---|
| `['[FILL: key]']` | `5 * 60_000` ms | none | `api.get[FILL]` |
| [FILL: shared key if reusing existing] | same as existing | — | shared cache hit — 0 extra HTTP calls |

---

## 6. State Transitions

```
[FILL: ComponentName]
  isLoading=true  → render LoadingSkeleton (N × animate-pulse rows)
  isError=true    → render ErrorMessage ("Data unavailable")
  data.length==0  → render EmptyState ("No data found")
  data.length > 0 → render full component
```

---

## 7. Error Handling Matrix

| Scenario | HTTP Status | UI Message | Recovery |
|---|---|---|---|
| Backend down | Network error | "[FILL: e.g., Location data unavailable]" | React Query retries ×3 with backoff |
| Empty DB table | 200 (empty list) | "[FILL: e.g., No data found in tickets]" | No action needed |
| External service timeout | 200 (partial) | [FILL: e.g., Amber banner "X addresses pending geocode"] | Retry next dashboard load |
| Pydantic validation error | 422 | FastAPI default error body | Fix request payload |
| [FILL: add rows] | | | |
