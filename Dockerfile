FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Source
COPY app/ ./app/
COPY data/sops/ ./data/sops/
COPY scripts/ ./scripts/

# R-16: Copy pre-built frontend (run `npm run build` in frontend/ before docker build)
COPY frontend/dist/ ./frontend/dist/

RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003", "--loop", "asyncio"]
