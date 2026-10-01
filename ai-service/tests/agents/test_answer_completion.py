"""Regression coverage for streamed answers that hit an output limit."""
from __future__ import annotations

import unittest

from app.agents.core.react_loop import (
    _request_answer_continuation,
    _stream_finish_reason,
)
from app.core.llm_gateway.errors import ContextLengthError
from app.core.llm_gateway.gateway import LLMGateway
from app.core.llm_gateway.types import ChatRequest, TASK_AGENT_FLASH


class FakeGateway:
    def __init__(self, events):
        self.events = events
        self.request = None

    async def stream(self, request):
        self.request = request
        for event in self.events:
            yield event


class AnswerCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_continuation_keeps_task_and_removes_repeated_formula(self):
        previous = "M6 = (A21 − A11) × (B11 + B12)\nM7 = (A12 − A22)"
        gateway = FakeGateway([
            ("M7 = (A12 − A22) × (B21 + B22)\n", None, {"choices": [{"finish_reason": None}]}),
            ("C11 = M1 + M4 − M5 + M7", None, {"choices": [{"finish_reason": "stop"}]}),
        ])
        request = ChatRequest(
            task=TASK_AGENT_FLASH,
            messages=[{"role": "user", "content": "Giải thích Strassen"}],
            max_tokens=1536,
            extra={"tools": [{"type": "function"}]},
        )

        text, reason = await _request_answer_continuation(gateway, request, previous)

        self.assertEqual(text, " × (B21 + B22)\nC11 = M1 + M4 − M5 + M7")
        self.assertEqual(reason, "stop")
        self.assertEqual(gateway.request.task, TASK_AGENT_FLASH)
        self.assertEqual(gateway.request.messages[-2]["content"], previous)
        self.assertEqual(gateway.request.extra, {})

    def test_terminal_reasons_cover_both_stream_formats(self):
        self.assertEqual(_stream_finish_reason({"choices": [{"finish_reason": "length"}]}), "length")
        self.assertEqual(
            _stream_finish_reason({"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}),
            "max_tokens",
        )
        self.assertEqual(
            _stream_finish_reason({"candidates": [{"finishReason": "MAX_TOKENS"}]}),
            "max_tokens",
        )

    def test_chat_budget_preserves_room_for_visible_answer(self):
        request = ChatRequest(
            task=TASK_AGENT_FLASH,
            messages=[{"role": "user", "content": "x" * 1200}],
            max_tokens=1536,
            min_completion_tokens=768,
        )
        with self.assertRaises(ContextLengthError):
            LLMGateway._fit_completion_budget(request, 1000, 1536)
        self.assertGreaterEqual(
            LLMGateway._fit_completion_budget(request, 2000, 1536), 768
        )


if __name__ == "__main__":
    unittest.main()
