# ==========================================
# Stage 1: Build virtual environment using uv
# ==========================================
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binaries
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Create a virtual environment
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install base dependencies (ML layers, etc.)
COPY requirements.base.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --compile-bytecode -r requirements.base.txt

# Install application dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --compile-bytecode -r requirements.txt

# ==========================================
# Stage 2: Final minimal runner image
# ==========================================
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        # curl: used by HEALTHCHECK CMD
        curl \
        # libgomp1: required by onnxruntime for OpenMP parallelism
        libgomp1 \
        # ffmpeg: required by yt-dlp to extract audio
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appuser \
 && useradd  --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtualenv from builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    # Model cache directory (backed by Docker volume in docker-compose.yml)
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/models \
    # Prevent ML libraries from spawning too many threads per worker.
    # ai-service runs multiple workers; unconstrained threads cause thrashing.
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false

# ── Model cache directory (bind-mounted volume in production) ─────────────
RUN mkdir -p /app/.cache/models \
 && chown -R appuser:appuser /app/.cache

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--workers", "1"]