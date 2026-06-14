# ── ReBrewie Control Pi – Dockerfile ─────────────────────────────────────────
# Multi-stage build: keeps the final image small.
# Target architecture: linux/arm64 (Raspberry Pi 4B 64-bit OS)
#   or linux/amd64 for x86 development/testing.
#
# Build:  docker build -t rebrewie-control-pi .
# Run:    docker run -p 8080:8080 --env-file .env rebrewie-control-pi
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# System deps for pyserial and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc \
      libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependency layer (cached unless requirements.txt changes) ─────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Application layer ─────────────────────────────────────────────────────────
COPY app/       ./app/
COPY recipes/   ./recipes/
COPY .env.example .env.example

# Create recipes volume mount point
RUN mkdir -p /data/recipes

ENV RECIPE_DIR=/data/recipes \
    LOCAL_BIND=0.0.0.0 \
    LOCAL_PORT=8080 \
    BREWIE_TRANSPORT=mock

EXPOSE 8080

# Use a non-root user
RUN useradd -r -u 1001 -g root rebrewie
USER rebrewie

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
