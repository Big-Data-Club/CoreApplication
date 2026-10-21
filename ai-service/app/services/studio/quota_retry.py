"""Bounded worker-only pacing after the gateway exhausts its key rotation."""
from __future__ import annotations

import asyncio

from app.core.llm_gateway.errors import RateLimitedError


async def authoring_call(call):
    from app.services.studio.jobs import active_lease
    for attempt in range(3):
        try:
            return await call()
        except RateLimitedError as exc:
            # HTTP callers never wait here. Long/daily exhaustion must surface
            # instead of keeping a worker occupied for hours.
            delay = exc.retry_after if exc.retry_after is not None else 30 * (attempt + 1)
            if not active_lease.get() or attempt == 2 or delay > 120:
                raise
            await asyncio.sleep(max(1, delay))
