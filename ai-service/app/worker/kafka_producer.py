import json
import logging
import asyncio
from aiokafka import AIOKafkaProducer
import os
from datetime import date, datetime

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

logger = logging.getLogger(__name__)

_producer: AIOKafkaProducer | None = None

async def get_kafka_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        brokers = os.getenv("KAFKA_BROKERS", "kafka:9092")
        _producer = AIOKafkaProducer(
            bootstrap_servers=brokers,
            value_serializer=lambda v: json.dumps(v, cls=DateTimeEncoder).encode('utf-8')
        )
        await _producer.start()
        logger.info("Kafka Producer started")
    return _producer

async def close_kafka_producer():
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
        logger.info("Kafka Producer stopped")

async def publish_status_event(content_id: int, status: str, chunks_created: int = 0, error: str = ""):
    producer = await get_kafka_producer()
    payload = {
        "content_id": content_id,
        "status": status,
        "chunks_created": chunks_created,
        "error": error,
        "job_id": 0
    }
    
    topic = "ai.document.processed.status"
    key = str(content_id).encode("utf-8")
    
    await producer.send_and_wait(topic, value=payload, key=key)
    logger.info(f"Published status to {topic} for content {content_id}: {status}")


async def publish_graph_event(command: str, status: str, result_count: int = 0, error: str = ""):
    """Send feedback about graph maintenance tasks (like GLOBAL_LINK)."""
    producer = await get_kafka_producer()
    payload = {
        "command": command,
        "status":  status,
        "result_count": result_count,
        "error":   error,
    }
    topic = "ai.graph.status"
    await producer.send_and_wait(topic, value=payload)
    logger.info(f"Published graph event to {topic}: {command} -> {status}")


async def publish_node_merged_event(
    course_id: int,
    survivor_id: int,
    absorbed_ids: list[int],
):
    """Cross-service cascade: tell the LMS to repoint its `node_id` columns
    (micro_lessons, quiz_questions) onto the survivor after a graph merge."""
    if not absorbed_ids:
        return
    producer = await get_kafka_producer()
    payload = {
        "course_id":    course_id,
        "survivor_id":  survivor_id,
        "absorbed_ids": absorbed_ids,
    }
    topic = "ai.graph.node_merged"
    key   = str(survivor_id).encode("utf-8")
    await producer.send_and_wait(topic, value=payload, key=key)
    logger.info(
        "Published %s for course=%d survivor=%d (absorbed=%d)",
        topic, course_id, survivor_id, len(absorbed_ids),
    )


async def publish_ai_job_status(
    job_id: str,
    status: str,
    result: dict | list | None = None,
    error: str = "",
    progress: int | None = None,
):
    """Send feedback about an async AI job (Quiz, Flashcard, Diagnosis, Video)."""
    producer = await get_kafka_producer()
    payload = {
        "job_id": job_id,
        "status": status,
    }
    if result is not None:
        payload["result"] = result
    if error:
        payload["error"] = error
    if progress is not None:
        payload["progress"] = progress
        
    topic = "ai.job.status"
    key = str(job_id).encode("utf-8")
    
    await producer.send_and_wait(topic, value=payload, key=key)
    logger.info(f"Published AI job status to {topic} for job {job_id}: {status} (progress: {progress}%)")



async def publish_consolidation_request(
    user_id: int,
    session_id: str,
    messages: list[dict],
    context: dict,
    job_id: str,
):
    """Publish a request to consolidate a user's chat session background memory."""
    producer = await get_kafka_producer()
    payload = {
        "job_id": job_id,
        "command_type": "CONSOLIDATE_SESSION",
        "payload": {
            "user_id": user_id,
            "session_id": session_id,
            "messages": messages,
            "context": context,
        }
    }
    topic = "lms.ai.command"
    key = str(session_id).encode("utf-8")
    await producer.send_and_wait(topic, value=payload, key=key)
    logger.info(f"Published consolidation request to {topic} for session {session_id}")


