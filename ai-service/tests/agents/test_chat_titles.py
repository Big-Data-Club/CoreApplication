"""Title delivery must survive failures of the auxiliary model."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.core.react_loop import _maybe_emit_title_update


@pytest.mark.parametrize("response,error", [
    ("Sorting algorithms", None),
    ("", None),
    (None, RuntimeError("provider unavailable")),
    (None, asyncio.TimeoutError()),
])
def test_title_generated_or_fallback_is_saved_and_emitted(response, error):
    async def run():
        with (
            patch("app.agents.core.react_loop.mtm.get_title", new=AsyncMock(return_value=None)),
            patch("app.agents.core.react_loop.mtm.update_title", new=AsyncMock()) as save,
            patch("app.core.llm.chat_complete", new=AsyncMock(return_value=response, side_effect=error)),
        ):
            events = [e async for e in _maybe_emit_title_update("s1", "Explain   quicksort", "t1")]
        expected = response or "Explain quicksort"
        save.assert_awaited_once_with("s1", expected)
        assert len(events) == 1
        assert events[0].type.value == "title_update"
        assert events[0].data["title"] == expected
    asyncio.run(run())


def test_existing_title_is_preserved_without_model_call():
    async def run():
        with (
            patch("app.agents.core.react_loop.mtm.get_title", new=AsyncMock(return_value="My title")),
            patch("app.agents.core.react_loop.mtm.update_title", new=AsyncMock()) as save,
            patch("app.core.llm.chat_complete", new=AsyncMock()) as model,
        ):
            assert [e async for e in _maybe_emit_title_update("s1", "hello", "t1")] == []
        save.assert_not_awaited()
        model.assert_not_awaited()
    asyncio.run(run())
