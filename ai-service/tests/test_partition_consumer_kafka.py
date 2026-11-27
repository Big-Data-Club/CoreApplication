"""Opt-in Kafka 3.7 regressions; use a disposable broker, never production."""

import asyncio
import base64
import json
import os
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from app.worker.partition_consumer import PartitionConsumer

BROKERS = os.getenv("WORKER_TEST_KAFKA_BROKERS")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not BROKERS, reason="Disposable broker not supplied"),
]


async def until(predicate, timeout=20):
    async with asyncio.timeout(timeout):
        while not await predicate():
            await asyncio.sleep(0.05)


async def fixture():
    topic, group = "worker-test-" + uuid4().hex, "worker-group-" + uuid4().hex
    admin = AIOKafkaAdminClient(bootstrap_servers=BROKERS)
    await admin.start()
    await admin.create_topics([NewTopic(topic, 2, 1)])
    await admin.close()
    producer = AIOKafkaProducer(bootstrap_servers=BROKERS, enable_idempotence=True)
    await producer.start()
    for partition in range(2):
        for offset in range(2):
            await producer.send_and_wait(
                topic,
                partition=partition,
                value=json.dumps({"job_id": f"{partition}:{offset}"}).encode(),
            )
    await producer.stop()
    return topic, group


def client(topic, group, handler):
    consumer = AIOKafkaConsumer(
        bootstrap_servers=BROKERS,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    runner = PartitionConsumer(
        consumer, [topic], group, handler, concurrency=2, drain_seconds=0
    )
    return consumer, runner


async def stop(consumer, task):
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await consumer.stop()


async def committed(consumer, topic, partition, expected):
    return await consumer.committed(TopicPartition(topic, partition)) == expected


async def test_restart_replays_cancelled_record_but_not_committed_partition():
    topic, group = await fixture()
    started = asyncio.Event()

    async def first(msg):
        if msg.partition == 0:
            started.set()
            await asyncio.Event().wait()

    c, w = client(topic, group, first)
    await c.start()
    task = asyncio.create_task(w.run())
    try:
        await asyncio.wait_for(started.wait(), 20)
        await until(lambda: committed(c, topic, 1, 2))
        assert await c.committed(TopicPartition(topic, 0)) is None
    finally:
        await stop(c, task)
    received = []

    async def second(msg):
        received.append((msg.partition, msg.offset))

    c2, w2 = client(topic, group, second)
    await c2.start()
    task2 = asyncio.create_task(w2.run())
    try:
        await until(lambda: committed(c2, topic, 0, 2))
        assert received == [(0, 0), (0, 1)]
    finally:
        await stop(c2, task2)


async def test_rebalance_fences_inflight_and_new_owner_finishes():
    topic, group = await fixture()
    blocked, release, seen = set(), asyncio.Event(), []

    async def first(msg):
        blocked.add(msg.partition)
        await release.wait()
        seen.append((msg.partition, msg.offset))

    c1, w1 = client(topic, group, first)
    await c1.start()
    t1 = asyncio.create_task(w1.run())
    c2 = t2 = None
    try:

        async def both():
            return len(blocked) == 2

        await until(both)

        async def second(msg):
            seen.append((msg.partition, msg.offset))

        c2, w2 = client(topic, group, second)
        await c2.start()
        t2 = asyncio.create_task(w2.run())

        async def assigned():
            return bool(c2.assignment()) and len(c1.assignment()) == 1

        await until(assigned)
        release.set()

        async def done():
            return all(
                [await committed(c1, topic, 0, 2), await committed(c1, topic, 1, 2)]
            )

        await until(done)
        assert sorted(seen) == [(0, 0), (0, 1), (1, 0), (1, 1)]
    finally:
        await stop(c1, t1)
        if c2:
            if t2:
                await stop(c2, t2)
            else:
                await c2.stop()


async def test_large_malformed_record_is_durably_quarantined_before_advancing():
    topic, group = "bad-wire-" + uuid4().hex, "bad-group-" + uuid4().hex
    admin = AIOKafkaAdminClient(bootstrap_servers=BROKERS)
    await admin.start()
    try:
        await admin.create_topics(
            [
                NewTopic(topic, 1, 1),
                NewTopic(
                    "ai.worker.failed.v1",
                    3,
                    1,
                    topic_configs={"max.message.bytes": "2097152"},
                ),
            ]
        )
    finally:
        await admin.close()
    raw = b"invalid JSON " + b"x" * 900_000
    wire = AIOKafkaProducer(bootstrap_servers=BROKERS, enable_idempotence=True)
    dead = AIOKafkaProducer(
        bootstrap_servers=BROKERS,
        enable_idempotence=True,
        max_request_size=2 * 1024 * 1024,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    dlq = AIOKafkaConsumer(
        "ai.worker.failed.v1",
        bootstrap_servers=BROKERS,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_partition_fetch_bytes=2 * 1024 * 1024,
    )
    await wire.start()
    await dead.start()
    await dlq.start()
    c = task = None
    seen = []

    async def handler(msg):
        seen.append(msg.offset)

    try:
        await wire.send_and_wait(topic, key=b"private-key", value=raw)
        await wire.send_and_wait(topic, value=b'{"job_id":"next"}')
        c, runner = client(topic, group, handler)
        await c.start()
        with patch(
            "app.worker.kafka_producer.get_kafka_producer", AsyncMock(return_value=dead)
        ):
            task = asyncio.create_task(runner.run())
            await until(lambda: committed(c, topic, 0, 2))
            result = await asyncio.wait_for(dlq.getone(), 20)
            envelope = json.loads(result.value)
            assert envelope["source_topic"] == topic
            assert envelope["source_offset"] == 0
            assert envelope["error_type"] == "InvalidEnvelope"
            assert base64.b64decode(envelope["payload_base64"]) == raw
            assert seen == [1]
            await stop(c, task)
            c = task = None
    finally:
        if c:
            if task:
                await stop(c, task)
            else:
                await c.stop()
        await dlq.stop()
        await dead.stop()
        await wire.stop()
