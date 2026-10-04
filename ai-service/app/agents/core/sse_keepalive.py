"""Keep SSE connections active while the agent awaits a model or tool."""
import asyncio
from collections.abc import AsyncGenerator


async def with_keepalive(source: AsyncGenerator[str, None], interval: float = 15.0):
    pending = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(source))
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield ": keepalive\n\n"
                continue
            try:
                value = pending.result()
            except StopAsyncIteration:
                break
            pending = None
            yield value
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await source.aclose()
