# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────────────────────
# FF Gateway — Multi-stage Docker build
# Base: python:3.11-slim  |  Non-root user  |  Gunicorn production server
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed for pycryptodome
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: production image ─────────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL maintainer="Esporizon Engineering <dev@esporizon.com>"
LABEL description="Free Fire Player Info Gateway"
LABEL version="1.0.0"

# Non-root user for security
RUN groupadd --gid 1001 gateway \
    && useradd --uid 1001 --gid gateway --shell /bin/sh --no-create-home gateway

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source
COPY src/ ./src/

# Create token cache directory writeable by non-root user
RUN mkdir -p /tmp && chown gateway:gateway /tmp

USER gateway

# Default port (overridable via ENV)
ENV PORT=8000
EXPOSE $PORT

# Azure App Service health probe path
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(f'http://localhost:{__import__(\"os\").getenv(\"PORT\",\"8000\")}/health')" || exit 1

# Gunicorn: 4 workers, 60s timeout, bind to $PORT
CMD ["sh", "-c", "gunicorn --workers 4 --timeout 60 --bind 0.0.0.0:${PORT:-8000} --access-logfile - --error-logfile - src.app:app"]
