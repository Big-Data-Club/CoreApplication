"""Dedicated durable worker for long-running course blueprint generation."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from uuid import UUID

from aiokafka import AIOKafkaConsumer
from app.core.database import close_ai_pool, init_ai_pool
from app.core.logging_config import configure_logging
from app.services.course_blueprint_job_service import recoverable_blueprint_ids, run_course_blueprint_job
from app.services.course_material_routing_job_service import recoverable_material_routing_ids, run_material_routing_job

configure_logging()
logger = logging.getLogger(__name__)
TOPIC = "lms.course-blueprint.command"


async def _run_exclusively(blueprint_id: UUID, worker_id: str, execution_lock: asyncio.Lock) -> bool:
    """One CPU/LLM-heavy job per replica; scale pods, not local fan-out."""
    async with execution_lock:
        return await run_course_blueprint_job(blueprint_id, worker_id)


async def _recover(worker_id: str, execution_lock: asyncio.Lock) -> None:
    for blueprint_id in await recoverable_blueprint_ids():
        await _run_exclusively(blueprint_id, worker_id, execution_lock)
    for routing_id in await recoverable_material_routing_ids():
        async with execution_lock:
            await run_material_routing_job(routing_id, worker_id)


async def _reconcile_forever(worker_id: str, execution_lock: asyncio.Lock) -> None:
    """Recover rows whose Kafka notification was lost or whose lease expired."""
    while True:
        await asyncio.sleep(60)
        try:
            await _recover(worker_id, execution_lock)
        except Exception:
            logger.exception("Course blueprint recovery sweep failed")


async def main() -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    await init_ai_pool()
    execution_lock = asyncio.Lock()
    # Recovery makes the database authoritative even if Kafka was unavailable
    # at enqueue time or a pod died after Kafka delivered a message.
    await _recover(worker_id, execution_lock)
    consumer = AIOKafkaConsumer(
        TOPIC, bootstrap_servers=os.getenv("KAFKA_BROKERS", "kafka:9092"),
        group_id="course-blueprint-worker-group", value_deserializer=lambda raw: json.loads(raw.decode()),
        enable_auto_commit=False, auto_offset_reset="earliest", max_poll_interval_ms=1_800_000,
        session_timeout_ms=60_000, heartbeat_interval_ms=10_000, request_timeout_ms=70_000,
    )
    await consumer.start()
    logger.info("Course blueprint worker ready", extra={"worker_id": worker_id, "topic": TOPIC})
    reconciler = asyncio.create_task(_reconcile_forever(worker_id, execution_lock))
    try:
        async for message in consumer:
            try:
                if message.value.get("routing_id"):
                    async with execution_lock:
                        await run_material_routing_job(UUID(str(message.value["routing_id"])), worker_id)
                else:
                    blueprint_id = UUID(str(message.value.get("blueprint_id")))
                    await _run_exclusively(blueprint_id, worker_id, execution_lock)
                await consumer.commit()
            except Exception:
                logger.exception("Course blueprint command failed before completion")
                # Leave the Kafka offset uncommitted; another delivery plus DB
                # lease/recovery makes this safe without duplicate planning.
                await asyncio.sleep(2)
    finally:
        reconciler.cancel()
        await asyncio.gather(reconciler, return_exceptions=True)
        await consumer.stop()
        await close_ai_pool()


if __name__ == "__main__":
    asyncio.run(main())
