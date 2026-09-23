# ============================================================
# backend/Dockerfile — Production-ready image for Render.com
#
# Render uses Linux containers. This Dockerfile:
# - Uses Python 3.12 slim (small, fast)
# - Does NOT install pywin32 (Windows-only, not available on Linux)
# - Installs only production dependencies
# - Runs uvicorn in single-worker mode (Render free tier: 512 MB RAM)
#
# Build locally:
#   docker build -t dyversifying-backend -f backend/Dockerfile .
#
# Run locally:
#   docker run -p 8000:8000 --env-file .env dyversifying-backend
# ============================================================

FROM python:3.12-slim

# Prevent .pyc files and enable unbuffered logging (important for Render logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ---- System dependencies ----
# libpq-dev: PostgreSQL client library (needed by psycopg2-binary)
# curl: health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---- Python dependencies ----
# Copy requirements first (Docker layer cache: only re-run if requirements change)
COPY requirements.txt .

# Install without pywin32 (Windows-only, will fail on Linux)
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir --upgrade pip && \
    grep -v "pywin32" requirements.txt > requirements_linux.txt && \
    pip install --no-cache-dir -r requirements_linux.txt && \
    rm requirements_linux.txt

# ---- Application code ----
COPY . .

# ---- Health check ----
# Render uses this to verify the service is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# ---- Start command ----
# Single worker: appropriate for Render free tier (512 MB RAM)
# --host 0.0.0.0: listen on all interfaces (required in containers)
# --port 10000: Render's default port (configurable via PORT env var)
CMD uvicorn backend.app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-10000} \
    --workers 1 \
    --log-level info
