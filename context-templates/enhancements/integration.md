# Integration / API Enhancement Request — [FILL: Feature Name]

## 1. Platform Context [PRE-FILLED]

- **Framework:** FastAPI 0.115, Python 3.12, Pydantic v2
- **Router file pattern:** `app/api/v1/<feature>.py` → registered in `app/api/v1/router.py`
- **Existing routers** (already registered):
  `stats` · `network` · `locations` · `dispatch` · `sop` · `triage` · `chat`
- **HTTP client:** `httpx.AsyncClient` — already in `pyproject.toml` (`httpx>=0.27`)
- **Async DB:** `aiosqlite` — already in `pyproject.toml`
- **Response models:** Pydantic v2 `BaseModel` — define in the same file as the router
- **Path ordering rule:** FastAPI routes are matched in registration order. Declare specific literal paths (e.g., `/location-summary`) **before** any `/{ticket_id}` path-param routes in the same router.
- **CORS:** configured globally in `app/main.py` — no per-router CORS needed
- **Dependency injection:** `app/dependencies.py` — use existing `get_db()` if available, or open `aiosqlite` directly in the endpoint
- **AI agent entry points:**
  - Triage: `app/agents/triage_agent.py`
  - Chat: `app/agents/chat_agent.py`
  - Chroma collection: `sop_documents`
- **Router registration snippet:**
  ```python
  # app/api/v1/router.py — add after existing includes:
  from app.api.v1 import <feature>
  v1_router.include_router(<feature>.router)
  ```

---

## 2. Endpoint Specification [FILL]

<!-- Define every new endpoint. Repeat the block below for each one. -->

### Endpoint 1

- **Method + Path:** `[FILL: GET/POST/PUT/DELETE] /api/v1/[FILL: resource/action]`
- **Query parameters:**
  | Param | Type | Required | Default | Description |
  |---|---|---|---|---|
  | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
- **Request body (POST/PUT only):**
  ```python
  class [FILL]Request(BaseModel):
      [FILL: field]: [FILL: type]
  ```
- **Response model:**
  ```python
  class [FILL]Response(BaseModel):
      [FILL: field]: [FILL: type]   # example: locations: list[LocationItem]
  ```
- **Error cases:**
  | HTTP Status | Condition | Message |
  |---|---|---|
  | 404 | [FILL] | [FILL] |
  | 422 | Invalid input | FastAPI auto-generated |
  | 500 | [FILL] | [FILL] |

---

## 3. External Service Integration [FILL — if applicable]

<!-- Complete this section only if the endpoint calls an external API (Nominatim, Slack, SMTP, etc.). -->

- **Service:** [FILL: service name and base URL]
- **Auth:** [FILL: API key header / OAuth / none (public)]
- **Rate limit:** [FILL: e.g., 1 req/s] → use `await asyncio.sleep([FILL: seconds])` between successive calls
- **Caching strategy:**
  - Cache table: [FILL: table name] (see `database.md` template for schema)
  - Cache hit: skip external call, return stored value
  - Cache miss: call external service, store result (or mark `failed=1` on empty/error response)
- **Timeout:** `httpx.AsyncClient(timeout=[FILL: seconds])`
- **Fallback on failure:** [FILL: e.g., return partial results with `pending_geocode` count; do not 500]

---

## 4. LangChain / Agent Integration [FILL — if applicable]

<!-- Complete this section only if the endpoint invokes an AI agent. -->

- **Agent file:** `app/agents/[FILL: agent_name].py`
- **Invocation pattern:**
  ```python
  from app.agents.[FILL] import [FILL]Agent
  result = await agent.run(input=ticket_dict)
  ```
- **Input shape:** [FILL: dict keys the agent expects]
- **Output shape:** [FILL: Pydantic model or dict the agent returns]
- **Chroma collection used:** [FILL: `sop_documents` or new collection name]
- **Fallback if agent unavailable:** [FILL: e.g., return ticket with `confidence_score=0`, `reasons=[]`]

---

## 5. RICEF Classification [FILL]

- **Type:** [FILL: I (Interface/API) or E (Extension/Agent)]
- **RICEF ID:** [FILL: R-xx]
- **Release:** [FILL: e.g., Release 15 — Feature Name]
- **Depends on:** [FILL: other RICEF IDs, or "none"]

---

## 6. Frontend Contract [FILL]

<!-- Specify the TypeScript additions required in `frontend/src/api/client.ts`. -->

```typescript
// Interfaces to add:
export interface [FILL: Name]Item {
  [FILL: field]: [FILL: type]
}

export interface [FILL: Name]Response {
  [FILL: field]: [FILL: type]
}

// Method to add inside the `api` object:
get[FILL: Name]: async (): Promise<[FILL: Name]Response> => {
  const { data } = await apiClient.get<[FILL: Name]Response>('/[FILL: path]')
  return data
},
```

<!-- If adding a field to an existing interface (e.g., TelcoTicket), specify:
     Interface: TelcoTicket
     Add field: location_id: string | null
-->

---

## 7. Acceptance Criteria [FILL]

- [ ] `GET /api/v1/[FILL: path]` returns HTTP 200 with correct Pydantic-validated shape
- [ ] Empty input / null DB rows handled gracefully — returns `200` with empty list, not `500`
- [ ] [FILL: e.g., External service timeout (> 5 s) handled — endpoint responds within 10 s with partial data]
- [ ] Second identical request returns cached result with noticeably lower latency
- [ ] FastAPI `/docs` shows the endpoint with correct schema and example
- [ ] [FILL: add more as needed]

---

## 8. Testing Requirements [FILL]

1. Start backend: `uvicorn app.main:app --reload --port 8000`
2. Open `http://localhost:8000/docs` — confirm new endpoint appears with correct schema
3. Execute via Swagger UI or curl:
   ```bash
   curl "http://localhost:8000/api/v1/[FILL: path]"
   ```
4. Confirm response matches the Pydantic model defined in step 2
5. [FILL: if external service] Observe FastAPI logs — confirm `await asyncio.sleep(...)` delay visible between Nominatim/external calls
6. Call endpoint a second time — confirm cache hit (no external call in logs, faster response)
7. [FILL: any additional integration check with frontend, e.g., "Open Dashboard → DevTools Network → confirm endpoint called once on load"]
