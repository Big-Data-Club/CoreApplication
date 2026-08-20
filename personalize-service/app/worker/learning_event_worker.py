"""
Learning Events Kafka Worker

Consumes learning events from Kafka and updates learner skill states
using the mastery calculation engine.
"""

import asyncio
import json
import logging
from typing import Dict, Optional
from datetime import datetime

from aiokafka import AIOKafkaConsumer
from app.services.mastery_engine import mastery_engine
from app.services.lakehouse import lakehouse_service

logger = logging.getLogger(__name__)


class LearningEventProcessor:
    """Processes learning events and updates skill mastery states."""

    def __init__(self, bootstrap_servers: str = "kafka:9092"):
        self.bootstrap_servers = bootstrap_servers
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

    async def start(self):
        """Start the Kafka consumer and process events."""
        self.consumer = AIOKafkaConsumer(
            'learning-events',
            bootstrap_servers=self.bootstrap_servers,
            group_id='mastery-calculator',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=True,
        )

        await self.consumer.start()
        self.running = True
        logger.info("Learning event processor started, listening to 'learning-events' topic")

        try:
            async for msg in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_event(msg.value)
                except Exception as e:
                    logger.error(f"Error processing event: {e}", exc_info=True)
                    # Continue processing other events even if one fails

        finally:
            await self.stop()

    async def stop(self):
        """Stop the Kafka consumer."""
        self.running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info("Learning event processor stopped")

    async def process_event(self, event: Dict):
        """
        Process a single learning event and update mastery state.

        Args:
            event: Learning event dictionary from Kafka
        """
        event_id = event.get('event_id')
        event_type = event.get('event_type')
        student_id = event.get('student_id')
        skill_id = event.get('skill_id')

        logger.debug(f"Processing event {event_id}: {event_type} for student {student_id}")

        # Only process events that affect mastery
        mastery_relevant_events = {
            'answer_submitted',
            'answer_retried',
            'hint_requested',
            'lesson_completed',
            'question_viewed'
        }

        if event_type not in mastery_relevant_events:
            logger.debug(f"Event type {event_type} does not affect mastery, skipping")
            return

        # Must have skill_id to update mastery
        if not skill_id:
            logger.debug(f"Event {event_id} has no skill_id, skipping mastery update")
            return

        try:
            # Store event in lakehouse
            self._store_event_in_lakehouse(event)

            # Get recent events for this student+skill
            recent_events = self._get_skill_events(student_id, skill_id, limit=50)

            if not recent_events:
                logger.warning(f"No events found for student {student_id}, skill {skill_id}")
                return

            # Calculate mastery
            mastery_state = mastery_engine.calculate_mastery(recent_events)

            # Update learner skill state
            self._update_learner_skill_state(
                student_id=student_id,
                skill_id=skill_id,
                mastery_state=mastery_state
            )

            logger.info(
                f"Updated mastery for student {student_id}, skill {skill_id}: "
                f"mastery={mastery_state['mastery_score']:.2f}, "
                f"confidence={mastery_state['confidence_score']:.2f}"
            )

        except Exception as e:
            logger.error(f"Failed to update mastery for event {event_id}: {e}", exc_info=True)
            raise

    def _store_event_in_lakehouse(self, event: Dict):
        """Store learning event in DuckDB lakehouse."""
        try:
            # Convert to lakehouse format
            event_data = {
                'event_id': event.get('event_id'),
                'event_type': event.get('event_type'),
                'student_id': event.get('student_id'),
                'session_id': event.get('session_id'),
                'course_id': event.get('course_id'),
                'lesson_id': event.get('lesson_id'),
                'question_id': event.get('question_id'),
                'skill_id': event.get('skill_id'),
                'difficulty': event.get('difficulty'),
                'correct': event.get('correct'),
                'attempt_no': event.get('attempt_no'),
                'response_time_ms': event.get('response_time_ms'),
                'hint_count': event.get('hint_count'),
                'metadata': json.dumps(event.get('metadata', {})),
                'created_at': event.get('created_at', datetime.now().isoformat()),
            }

            lakehouse_service.ingest_learning_event(event_data)

        except Exception as e:
            logger.error(f"Failed to store event in lakehouse: {e}", exc_info=True)
            # Don't raise - lakehouse storage failure shouldn't block mastery update

    def _get_skill_events(self, student_id: int, skill_id: int, limit: int = 50) -> list:
        """Get recent learning events for a student+skill from lakehouse."""
        try:
            events = lakehouse_service.get_skill_events(student_id, skill_id, limit)
            return events
        except Exception as e:
            logger.error(f"Failed to get skill events: {e}", exc_info=True)
            return []

    def _update_learner_skill_state(
        self,
        student_id: int,
        skill_id: int,
        mastery_state: Dict
    ):
        """Update learner skill state in lakehouse."""
        try:
            state_data = {
                'student_id': student_id,
                'skill_id': skill_id,
                'mastery_score': mastery_state['mastery_score'],
                'confidence_score': mastery_state['confidence_score'],
                'attempt_count': mastery_state['attempt_count'],
                'accuracy': mastery_state['accuracy'],
                'avg_response_time_ms': mastery_state['avg_response_time_ms'],
                'hint_dependency': mastery_state['hint_dependency'],
                'recommended_difficulty': mastery_state['recommended_difficulty'],
                'last_practiced_at': mastery_state.get('last_practiced_at'),
                'updated_at': datetime.now().isoformat(),
            }

            lakehouse_service.update_learner_skill_state(state_data)

        except Exception as e:
            logger.error(f"Failed to update learner skill state: {e}", exc_info=True)
            raise


# Global processor instance
learning_event_processor = LearningEventProcessor()


async def run_learning_event_worker():
    """Main entry point for the Kafka worker."""
    logger.info("Starting learning event worker...")
    try:
        await learning_event_processor.start()
    except KeyboardInterrupt:
        logger.info("Shutting down learning event worker...")
        await learning_event_processor.stop()
    except Exception as e:
        logger.error(f"Learning event worker crashed: {e}", exc_info=True)
        raise
