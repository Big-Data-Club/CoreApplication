"""Small durable LLM worker: no embedding, Kafka, Qdrant or Neo4j warmup."""
import asyncio
import logging
from app.core.database import init_ai_pool, close_ai_pool
from app.services.lab_authoring_service import run_lab_authoring_worker


async def main():
    await init_ai_pool()
    try:
        await run_lab_authoring_worker()
    finally:
        await close_ai_pool()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
