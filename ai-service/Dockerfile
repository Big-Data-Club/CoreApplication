FROM python:3.12-slim AS ml-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.base.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel \
        --default-timeout=100 \
        --wheel-dir=/wheels/ml \
        -r requirements.base.txt

FROM python:3.12-slim AS app-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel \
        --default-timeout=100 \
        --wheel-dir=/wheels/app \
        -r requirements.txt

FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        # curl: used by HEALTHCHECK CMD
        curl \
        # libgomp1: required by onnxruntime for OpenMP parallelism
        libgomp1 \
        # ffmpeg: required by yt-dlp to extract audio
        ffmpeg \
        # fonts: for video rendering slide creation
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*



RUN groupadd --gid 1001 appuser \
 && useradd  --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=ml-builder  /wheels/ml  /tmp/wheels/
COPY                    requirements.base.txt /tmp/requirements.base.txt
RUN pip install --no-cache-dir \
        --no-index \
        --find-links=/tmp/wheels \
        -r /tmp/requirements.base.txt \
 && rm -rf /tmp/wheels /tmp/requirements.base.txt

COPY --from=app-builder /wheels/app /tmp/wheels/
COPY                    requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
        --no-index \
        --find-links=/tmp/wheels \
        -r /tmp/requirements.txt \
 && rm -rf /tmp/wheels /tmp/requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1 \
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