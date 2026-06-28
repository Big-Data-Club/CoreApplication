# ==========================================
# Stage 1: Build dependencies in virtual env using uv
# ==========================================
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libc-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binaries
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Create virtual environment
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

# Install dependencies using cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --compile-bytecode -r requirements.txt

# ==========================================
# Stage 2: Final minimal runner image
# ==========================================
FROM python:3.12-slim AS runner

# Install runtime utilities only (curl is needed for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appuser \
 && useradd  --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy python virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create data directory and set permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

# Copy app code
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8082"]
