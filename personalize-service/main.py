import asyncio
import logging
import time
from fastapi import FastAPI
from prometheus_client import Counter, Histogram, make_asgi_app
from app.api.router import router
from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("personalize_main")

app = FastAPI(
    title="BDC Personalize Service",
    description="Lightweight DuckDB Lakehouse for student interaction personalization",
    version="1.0"
)

http_requests_total = Counter(
    "bdc_http_requests_total",
    "HTTP requests completed by BDC services.",
    ("service", "method", "route", "status"),
)
http_request_duration_seconds = Histogram(
    "bdc_http_request_duration_seconds",
    "HTTP request duration in seconds for BDC services.",
    ("service", "method", "route", "status"),
)


@app.middleware("http")
async def prometheus_metrics(request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        labels = ("personalize-service", request.method, route_path, str(status))
        http_requests_total.labels(*labels).inc()
        http_request_duration_seconds.labels(*labels).observe(time.perf_counter() - started)


app.mount("/metrics", make_asgi_app())

# Include router
app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "personalize-service"}


@app.on_event("startup")
async def startup_event():
    logger.info("BDC Personalize Service starting...")

    # Start existing Kafka worker
    from app.worker.kafka_worker import main as run_worker
    asyncio.create_task(run_worker())

    # Start the learning-event worker: consumes 'learning-events' produced by
    # the LMS and projects skill mastery into the lakehouse. A crash here must
    # not take down the API, so the task only logs failures.
    from app.worker.learning_event_worker import run_learning_event_worker

    async def _safe_learning_event_worker():
        try:
            await run_learning_event_worker()
        except Exception:
            logger.exception("Learning event worker crashed; API continues serving")

    asyncio.create_task(_safe_learning_event_worker())

    logger.info(
        "BDC Personalize Service started successfully with Kafka analytics + learning event workers"
    )
