"""Regression tests for real SSE streaming from compatible providers."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.llm_gateway.adapters.openai_compat_adapter import OpenAICompatAdapter
from app.core.llm_gateway.types import Model


class _FakeResponse:
    status_code = 200

    def __init__(self, lines: list[str], *, headers: dict[str, str] | None = None, body: bytes = b""):
        self._lines = lines
        self.headers = headers or {}
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return self._body


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self.response = response
        self.calls: list[tuple[tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


def _model() -> Model:
    return Model(
        id=1,
        provider_id=1,
        provider_code="compatible",
        adapter_type="openai_compat",
        base_url="https://llm.example/v1",
        model_name="fast-model",
        display_name="Fast model",
        family=None,
        context_window=8192,
        supports_json=True,
        supports_tools=True,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_1k=0,
        output_cost_per_1k=0,
        default_temperature=0.2,
        default_max_tokens=512,
        enabled=True,
        config={},
    )


class OpenAICompatStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_relays_text_tool_and_usage_chunks_without_buffering(self):
        response = _FakeResponse([
            ": keepalive",
            'data: {"model":"fast-model","choices":[{"delta":{"content":"Xin "}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"search","arguments":"{\\\"q\\\":\\\""}}]}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"oop\\\"}"}}]}}],"usage":{"prompt_tokens":12,"completion_tokens":3,"total_tokens":15}}',
            "data: [DONE]",
        ])
        client = _FakeClient(response)
        adapter = OpenAICompatAdapter(api_key="secret", base_url="https://llm.example/v1")

        with patch(
            "app.core.llm_gateway.adapters.openai_compat_adapter.httpx.AsyncClient",
            return_value=client,
        ):
            chunks = [
                chunk async for chunk in adapter.stream(
                    model=_model(),
                    messages=[{"role": "user", "content": "Explain OOP"}],
                    temperature=0.2,
                    max_tokens=512,
                    json_mode=False,
                    extra={"tools": [{"type": "function"}], "tool_choice": "auto"},
                )
            ]

        self.assertEqual(chunks[0][0], "Xin ")
        self.assertEqual(chunks[1][2]["choices"][0]["delta"]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(chunks[2][1].total_tokens, 15)
        self.assertEqual(len(client.calls), 1)
        _, kwargs = client.calls[0]
        self.assertTrue(kwargs["json"]["stream"])
        self.assertEqual(kwargs["json"]["tools"], [{"type": "function"}])

    async def test_falls_back_when_a_compatible_gateway_returns_json(self):
        response = _FakeResponse(
            [],
            headers={"content-type": "application/json"},
            body=(
                b'{"choices":[{"message":{"content":"Complete response"}}],'
                b'"usage":{"prompt_tokens":7,"completion_tokens":2,"total_tokens":9}}'
            ),
        )
        client = _FakeClient(response)
        adapter = OpenAICompatAdapter(api_key="secret", base_url="https://llm.example/v1")

        with patch(
            "app.core.llm_gateway.adapters.openai_compat_adapter.httpx.AsyncClient",
            return_value=client,
        ):
            chunks = [
                chunk async for chunk in adapter.stream(
                    model=_model(),
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.2,
                    max_tokens=512,
                    json_mode=False,
                    extra={},
                )
            ]

        self.assertEqual(chunks[0][0], "Complete response")
        self.assertEqual(chunks[0][1].total_tokens, 9)
