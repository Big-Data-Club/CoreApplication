"""Agent prompt packing against a selected gateway model/key envelope."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agents.core.prompt_budget import pack_agent_messages
from app.agents.core.prompts import build_compact_system_prompt, build_system_prompt
from app.agents.memory.active_courses import format_active_courses_for_prompt
from app.agents.tools.registry import get_tool_schemas
from app.core.llm_gateway.errors import ContextLengthError, RateLimitedError
from app.core.llm_gateway.gateway import LLMGateway
from app.core.llm_gateway.token_budget import estimate_request_tokens
from app.core.llm_gateway.types import ChatRequest, Model, TaskBinding, Usage, TASK_AGENT_REACT


def _model(context_window: int) -> Model:
    return Model(
        id=1, provider_id=1, provider_code="test", adapter_type="openai",
        base_url=None, model_name="test-model", display_name=None, family=None,
        context_window=context_window, supports_json=True, supports_tools=True,
        supports_streaming=True, supports_vision=False, input_cost_per_1k=0,
        output_cost_per_1k=0, default_temperature=0.3,
        default_max_tokens=1024, enabled=True, config={},
    )


class PromptBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = json.dumps({
            "data": {"chunks": [
                {"id": f"chunk-{i}", "text": "Evidence " * 500}
                for i in range(8)
            ]}
        })
        self.messages = [
            {"role": "system", "content": "Teach precisely."},
            {"role": "user", "content": "old question " * 200},
            {"role": "assistant", "content": "old answer " * 200},
            {"role": "user", "content": "Explain Strassen."},
            {"role": "assistant", "tool_calls": [{
                "id": "call_1", "type": "function", "function": {
                    "name": "search_course_materials", "arguments": "{}",
                },
            }]},
            {"role": "tool", "tool_call_id": "call_1", "content": self.evidence},
        ]
        self.extra = {"tools": [{"type": "function", "function": {
            "name": "search_course_materials", "description": "Search lessons",
        }}]}

    def test_small_key_packs_history_and_evidence_without_breaking_tool_protocol(self) -> None:
        packed = pack_agent_messages(self.messages, self.extra, 1150)
        self.assertLessEqual(estimate_request_tokens(packed, self.extra), 1150)
        self.assertEqual(packed[0], self.messages[0])
        self.assertIn("Explain Strassen.", [m.get("content") for m in packed])
        self.assertEqual(packed[-2]["tool_calls"][0]["id"], packed[-1]["tool_call_id"])
        self.assertNotIn("old question " * 200, [m.get("content") for m in packed])
        self.assertIn("_evidence_notice", packed[-1]["content"])
        self.assertEqual(self.messages[-1]["content"], self.evidence)

    def test_schema_trimming_preserves_previously_called_tool(self) -> None:
        called = {"type": "function", "function": {
            "name": "search_course_materials", "description": "Search",
        }}
        unused = {"type": "function", "function": {
            "name": "unused", "description": "Large unused schema " * 200,
        }}
        messages = self.messages[-3:]
        messages[-1] = {**messages[-1], "content": "Evidence"}
        extra = {"tools": [unused, called], "tool_choice": "auto"}
        packed = pack_agent_messages(messages, extra, 500)
        self.assertEqual(extra["tools"], [called])
        self.assertEqual(packed[-2]["tool_calls"][0]["id"], packed[-1]["tool_call_id"])

    def test_oversized_called_schema_fails_instead_of_sending_invalid_protocol(self) -> None:
        extra = {"tools": [{"type": "function", "function": {
            "name": "search_course_materials", "description": "Large schema " * 1000,
        }}]}
        with self.assertRaises(ContextLengthError):
            pack_agent_messages(self.messages, extra, 500)
        self.assertEqual(len(extra["tools"]), 1)

    def test_large_key_keeps_all_input(self) -> None:
        packed = pack_agent_messages(self.messages, self.extra, 30000)
        self.assertEqual(packed, self.messages)

    def test_mandatory_input_reports_context_error(self) -> None:
        with self.assertRaises(ContextLengthError):
            pack_agent_messages(self.messages, self.extra, 40)

    def test_real_mentor_prompt_and_tools_fit_low_tpm_tier(self) -> None:
        question = "Có bao nhiêu cách scheduling trong một hệ HPC-QC? Giải thích chi tiết."
        page = {"courseId": 7, "contentId": 22, "contentTitle": "Hybrid scheduling",
                "contentBody": "Lesson content " * 1000}
        full = build_system_prompt("mentor", "", page_context=page)
        compact = build_compact_system_prompt("mentor", page_context=page)
        messages = [{"role": "system", "content": full},
                    {"role": "user", "content": question}]
        tools = {"tools": get_tool_schemas("mentor"), "tool_choice": "auto"}
        self.assertGreater(estimate_request_tokens(messages, tools), 4976)
        packed = pack_agent_messages(
            messages, tools, 4976, compact_system_prompt=compact,
        )
        self.assertLessEqual(estimate_request_tokens(packed, tools), 4976)
        self.assertEqual(packed[-1]["content"], question)
        self.assertIn("Virtual Mentor", packed[0]["content"])
        self.assertIn("retrieve scoped material", packed[0]["content"])

    def test_gateway_keeps_original_tool_catalogue_for_larger_key_retry(self) -> None:
        full = build_system_prompt("teacher", "")
        compact = build_compact_system_prompt("teacher")
        original_tools = get_tool_schemas("teacher")
        request = ChatRequest(
            task=TASK_AGENT_REACT,
            messages=[{"role": "system", "content": full},
                      {"role": "user", "content": "How do I schedule HPC-QC jobs?"}],
            extra={"tools": original_tools, "tool_choice": "auto"},
            min_completion_tokens=1024,
            message_packer=lambda messages, extra, limit: pack_agent_messages(
                messages, extra, limit, compact_system_prompt=compact,
            ),
        )
        gateway = LLMGateway()
        prepared, output_tokens = gateway._prepare_request(
            request, _model(20000), 2048, key_tpm_limit=8000,
        )
        self.assertLess(len(prepared.extra.get("tools", [])), len(original_tools))
        self.assertEqual(len(request.extra["tools"]), len(original_tools))
        self.assertLessEqual(
            estimate_request_tokens(prepared.messages, prepared.extra) + output_tokens,
            6000,
        )

    def test_gateway_rechecks_actual_key_tpm_and_reserves_completion(self) -> None:
        request = ChatRequest(
            task=TASK_AGENT_REACT, messages=self.messages, extra=self.extra,
            min_completion_tokens=384, max_tokens=1024,
            message_packer=pack_agent_messages,
        )
        gateway = LLMGateway()
        prepared, output_tokens = gateway._prepare_request(
            request, _model(20000), 1024, key_tpm_limit=4000,
        )
        self.assertIsNone(prepared.message_packer)
        self.assertLessEqual(
            estimate_request_tokens(prepared.messages, prepared.extra) + output_tokens,
            3000,
        )
        self.assertEqual(request.messages[-1]["content"], self.evidence)

    def test_course_catalogue_marks_entries_deferred_by_small_budget(self) -> None:
        anchor = {"agent_type": "teacher", "courses": [
            {"id": index, "title": f"Course {index}", "nodes": [
                {"id": index * 100 + node, "name": "Algebra concept " * 20}
                for node in range(10)
            ]}
            for index in range(1, 12)
        ]}
        small = format_active_courses_for_prompt(anchor, max_tokens=200)
        large = format_active_courses_for_prompt(anchor, max_tokens=10000)
        self.assertIn("omitted", small)
        self.assertIn("course_id=11", large)
        self.assertLess(len(small), len(large))


class StreamFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_preflight_tries_another_key_on_same_model(self) -> None:
        gateway = LLMGateway()
        binding = TaskBinding(1, TASK_AGENT_REACT, _model(20000), 1, None, None, False, False, True)

        class Pool:
            def __init__(self):
                self.exclusions = []

            async def lease(self, provider_id, exclude_ids=None):
                self.exclusions.append(set(exclude_ids or ()))
                key_id = 2 if exclude_ids else 1
                return SimpleNamespace(
                    id=key_id, plaintext="test", record=SimpleNamespace(
                        tpm_limit=4000 if key_id == 2 else 500,
                    ),
                )

            async def record_success(self, *args, **kwargs):
                return None

        class Adapter:
            def __init__(self, **kwargs):
                pass

            async def chat(self, **kwargs):
                return "answer", Usage(), {}

        pool = Pool()
        gateway.key_pool = pool
        request = ChatRequest(
            task=TASK_AGENT_REACT,
            messages=[{"role": "system", "content": "x" * 1500},
                      {"role": "user", "content": "question"}],
            min_completion_tokens=384, max_tokens=512,
            message_packer=pack_agent_messages,
        )
        with (
            patch("app.core.llm_gateway.gateway.get_adapter_class", return_value=Adapter),
            patch.object(gateway, "_log", new=AsyncMock()),
        ):
            response = await gateway._call_binding(
                binding=binding, req=request, attempt_no=1, fallback_used=False,
            )
        self.assertEqual(response.content, "answer")
        self.assertEqual(response.api_key_id, 2)
        self.assertEqual(pool.exclusions, [set(), {1}])

    async def test_partial_stream_error_does_not_restart_on_fallback_model(self) -> None:
        gateway = LLMGateway()
        first = TaskBinding(1, TASK_AGENT_REACT, _model(8000), 1, None, None, False, False, True)
        second = TaskBinding(2, TASK_AGENT_REACT, _model(16000), 2, None, None, False, False, True)
        calls = []

        async def fake_binding(*, binding, **kwargs):
            calls.append(binding.id)
            yield "partial", None, {}
            raise RateLimitedError("limit")

        with (
            patch.object(gateway, "_resolve_chain", new=AsyncMock(return_value=[first, second])),
            patch.object(gateway, "_stream_binding", new=fake_binding),
        ):
            with self.assertRaises(RateLimitedError):
                [event async for event in gateway.stream(ChatRequest(task=TASK_AGENT_REACT, messages=[]))]
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
