# ── OpsIQ — Production Dockerfile ──────────────────────────
# Multi-stage build: builder → runtime
# Optimized for layer caching, security, and minimal image size
# Build with: DOCKER_BUILDKIT=1 docker build .

# ── Builder Stage ──────────────────────────────────────────
FROM python:3.14-slim AS builder

LABEL maintainer="Ismail-2001" \
      description="OpsIQ — Autonomous Ecommerce Operations Engine" \
      version="0.2.0"

WORKDIR /build

# Install only system deps needed for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files FIRST for layer caching
# Only re-installs deps when requirements.txt or pyproject.toml changes
COPY pyproject.toml requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user hatchling && \
    python -m pip install --user -r requirements.txt

# ── Runtime Stage ──────────────────────────────────────────
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    ENV=production \
    PYTHONPATH=/app \
    # Playwright temp directory
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright

WORKDIR /app

# Install runtime system deps (Playwright + PostgreSQL client)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PostgreSQL client
    libpq5 \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libexpat1 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 \
    # Fonts for rendering
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH="/root/.local/bin:${PATH}"

# Install Playwright Chromium (deps already installed above)
RUN --mount=type=cache,target=/app/.playwright playwright install chromium

# Create non-root user for security
RUN groupadd --system app && \
    useradd --system --gid app --create-home --shell /bin/bash app

# Create directories for runtime
RUN mkdir -p /app/.playwright /app/logs /app/tmp && \
    chown -R app:app /app

# Copy application code
COPY ecommerce_ops/ ./ecommerce_ops/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Copy built dashboard (if exists)
RUN mkdir -p /app/dashboard/dist

# Set ownership
RUN chown -R app:app /app

# Switch to non-root user
USER app

EXPOSE 8000

# Health check — checks DB-aware readiness probe
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "\
import urllib.request; \
r = urllib.request.urlopen('http://localhost:8000/ready'); \
r.read(); \
exit(0) if r.status == 200 else exit(1)"

# Production CMD — uvicorn with graceful shutdown
CMD ["uvicorn", "ecommerce_ops.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "info", \
     "--access-log", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--timeout-graceful-shutdown", "30"]