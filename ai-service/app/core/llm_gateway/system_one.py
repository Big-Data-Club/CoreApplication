"""Structured System One call using the gateway's Admin-managed provider keys."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.llm_gateway.errors import NoKeyAvailableError
from app.core.llm_gateway.key_pool import KeyPool
from app.core.llm_gateway.registry import ModelRegistry

logger = logging.getLogger(__name__)
PROVIDER_CODE = "opencode_zen"
ENDPOINT = "https://opencode.ai/zen/v1/systemone"


async def decide_system_one(
    state: str, *, registry: ModelRegistry, key_pool: KeyPool,
) -> dict[str, Any] | None:
    """Return an advisory score, or None if disabled/unavailable/invalid."""
    settings = get_settings()
    if not settings.jev_enabled:
        return None
    prompt = state.strip()[:900]
    if not prompt:
        return None

    try:
        provider = await registry.get_provider_by_code(PROVIDER_CODE)
        if provider is None or not provider.enabled:
            return None
        lease = await key_pool.lease(provider.id)
    except NoKeyAvailableError:
        logger.info("Jev decision unavailable: no active OpenCode Zen key")
        return None
    except Exception as exc:  # Registry/key-store failure must not break chat.
        logger.warning("Jev key lookup failed: %s", type(exc).__name__)
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
                ENDPOINT,
                headers={"Authorization": f"Bearer {lease.plaintext}"},
                json=payload,
            )
        if response.status_code in (401, 403):
            await key_pool.record_auth_failure(lease.id, "System One authentication failed")
            return None
        if response.status_code == 429:
            await key_pool.record_rate_limit(lease.id)
            return None
        response.raise_for_status()
        result = response.json()
        answer = (result.get("answers") or {}).get("decompose") if isinstance(result, dict) else None
        value = answer.get("noul") if isinstance(answer, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            logger.warning("Jev returned an invalid decomposition value")
            await key_pool.record_generic_failure(lease.id, "Invalid System One response")
            return None
        usage = result.get("usage") or {}
        tokens = sum(
            value for value in (usage.get("input_tokens"), usage.get("output_tokens"))
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ) if isinstance(usage, dict) else 0
        await key_pool.record_success(lease.id, tokens)
        return {"score": round(float(value), 3), "model": settings.jev_model}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("Jev decision unavailable: %s", type(exc).__name__)
        try:
            await key_pool.record_generic_failure(lease.id, type(exc).__name__)
        except Exception:
            logger.warning("Jev key health update failed")
        return None
    except Exception as exc:
        logger.warning("Jev decision unavailable: %s", type(exc).__name__)
        return None
