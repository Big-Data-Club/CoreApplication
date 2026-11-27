"""Bounded partition workers with explicit acknowledgements and safe revocation."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from types import SimpleNamespace

from aiokafka import ConsumerRebalanceListener, TopicPartition
from aiokafka.errors import CommitFailedError, KafkaError
from aiokafka.structs import OffsetAndMetadata
from app.worker.contracts import DEAD_LETTER_TOPIC

logger = logging.getLogger(__name__)


class InvalidEnvelope(ValueError):
    """Invalid wire data must be quarantined without interpreting it."""


class PartitionConsumer(ConsumerRebalanceListener):
    """At most one in-flight record per partition; no commit in cancellation paths."""

    def __init__(
        self,
        consumer,
        topics,
        group_id,
        handler,
        *,
        concurrency=1,
        attempts=3,
        retry_delay=1.0,
        drain_seconds=25.0,
        quarantine=None,
    ):
        self.consumer, self.group_id, self.handler = consumer, group_id, handler
        self.concurrency = max(1, concurrency)
        self.attempts, self.retry_delay = attempts, retry_delay
        self.drain_seconds = drain_seconds
        self.quarantine = quarantine or self._quarantine
        self.tasks = {}
        self.settling = set()
        self.epochs = {}
        self.last_poll = 0.0
        self.poll_ok = False
        self.running = False
        consumer.subscribe(topics=topics, listener=self)

    @property
    def ready(self):
        return (
            self.running
            and self.poll_ok
            and bool(self.consumer.assignment())
            and time.monotonic() - self.last_poll < 30
        )

    async def on_partitions_revoked(self, revoked):
        # Fence first, then cancel: old tasks must never acknowledge new ownership.
        tasks = []
        for tp in revoked:
            self.epochs[tp] = self.epochs.get(tp, 0) + 1
            task = self.tasks.pop(tp, None)
            self.settling.discard(tp)
            if task:
                task.cancel()
                tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)
        self.settling.difference_update(revoked)

    async def on_partitions_assigned(self, assigned):
        for tp in assigned:
            self.epochs[tp] = self.epochs.get(tp, 0) + 1
            self.settling.discard(tp)
        if assigned:
            self.consumer.resume(*assigned)

    def _owns(self, tp, epoch):
        return tp in self.consumer.assignment() and self.epochs.get(tp, 0) == epoch

    async def _quarantine(self, record, error):
        from app.worker.kafka_producer import get_kafka_producer

        raw = record.value
        if not isinstance(raw, bytes):
            raw = json.dumps(raw, separators=(",", ":")).encode()
        producer = await get_kafka_producer()
        await producer.send_and_wait(
            DEAD_LETTER_TOPIC,
            key=f"{self.group_id}:{record.topic}:{record.partition}:{record.offset}".encode(),
            value={
                "schema_version": 1,
                "consumer_group": self.group_id,
                "source_topic": record.topic,
                "source_partition": record.partition,
                "source_offset": record.offset,
                "source_key_base64": base64.b64encode(record.key or b"").decode(),
                "payload_base64": base64.b64encode(raw).decode(),
                "error_type": type(error).__name__,
            },
        )

    @staticmethod
    def _decode(record):
        try:
            value = (
                json.loads(record.value)
                if isinstance(record.value, (bytes, str))
                else record.value
            )
        except (ValueError, UnicodeError) as exc:
            raise InvalidEnvelope("Invalid JSON envelope") from exc
        if not isinstance(value, dict) or not value:
            raise InvalidEnvelope("Expected nonempty JSON object")
        return SimpleNamespace(
            topic=record.topic,
            partition=record.partition,
            offset=record.offset,
            key=record.key,
            value=value,
        )

    async def _handle(self, record, tp, epoch):
        error = None
        for attempt in range(self.attempts):
            if not self._owns(tp, epoch):
                return
            try:
                decoded = self._decode(record)
                logger.info(
                    "Kafka message received",
                    extra={
                        "group_id": self.group_id,
                        "topic": tp.topic,
                        "partition": tp.partition,
                        "offset": record.offset,
                        "job_id": decoded.value.get("job_id"),
                        "command_type": decoded.value.get("command_type"),
                        "attempt": attempt + 1,
                    },
                )
                await self.handler(decoded)
                error = None
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = exc
                logger.warning(
                    "Kafka handler failed",
                    extra={
                        "group_id": self.group_id,
                        "topic": tp.topic,
                        "partition": tp.partition,
                        "offset": record.offset,
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                    },
                )
                if isinstance(exc, InvalidEnvelope):
                    break
                if attempt + 1 < self.attempts:
                    await asyncio.sleep(self.retry_delay * 2**attempt)
        # Settling an already-executed record does not consume a CPU/LLM slot.
        # Keep its partition paused, but let other partitions execute even if
        # quarantine or commit is unavailable. Buffers remain one record/partition.
        self.settling.add(tp)
        if error:
            # Broker failure here keeps the source uncommitted. Retry only the
            # quarantine write, never repeatedly execute the failed handler.
            while self._owns(tp, epoch):
                try:
                    await self.quarantine(record, error)
                    logger.error(
                        "Kafka record quarantined",
                        extra={
                            "group_id": self.group_id,
                            "topic": tp.topic,
                            "partition": tp.partition,
                            "offset": record.offset,
                            "error_type": type(error).__name__,
                        },
                    )
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Kafka quarantine unavailable",
                        extra={
                            "group_id": self.group_id,
                            "error_type": type(exc).__name__,
                        },
                    )
                    await asyncio.sleep(max(1, self.retry_delay))
        while self._owns(tp, epoch):
            try:
                await self.consumer.commit(
                    {tp: OffsetAndMetadata(record.offset + 1, "")}
                )
                return
            except CommitFailedError:
                # A rebalance may race its listener; let the new owner replay.
                return record.offset
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Kafka commit unavailable",
                    extra={
                        "group_id": self.group_id,
                        "error_type": type(exc).__name__,
                    },
                )
                await asyncio.sleep(max(1, self.retry_delay))

    async def run(self):
        self.running = True
        try:
            while True:
                self.last_poll = time.monotonic()
                for tp, task in list(self.tasks.items()):
                    if task.done():
                        replay_offset = task.result()
                        self.tasks.pop(tp)
                        self.settling.discard(tp)
                        if tp in self.consumer.assignment():
                            # Only rewind after a failed commit. Successful
                            # records need no extra broker offset lookup.
                            if replay_offset is not None:
                                self.consumer.seek(tp, replay_offset)
                            self.consumer.resume(tp)
                if len(self.tasks) - len(self.settling) >= self.concurrency:
                    await asyncio.wait(
                        self.tasks.values(),
                        timeout=1,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    continue
                try:
                    records = await self.consumer.getmany(
                        timeout_ms=1000, max_records=1
                    )
                except KafkaError as exc:
                    self.poll_ok = False
                    logger.warning(
                        "Kafka poll unavailable",
                        extra={
                            "group_id": self.group_id,
                            "error_type": type(exc).__name__,
                        },
                    )
                    await asyncio.sleep(1)
                    continue
                self.poll_ok = True
                for tp, batch in records.items():
                    if not batch:
                        continue
                    self.consumer.pause(tp)
                    epoch = self.epochs.get(tp, 0)
                    self.tasks[tp] = asyncio.create_task(
                        self._handle(batch[0], tp, epoch),
                        name=f"{self.group_id}:{tp}:{batch[0].offset}",
                    )
        finally:
            self.running = False
            pending = list(self.tasks.values())
            if pending:
                _, unfinished = await asyncio.wait(pending, timeout=self.drain_seconds)
                for task in unfinished:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            self.tasks.clear()
            self.settling.clear()
