"""Regression coverage for acknowledgement, ordering and cancellation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from aiokafka import TopicPartition
from aiokafka.errors import CommitFailedError
from app.worker.partition_consumer import PartitionConsumer, InvalidEnvelope


def record(offset=0, partition=0, value=b'{"job_id":"job","command_type":"TEST"}'):
    return SimpleNamespace(
        topic="test", partition=partition, offset=offset, key=b"key", value=value
    )


class Consumer:
    def __init__(self, records=()):
        self.records, self.positions = list(records), {}
        self.assigned = {TopicPartition("test", i) for i in (0, 1)}
        self.paused, self.offsets, self.commits = set(), {}, []

    def subscribe(self, topics, listener):
        self.listener = listener

    def assignment(self):
        return self.assigned

    def pause(self, *tps):
        self.paused.update(tps)

    def resume(self, *tps):
        self.paused.difference_update(tps)

    async def commit(self, offsets):
        self.commits.append(offsets)
        self.offsets.update({tp: om.offset for tp, om in offsets.items()})

    async def committed(self, tp):
        return self.offsets.get(tp)

    def seek(self, tp, offset):
        self.positions[tp] = offset

    async def getmany(self, **kwargs):
        for r in self.records:
            tp = TopicPartition(r.topic, r.partition)
            if (
                tp in self.assigned
                and tp not in self.paused
                and r.offset >= self.positions.get(tp, 0)
            ):
                self.positions[tp] = r.offset + 1
                return {tp: [r]}
        await asyncio.sleep(0.001)
        return {}


def worker(c, handler, **kwargs):
    return PartitionConsumer(
        c, ("test",), "group", handler, retry_delay=0, drain_seconds=0, **kwargs
    )


@pytest.mark.asyncio
async def test_retry_and_quarantine_finish_before_commit():
    c, handler = Consumer(), AsyncMock(side_effect=RuntimeError("dependency down"))

    async def quarantine(rec, exc):
        assert not c.commits

    w = worker(c, handler, quarantine=quarantine)
    await w._handle(record(), TopicPartition("test", 0), 0)
    assert handler.await_count == 3
    assert c.commits[0][TopicPartition("test", 0)].offset == 1


@pytest.mark.asyncio
async def test_cancel_does_not_commit():
    c, started = Consumer(), asyncio.Event()

    async def handler(msg):
        started.set()
        await asyncio.Event().wait()

    w = worker(c, handler)
    task = asyncio.create_task(w._handle(record(), TopicPartition("test", 0), 0))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not c.commits


@pytest.mark.asyncio
async def test_quarantine_outage_does_not_ack_or_rerun_handler():
    c, attempted = Consumer(), asyncio.Event()

    async def quarantine(*args):
        attempted.set()
        raise RuntimeError("broker down")

    handler = AsyncMock(side_effect=ValueError("bad response"))
    w = worker(c, handler, quarantine=quarantine, attempts=1)
    task = asyncio.create_task(w._handle(record(), TopicPartition("test", 0), 0))
    await attempted.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert not c.commits
    assert handler.await_count == 1


@pytest.mark.asyncio
async def test_invalid_bytes_quarantined_without_handler():
    c, handler, quarantine = Consumer(), AsyncMock(), AsyncMock()
    w = worker(c, handler, quarantine=quarantine)
    await w._handle(record(value=b"not-json"), TopicPartition("test", 0), 0)
    handler.assert_not_awaited()
    assert isinstance(quarantine.await_args.args[1], InvalidEnvelope)
    assert c.commits


@pytest.mark.asyncio
async def test_parallel_partitions_preserve_per_partition_order():
    c = Consumer([record(0, 0), record(1, 0), record(0, 1)])
    blocked, other_done, release, order = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
        [],
    )

    async def handler(msg):
        order.append((msg.partition, msg.offset))
        if msg.partition == 0 and msg.offset == 0:
            blocked.set()
            await release.wait()
        if msg.partition == 1:
            other_done.set()

    w = worker(c, handler, concurrency=2)
    task = asyncio.create_task(w.run())
    try:
        await asyncio.wait_for(blocked.wait(), 1)
        await asyncio.wait_for(other_done.wait(), 1)
        assert (0, 1) not in order
        release.set()
        for _ in range(1000):
            if c.offsets.get(TopicPartition("test", 0)) == 2:
                break
            await asyncio.sleep(0.001)
        assert c.offsets[TopicPartition("test", 0)] == 2
        assert order.index((0, 0)) < order.index((0, 1))
        assert all(len(commit) == 1 for commit in c.commits)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_revoke_cancels_and_fences_old_commit():
    c, started = Consumer(), asyncio.Event()

    async def handler(msg):
        started.set()
        await asyncio.Event().wait()

    w, tp = worker(c, handler), TopicPartition("test", 0)
    task = asyncio.create_task(w._handle(record(), tp, 0))
    w.tasks[tp] = task
    await started.wait()
    await w.on_partitions_revoked([tp])
    assert task.cancelled()
    assert not c.commits
    await w.on_partitions_assigned([tp])
    assert not w._owns(tp, 0)


@pytest.mark.asyncio
async def test_commit_failure_does_not_repeat_handler_in_same_attempt():
    c, handler = Consumer(), AsyncMock()
    c.commit = AsyncMock(side_effect=CommitFailedError())
    await worker(c, handler)._handle(record(), TopicPartition("test", 0), 0)
    handler.assert_awaited_once()
    c.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocked_quarantine_does_not_occupy_an_execution_slot():
    c = Consumer([record(0, 0), record(0, 1)])
    quarantining, finished = asyncio.Event(), asyncio.Event()

    async def handler(msg):
        if msg.partition == 0:
            raise ValueError("bad output")
        finished.set()

    async def quarantine(*args):
        quarantining.set()
        await asyncio.Event().wait()

    w = worker(c, handler, attempts=1, concurrency=1, quarantine=quarantine)
    task = asyncio.create_task(w.run())
    try:
        await asyncio.wait_for(quarantining.wait(), 2)
        await asyncio.wait_for(finished.wait(), 2)
        assert TopicPartition("test", 0) not in c.offsets
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
