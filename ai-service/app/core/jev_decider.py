"""Optional System One decision client, separate from chat model routing."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_ENDPOINT = "https://opencode.ai/zen/v1/systemone"


def bootstrap_jev_decider() -> bool:
    """Report configuration at startup without making a network call or logging a key."""
    settings = get_settings()
    configured = bool(settings.jev_enabled and settings.opencode_api_key.strip())
    logger.info("Jev decision endpoint %s", "configured" if configured else "disabled")
    return configured


async def decide_decomposition(state: str) -> dict[str, Any] | None:
    """Advise on decomposing a read-only question. None means use local routing."""
    settings = get_settings()
    if not settings.jev_enabled or not settings.opencode_api_key.strip():
        return None
    prompt = state.strip()[:900]
    if not prompt:
        return None
    payload = {
        "model": settings.jev_model,
        "state": prompt,
        "questions": {"decompose": {
            "type": "noul",
            "instructions": (
                "Does this learning question require separate evidence retrieval, "
                "drafting, and factual critique to answer accurately?"
            ),
        }},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.jev_timeout_seconds) as client:
            response = await client.post(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {settings.opencode_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                return None
            answers = result.get("answers")
            if not isinstance(answers, dict):
                return None
            answer = answers.get("decompose")
            if not isinstance(answer, dict):
                return None
            value = answer.get("noul")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
                logger.warning("Jev returned an invalid decomposition value")
                return None
            return {"score": round(float(value), 3), "model": settings.jev_model}
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Jev decision unavailable: %s", type(exc).__name__)
        return None
