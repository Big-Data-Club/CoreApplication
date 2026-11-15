import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.lms_callbacks import post_lms_callback


def test_callback_retries_same_payload_then_succeeds():
    async def run():
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(503 if len(calls) == 1 else 200)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await post_lms_callback(
                "http://lms.test", "fixture-secret", "/api/v1/internal/micro-lessons/lessons",
                {"job_id": 7, "lessons": []}, client=client, sleep=AsyncMock(),
            )
        assert result and len(calls) == 2
        assert calls[0].content == calls[1].content
        assert calls[1].headers["X-API-Secret"] == "fixture-secret"
    asyncio.run(run())


def test_result_callback_does_not_swallow_permanent_failure():
    async def run():
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(403)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await post_lms_callback("http://lms.test", "fixture-secret", "/api/v1/internal/micro-quizzes/quizzes", {}, client=client)
        assert len(calls) == 1
    asyncio.run(run())


def test_progress_failure_is_bounded_and_noncritical():
    async def run():
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(503)
        sleep = AsyncMock()
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await post_lms_callback("http://lms.test", "fixture-secret", "/api/v1/internal/micro-lessons/status", {}, required=False, client=client, sleep=sleep)
        assert result is False and len(calls) == 5 and sleep.await_count == 4
    asyncio.run(run())
