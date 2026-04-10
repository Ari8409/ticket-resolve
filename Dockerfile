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

RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
