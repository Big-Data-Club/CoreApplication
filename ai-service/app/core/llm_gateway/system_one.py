"""Structured System One call using the gateway's Admin-managed provider keys."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.core.llm_gateway.errors import NoKeyAvailableError
from app.core.llm_gateway.key_pool import KeyPool
from app.core.llm_gateway.registry import ModelRegistry
from app.core.llm_gateway.usage import record_usage

logger = logging.getLogger(__name__)
PROVIDER_CODE = "opencode_zen"


def _system_one_url(base_url: str | None) -> str | None:
    """Build the structured endpoint from the Admin-managed provider URL."""
    if not base_url:
        return None
    parsed = urlsplit(base_url.strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        return None
    return base_url.strip().rstrip("/") + "/systemone"


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
        endpoint = _system_one_url(provider.base_url)
        if endpoint is None:
            logger.warning("Jev provider has no valid HTTPS base URL")
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
    started = time.monotonic()

    async def log_attempt(*, success: bool, error_code: str | None = None,
                          input_tokens: int = 0, output_tokens: int = 0) -> None:
        await record_usage(
            task_code="jev_decision", model=None, api_key_id=lease.id,
            provider_code=PROVIDER_CODE, model_name=settings.jev_model,
            prompt_tokens=input_tokens, completion_tokens=output_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
            success=success, fallback_used=False, attempt_no=1,
            error_code=error_code,
        )

    try:
        async with httpx.AsyncClient(timeout=settings.jev_timeout_seconds) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {lease.plaintext}"},
                json=payload,
            )
        if response.status_code in (401, 403):
            await key_pool.record_auth_failure(lease.id, "System One authentication failed")
            await log_attempt(success=False, error_code="auth")
            return None
        if response.status_code == 429:
            await key_pool.record_rate_limit(lease.id)
            await log_attempt(success=False, error_code="rate_limited")
            return None
        response.raise_for_status()
        result = response.json()
        answer = (result.get("answers") or {}).get("decompose") if isinstance(result, dict) else None
        value = answer.get("noul") if isinstance(answer, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            logger.warning("Jev returned an invalid decomposition value")
            await key_pool.record_generic_failure(lease.id, "Invalid System One response")
            await log_attempt(success=False, error_code="invalid_response")
            return None
        usage = result.get("usage") or {}
        input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0
        input_tokens = int(input_tokens) if isinstance(input_tokens, (int, float)) and not isinstance(input_tokens, bool) else 0
        output_tokens = int(output_tokens) if isinstance(output_tokens, (int, float)) and not isinstance(output_tokens, bool) else 0
        await key_pool.record_success(lease.id, input_tokens + output_tokens)
        await log_attempt(success=True, input_tokens=input_tokens, output_tokens=output_tokens)
        return {"score": round(float(value), 3), "model": settings.jev_model}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("Jev decision unavailable: %s", type(exc).__name__)
        try:
            await key_pool.record_generic_failure(lease.id, type(exc).__name__)
        except Exception:
            logger.warning("Jev key health update failed")
        await log_attempt(success=False, error_code=type(exc).__name__)
        return None
    except Exception as exc:
        logger.warning("Jev decision unavailable: %s", type(exc).__name__)
        return None
