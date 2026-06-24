import asyncio
import logging
from fastapi import FastAPI
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

# Include router
app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "personalize-service"}


@app.on_event("startup")
async def startup_event():
    logger.info("BDC Personalize Service starting...")
    from app.worker.kafka_worker import main as run_worker
    # Spin off the worker consumer loop as a background task in the same event loop
    asyncio.create_task(run_worker())
    logger.info("BDC Personalize Service started successfully with Kafka background worker")

