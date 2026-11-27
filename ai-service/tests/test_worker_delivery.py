"""Producer lifecycle and rolling-upgrade delivery contracts."""

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.worker import kafka_producer as producer
from app.worker.partition_consumer import PartitionConsumer, InvalidEnvelope


@pytest.mark.asyncio
async def test_concurrent_cold_producer_start_is_single_flight():
    async def start():
        await asyncio.sleep(0.001)

    client = SimpleNamespace(start=AsyncMock(side_effect=start), stop=AsyncMock())
    with patch.object(producer, "_producer", None), patch.object(
        producer, "_producer_lock", asyncio.Lock()
    ), patch.object(producer, "AIOKafkaProducer", return_value=client) as factory:
        results = await asyncio.gather(
            producer.get_kafka_producer(), producer.get_kafka_producer()
        )
        assert results == [client, client]
        factory.assert_called_once()
        client.start.assert_awaited_once()
        assert factory.call_args.kwargs["enable_idempotence"] is True


@pytest.mark.asyncio
async def test_failed_start_does_not_publish_half_initialized_client():
    client = SimpleNamespace(
        start=AsyncMock(side_effect=RuntimeError("unavailable")), stop=AsyncMock()
    )
    with patch.object(producer, "_producer", None), patch.object(
        producer, "_producer_lock", asyncio.Lock()
    ), patch.object(producer, "AIOKafkaProducer", return_value=client):
        with pytest.raises(RuntimeError):
            await producer.get_kafka_producer()
        assert producer._producer is None
        client.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_memory_forward_preserves_identity_and_propagates_failed_ack():
    with patch("app.core.logging_config.configure_logging"):
        from app.worker.kafka_worker import _dispatch_batch
    payload = {
        "job_id": "stable-job",
        "command_type": "CONSOLIDATE_SESSION",
        "payload": {"user_id": 1, "session_id": "session-1", "context": {}},
    }
    client = SimpleNamespace(send_and_wait=AsyncMock())
    with patch.object(producer, "get_kafka_producer", AsyncMock(return_value=client)):
        await _dispatch_batch(SimpleNamespace(topic="lms.ai.command", value=payload))
        assert client.send_and_wait.await_args.args == ("lms.ai.memory.v1",)
        assert client.send_and_wait.await_args.kwargs == {
            "key": b"session-1",
            "value": payload,
        }
        client.send_and_wait.side_effect = RuntimeError("no broker acknowledgement")
        with pytest.raises(RuntimeError):
            await _dispatch_batch(
                SimpleNamespace(topic="lms.ai.command", value=payload)
            )


@pytest.mark.asyncio
async def test_memory_lane_rejects_other_commands_and_future_schema():
    with patch("app.core.logging_config.configure_logging"):
        from app.worker.kafka_worker import _dispatch_memory
    for value in [
        {"job_id": "job", "command_type": "INDEX_QUIZ", "payload": {}},
        {
            "schema_version": 2,
            "job_id": "job",
            "command_type": "CONSOLIDATE_SESSION",
            "payload": {},
        },
    ]:
        with pytest.raises(InvalidEnvelope):
            await _dispatch_memory(
                SimpleNamespace(value=value, topic="lms.ai.memory.v1")
            )


@pytest.mark.asyncio
async def test_quarantine_preserves_original_bytes_and_source_coordinates():
    client = SimpleNamespace(send_and_wait=AsyncMock())
    runner = PartitionConsumer(
        SimpleNamespace(subscribe=Mock()), ["source"], "group", AsyncMock()
    )
    record = SimpleNamespace(
        topic="source",
        partition=2,
        offset=45,
        key=b"private-key",
        value=b"\xff\x00invalid",
    )
    with patch.object(producer, "get_kafka_producer", AsyncMock(return_value=client)):
        await runner._quarantine(record, ValueError("private error content"))
    call = client.send_and_wait.await_args
    assert call.args == ("ai.worker.failed.v1",)
    assert call.kwargs["key"] == b"group:source:2:45"
    envelope = call.kwargs["value"]
    assert base64.b64decode(envelope["payload_base64"]) == record.value
    assert base64.b64decode(envelope["source_key_base64"]) == record.key
    assert envelope["error_type"] == "ValueError"
    assert "private error content" not in str(envelope)
