"""Bounded, retryable delivery to LMS's idempotent internal callbacks."""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def post_lms_callback(
    base_url: str,
    secret: str,
    path: str,
    body: dict,
    *,
    required: bool = True,
    client: httpx.AsyncClient | None = None,
    sleep=asyncio.sleep,
) -> bool:
    if not path.startswith("/api/v1/internal/"):
        raise ValueError("LMS callbacks must use an internal path")
    if not secret or secret in {"None", "ai-service-secret-change-me"}:
        raise ValueError("LMS service authentication is not configured")
    if client is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as owned:
            return await post_lms_callback(
                base_url, secret, path, body, required=required, client=owned, sleep=sleep,
            )
    for attempt in range(5):
        try:
            response = await client.post(
                base_url.rstrip("/") + path,
                json=body,
                headers={"X-API-Secret": secret},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
            if not retryable or attempt == 4:
                if required:
                    raise
                logger.warning("LMS progress callback was not delivered: %s", path)
                return False
        except httpx.TransportError:
            if attempt == 4:
                if required:
                    raise
                logger.warning("LMS progress callback was not delivered: %s", path)
                return False
        await sleep(min(0.25 * 2**attempt, 4))
    return False
