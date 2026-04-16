#!/usr/bin/env bash
# =============================================================================
# startup.sh — R-16: NOC Platform Production Server
#
# Builds the React frontend then starts FastAPI on port 8003.
# A single process serves both the API (/api/v1/*) and the NOC dashboard UI.
#
# Usage:
#   bash startup.sh                    # build frontend + start server
#   SKIP_BUILD=true bash startup.sh    # skip build (use existing dist/)
#   PORT=9000 bash startup.sh          # use a different port
#
# Prerequisites:
#   - Node.js >= 18 + npm  (for frontend build)
#   - Python env with ticket-resolve installed (pip install -e .)
#   - ChromaDB running: python3 -c "import sys,chromadb.cli.cli as c; sys.argv=['chroma','run','--host','0.0.0.0','--port','8001','--path','./data/chroma']; c.app()"
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8003}"
SKIP_BUILD="${SKIP_BUILD:-false}"

echo "============================================================"
echo " NOC Platform — R-16 Production Server"
echo "============================================================"
echo " Repo:  $REPO"
echo " Port:  $PORT"
echo ""

# ── 1. Frontend build ─────────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" != "true" ]]; then
  echo "[1/2] Building frontend..."

  if ! command -v npm &>/dev/null; then
    echo "ERROR: npm not found. Install Node.js >= 18 and retry."
    exit 1
  fi

  cd "$REPO/frontend"
  npm install --prefer-offline --silent

  # Call vite directly — avoids Windows .bin\ PATH resolution issues with npm run build
  node node_modules/vite/bin/vite.js build

  if [[ ! -f "$REPO/frontend/dist/index.html" ]]; then
    echo "ERROR: Build completed but frontend/dist/index.html not found."
    exit 1
  fi

  echo "      → frontend/dist/ ready"
  echo ""
else
  echo "[1/2] Skipping frontend build (SKIP_BUILD=true)"
  if [[ ! -f "$REPO/frontend/dist/index.html" ]]; then
    echo "WARNING: frontend/dist/index.html not found — server will show fallback page."
  fi
  echo ""
fi

# ── 2. Start FastAPI ──────────────────────────────────────────────────────────
echo "[2/2] Starting FastAPI on port $PORT..."
cd "$REPO"

# Activate virtualenv if present
if [[ -f ".venv/Scripts/activate" ]]; then
  # Git Bash on Windows
  source ".venv/Scripts/activate"
elif [[ -f ".venv/bin/activate" ]]; then
  # Linux / macOS
  source ".venv/bin/activate"
fi

echo ""
echo "  NOC Dashboard : http://localhost:${PORT}/"
echo "  API docs      : http://localhost:${PORT}/docs"
echo "  Health        : http://localhost:${PORT}/api/v1/health"
echo ""

exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --loop asyncio
