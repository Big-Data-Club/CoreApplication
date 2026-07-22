import asyncio
import json
import logging
import os
from datetime import datetime
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("personalize_worker")

from app.core.config import get_settings
from app.services.lakehouse import lakehouse_service

settings = get_settings()
_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        await _producer.start()
        logger.info("AIOKafkaProducer started successfully")
    return _producer


async def close_producer():
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
        logger.info("AIOKafkaProducer stopped")


async def publish_profile_update(user_id: int, course_id: int, profile: dict):
    """Publish profile update to Kafka for ai-service consumption."""
    try:
        producer = await get_producer()
        topic = "personalize.profile.updated"
        payload = {
            "user_id": user_id,
            "course_id": course_id,
            "profile": profile
        }
        key = f"{user_id}:{course_id}".encode("utf-8")
        await producer.send_and_wait(topic, value=payload, key=key)
        logger.info(f"Published profile update event to {topic} for student={user_id} course={course_id}")
    except Exception as e:
        logger.error(f"Failed to publish profile update event: {str(e)}")


async def process_interaction_event(event: dict):
    """Process single interaction event: ingest to DuckDB, compute Gold profile, publish update."""
    user_id = event.get("user_id")
    course_id = event.get("course_id")
    if not user_id or not course_id:
        logger.warning(f"Discarding event with missing user_id/course_id: {event}")
        return

    # 1. Ingest into DuckDB
    lakehouse_service.ingest_interaction(event)

    # 2. Compute Gold profile
    profile = lakehouse_service.get_student_profile(int(user_id), int(course_id))

    # 3. Publish update event
    await publish_profile_update(int(user_id), int(course_id), profile)


async def publish_notification_trigger(user_id: int, course_id: int, alert_type: str, alert_message: str):
    """Publish a struggle alert/inactivity trigger to Kafka."""
    try:
        producer = await get_producer()
        topic = "personalize.notification.trigger"
        payload = {
            "user_id": user_id,
            "course_id": course_id,
            "alert_type": alert_type,
            "alert_message": alert_message,
            "detected_at": datetime.now().isoformat()
        }
        key = f"{user_id}:{alert_type}".encode("utf-8")
        await producer.send_and_wait(topic, value=payload, key=key)
        logger.info(f"Published notification trigger to {topic} for student={user_id}, type={alert_type}")
    except Exception as e:
        logger.error(f"Failed to publish notification trigger event: {str(e)}")


async def run_notification_detector():
    """Background task to scan Gold alerts and trigger Kafka notifications."""
    # Wait for the system to settle on startup
    await asyncio.sleep(10)
    while True:
        try:
            logger.info("Running struggle alert detector query...")
            alerts = lakehouse_service.get_gold_struggle_alerts()
            for alert in alerts:
                user_id = alert["user_id"]
                course_id = alert["course_id"]
                alert_type = alert["alert_type"]
                alert_message = alert["alert_message"]
                node_id = alert.get("node_id")
                
                # Normalize node_id (DuckDB might return float, None, or int)
                if node_id is not None:
                    try:
                        import math
                        if isinstance(node_id, float) and math.isnan(node_id):
                            node_id = None
                        else:
                            node_id = int(node_id)
                    except (ValueError, TypeError):
                        node_id = None

                # Check if notification was recently sent (24h cooldown)
                recently_sent = lakehouse_service.has_notification_been_sent_recently(
                    user_id=int(user_id),
                    alert_type=alert_type,
                    node_id=node_id,
                    cooldown_hours=24
                )
                
                if not recently_sent:
                    # Publish to Kafka
                    await publish_notification_trigger(
                        user_id=int(user_id),
                        course_id=int(course_id),
                        alert_type=alert_type,
                        alert_message=alert_message
                    )
                    # Record in ledger
                    lakehouse_service.record_sent_notification(
                        user_id=int(user_id),
                        alert_type=alert_type,
                        node_id=node_id
                    )
        except Exception as e:
            logger.error(f"Error in notification detector loop: {str(e)}")
        
        # Check every 2 minutes for new alerts
        await asyncio.sleep(120)


async def run_archive_scheduler():
    """Background task to run Lakehouse Parquet archiving pipeline once every 1 hour."""
    while True:
        try:
            logger.info("Running scheduled Lakehouse archival task (Bronze -> Parquet)...")
            lakehouse_service.archive_interactions_to_parquet(age_days=7)
        except Exception as e:
            logger.error(f"Lakehouse archival task error: {str(e)}")
        await asyncio.sleep(3600)  # Sleep for 1 hour


async def main():
    logger.info("Initializing Personalize Kafka Worker")
    
    # Start background tasks
    asyncio.create_task(run_archive_scheduler())
    asyncio.create_task(run_notification_detector())

    consumer = AIOKafkaConsumer(
        "lms.analytics.interactions",
        "user.login.events",
        "lms.analytics.telemetry",
        "lms.course.interactions",
        bootstrap_servers=settings.kafka_brokers,
        group_id="personalize-worker-group",
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        auto_offset_reset="earliest"
    )

    await consumer.start()
    logger.info("Personalize Kafka Consumer started")

    try:
        async for msg in consumer:
            if not msg.value:
                continue
            logger.debug(f"Received message from topic {msg.topic}: {msg.value}")
            if msg.topic == "lms.analytics.interactions":
                await process_interaction_event(msg.value)
            elif msg.topic == "user.login.events":
                lakehouse_service.ingest_login_event(msg.value)
            elif msg.topic == "lms.analytics.telemetry":
                lakehouse_service.ingest_clickstream_event(msg.value)
            elif msg.topic == "lms.course.interactions":
                lakehouse_service.ingest_course_interaction(msg.value)
    except asyncio.CancelledError:
        logger.info("Personalize Kafka Worker cancelled")
    finally:
        await consumer.stop()
        await close_producer()
        logger.info("Personalize Kafka Worker stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())

