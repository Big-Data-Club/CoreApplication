"""Regression tests for bounded, durable post-turn memory work."""
from __future__ import annotations

import unittest
import sys
from types import ModuleType
from unittest.mock import AsyncMock, patch

from app.agents.core.react_loop import _trigger_post_turn_consolidation
from app.agents.memory.compressor import compress_conversation
from app.agents.memory.consolidation_pipeline import consolidate_session_job
from app.core.llm_gateway.token_budget import estimate_messages_tokens


class MemoryConsolidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_interval_publishes_identity_without_raw_chat(self) -> None:
        fake_producer = ModuleType("app.worker.kafka_producer")
        fake_producer.publish_consolidation_request = AsyncMock()
        with (
            patch("app.agents.core.react_loop.mtm.increment_turn_count", new=AsyncMock(return_value=5)),
            patch.dict(sys.modules, {"app.worker.kafka_producer": fake_producer}),
        ):
            await _trigger_post_turn_consolidation(
                "session-1", 42, "mentor", 7, "knowledge_question",
            )
        fake_producer.publish_consolidation_request.assert_awaited_once()
        kwargs = fake_producer.publish_consolidation_request.await_args.kwargs
        self.assertEqual(kwargs["session_id"], "session-1")
        self.assertEqual(kwargs["user_id"], 42)
        self.assertEqual(kwargs["context"]["turn_count"], 5)
        self.assertNotIn("messages", kwargs)

    async def test_long_history_is_compressed_in_bounded_segments(self) -> None:
        compressed = {"key_facts": {"current_topic": "Strassen"}, "memory_items": []}
        with patch("app.agents.memory.compressor.chat_complete_json", new=AsyncMock(return_value=compressed)) as call:
            result = await compress_conversation(
                [{"role": "user", "content": "matrix multiplication " * 700}],
                "mentor", strict=True,
            )
        self.assertGreater(call.await_count, 1)
        for invocation in call.await_args_list:
            self.assertLess(estimate_messages_tokens(invocation.kwargs["messages"]), 2700)
        self.assertEqual(result["key_facts"]["current_topic"], "Strassen")

    async def test_strict_failure_does_not_advance_worker_cursor(self) -> None:
        with patch("app.agents.memory.compressor.chat_complete_json", new=AsyncMock(side_effect=RuntimeError("gateway down"))):
            with self.assertRaises(RuntimeError):
                await compress_conversation(
                    [{"role": "user", "content": "Need help with arrays"}],
                    "mentor", strict=True,
                )

    async def test_worker_advances_cursor_only_after_bounded_compression(self) -> None:
        messages = [
            {"id": 11, "role": "user", "content": "Strassen?"},
            {"id": 12, "role": "assistant", "content": "Seven products."},
        ]
        new_ctx = {"key_facts": {"current_topic": "Strassen"}}
        with (
            patch("app.agents.memory.consolidation_pipeline.mtm.get_context", new=AsyncMock(return_value={"_last_consolidated_message_id": 10})),
            patch("app.agents.memory.consolidation_pipeline.message_store.get_unconsolidated", new=AsyncMock(return_value=messages)) as fetch,
            patch("app.agents.memory.consolidation_pipeline.compress_conversation", new=AsyncMock(return_value=new_ctx)) as compress,
            patch("app.agents.memory.consolidation_pipeline.ltm.store_episode", new=AsyncMock(return_value="episode-1")) as episode,
            patch("app.agents.memory.consolidation_pipeline.mtm.save_compressed", new=AsyncMock()) as save,
            patch("app.agents.memory.consolidation_pipeline.stm.trim_to_recent", new=AsyncMock()) as trim,
        ):
            result = await consolidate_session_job({
                "session_id": "session-1", "user_id": 42,
                "context": {"agent_type": "mentor", "turn_count": 5},
            })
        fetch.assert_awaited_once_with("session-1", 42, 10, limit=100)
        self.assertTrue(compress.await_args.kwargs["strict"])
        self.assertEqual(save.await_args.args[1]["_last_consolidated_message_id"], 12)
        self.assertEqual(episode.await_args.kwargs["idempotency_key"], "session-1:10:12")
        trim.assert_awaited_once_with("session-1", keep_last=6)
        self.assertEqual(result["cursor"], 12)

    async def test_worker_does_not_trim_when_compression_fails(self) -> None:
        with (
            patch("app.agents.memory.consolidation_pipeline.mtm.get_context", new=AsyncMock(return_value={})),
            patch("app.agents.memory.consolidation_pipeline.message_store.get_unconsolidated", new=AsyncMock(return_value=[{"id": 1, "role": "user", "content": "x"}])),
            patch("app.agents.memory.consolidation_pipeline.compress_conversation", new=AsyncMock(side_effect=RuntimeError("gateway down"))),
            patch("app.agents.memory.consolidation_pipeline.mtm.save_compressed", new=AsyncMock()) as save,
            patch("app.agents.memory.consolidation_pipeline.stm.trim_to_recent", new=AsyncMock()) as trim,
        ):
            with self.assertRaises(RuntimeError):
                await consolidate_session_job({"session_id": "session-1", "user_id": 42})
        save.assert_not_awaited()
        trim.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
