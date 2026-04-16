# Low-Level Design — NOC Dashboard Web Server

## Document Metadata

| Field      | Value                                           |
|------------|-------------------------------------------------|
| Release    | Release 16 — NOC Dashboard Web Server           |
| RICEF ID   | R-16                                            |
| RICEF Type | I (Interface)                                   |
| Author     | NOC Platform Team                               |
| Date       | 2026-04-16                                      |
| Version    | 1.0                                             |
| Status     | Approved                                        |

## Platform Reference

- Backend: FastAPI 0.115 · Python 3.12 · SQLite (`data/tickets.db`) · LangChain 0.3 · ChromaDB
- Frontend: React 18 · TypeScript · Vite · TailwindCSS · shadcn/ui · Recharts · React Query v5
- Repository path: `ticket-resolve/`

---

## 1. Module Breakdown

### Backend

**`app/main.py`** *(modified)*

```python
# New helper
def _dist_dir() -> Path:
    # Returns Path(__file__).parent.parent / "frontend" / "dist"
    # Used by StaticFiles mount and SPA route handlers

# New constant
_FALLBACK_HTML: str = """<!doctype html>
<html><head><title>NOC Platform</title></head>
<body><p>Frontend not built. Run: bash startup.sh</p></body></html>"""

# New StaticFiles mount (added to app after existing routes)
app.mount(
    "/assets",
    StaticFiles(directory=str(_dist_dir() / "assets"), html=False),
    name="assets",
)

# New route: SPA root
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def spa_root() -> HTMLResponse:
    # Reads frontend/dist/index.html; falls back to _FALLBACK_HTML if not found
    index = _dist_dir() / "index.html"
    return HTMLResponse(content=index.read_text() if index.exists() else _FALLBACK_HTML)

# New route: SPA catch-all (must be last route to avoid overriding API routes)
@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def spa_catchall(full_path: str) -> HTMLResponse:
    # Same as spa_root — returns index.html for any unmatched path
    index = _dist_dir() / "index.html"
    return HTMLResponse(content=index.read_text() if index.exists() else _FALLBACK_HTML)

# CORS: tightened for production
origins = ["http://localhost:8003"]   # production — no wildcard
```

**`app/config.py`** *(modified — 2 new Settings fields)*

```python
SERVE_FRONTEND: bool = True
# When True, app/main.py mounts StaticFiles and registers SPA routes.
# Set to False for API-only development (avoids needing frontend/dist/ present).

FRONTEND_DIST_DIR: str = ""
# Override path to the frontend dist directory.
# If empty string, _dist_dir() computes the default relative path.
```

### Frontend

**`frontend/vite.config.ts`** *(modified)*

```typescript
export default defineConfig({
  // ... existing config ...
  build: {
    outDir: 'dist',       // explicit — prevents accidental non-standard output location
    emptyOutDir: true,    // clean dist/ before each build
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8003',   // updated from 8000 → 8003
    },
  },
})
```

### Infrastructure

**`Dockerfile`** *(modified)*

```dockerfile
# After React build stage:
COPY frontend/dist/ ./frontend/dist/

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

**`startup.sh`** *(new file)*

```bash
#!/usr/bin/env bash
set -e

echo "==> Building frontend..."
node node_modules/vite/bin/vite.js build

echo "==> Starting uvicorn on port 8003..."
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003
```

---

## 2. Database Schema DDL

No new database tables introduced in R-16. Existing schema unchanged.

---

## 3. Pydantic Models

No new Pydantic API models. The two new Settings fields added to `app/config.py` are:

```python
class Settings(BaseSettings):
    # ... existing fields ...

    SERVE_FRONTEND: bool = True
    # Feature flag — when True, FastAPI mounts StaticFiles and SPA catch-all routes.

    FRONTEND_DIST_DIR: str = ""
    # Optional override for the frontend dist directory path.
    # Defaults to <repo_root>/frontend/dist when empty.
```

---

## 4. React Component Tree

No new React components. SPA routing handled server-side by FastAPI catch-all route.

---

## 5. Route Priority

FastAPI evaluates routes in registration order. R-16 exploits this to ensure API routes always win over the SPA catch-all:

| Priority | Path Pattern          | Handler           | Notes                               |
|----------|-----------------------|-------------------|-------------------------------------|
| 1        | `/api/v1/*`           | Existing routers  | Registered first via `include_router` |
| 2        | `/assets/*`           | StaticFiles       | Mounted before SPA routes           |
| 3        | `/`                   | `spa_root()`      | Explicit root handler               |
| 4        | `/{full_path:path}`   | `spa_catchall()`  | Catch-all — last route registered   |

---

## 6. Error Handling Matrix

| Scenario | HTTP Status | Response | Recovery |
|---|---|---|---|
| `frontend/dist/` not built | 200 | Inline `_FALLBACK_HTML` with build instructions | Run `bash startup.sh` |
| `frontend/dist/index.html` missing | 200 | Inline `_FALLBACK_HTML` | Run `npm run build` in `frontend/` |
| Static asset file not found | 404 | Starlette default 404 | Rebuild frontend; check asset hash in HTML |
| API route not found | 404 | FastAPI JSON `{"detail":"Not Found"}` | Correct the API path |
| uvicorn startup failure | Process exit | stderr log | Check port 8003 availability; check Python deps |
