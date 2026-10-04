"""System One task execution through gateway bindings, providers, and key pool."""

from __future__ import annotations

import logging
import math
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.core.llm_gateway.errors import NoKeyAvailableError
from app.core.llm_gateway.key_pool import KeyPool, LeasedKey
from app.core.llm_gateway.registry import ModelRegistry
from app.core.llm_gateway.types import Model, TASK_JEV_DECISION
from app.core.llm_gateway.usage import record_usage

logger = logging.getLogger(__name__)
MAX_KEYS_PER_MODEL = 3


def _system_one_url(base_url: str | None, path: str = "systemone") -> str | None:
    """Build a safe HTTPS endpoint from the selected provider/model settings."""
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    parsed = urlsplit(base_url.strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        return None
    if (not isinstance(path, str) or not path or path.startswith("/")
            or ".." in path or "?" in path or "#" in path or "\\" in path):
        return None
    return base_url.strip().rstrip("/") + "/" + path


async def _attempt(
    *, prompt: str, model: Model, endpoint: str, lease: LeasedKey,
    key_pool: KeyPool, timeout: float, attempt_no: int, fallback_used: bool,
    questions: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Run one key attempt; tell the caller whether another key may help."""
    started = time.monotonic()

    async def log_attempt(*, success: bool, error_code: str | None = None,
                          input_tokens: int = 0, output_tokens: int = 0) -> None:
        await record_usage(
            task_code=TASK_JEV_DECISION, model=model, api_key_id=lease.id,
            prompt_tokens=input_tokens, completion_tokens=output_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
            success=success, fallback_used=fallback_used,
            attempt_no=attempt_no, error_code=error_code,
        )

    payload = {
        "model": model.model_name,
        "state": prompt,
        "questions": {"decompose": {
            "type": "noul",
            "instructions": (
                "Does this learning question require separate evidence retrieval, "
                "drafting, and factual critique to answer accurately?"
            ),
        }},
    }
    if questions is not None:
        payload["questions"] = {
            name: {"type": "noul", "instructions": instruction}
            for name, instruction in questions.items()
        }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {lease.plaintext}"},
                json=payload,
            )
        if response.status_code in (401, 403):
            await key_pool.record_auth_failure(lease.id, "System One authentication failed")
            await log_attempt(success=False, error_code="auth")
            return "next_key", None
        if response.status_code == 429:
            await key_pool.record_rate_limit(lease.id)
            await log_attempt(success=False, error_code="rate_limited")
            return "next_key", None
        response.raise_for_status()
        result = response.json()
        answers = result.get("answers") if isinstance(result, dict) else None
        scores = {}
        for name in payload["questions"]:
            answer = answers.get(name) if isinstance(answers, dict) else None
            value = answer.get("noul") if isinstance(answer, dict) else None
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 1):
                break
            scores[name] = float(value)
        if len(scores) != len(payload["questions"]):
            await key_pool.record_generic_failure(lease.id, "Invalid System One response")
            await log_attempt(success=False, error_code="invalid_response")
            return "next_model", None
        usage = result.get("usage") or {}
        input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0
        input_tokens = int(input_tokens) if isinstance(input_tokens, (int, float)) and not isinstance(input_tokens, bool) else 0
        output_tokens = int(output_tokens) if isinstance(output_tokens, (int, float)) and not isinstance(output_tokens, bool) else 0
        await key_pool.record_success(lease.id, input_tokens + output_tokens)
        await log_attempt(success=True, input_tokens=input_tokens, output_tokens=output_tokens)
        return "success", {
            **({"scores": scores} if questions is not None else
               {"score": round(scores["decompose"], 3)}),
            "model": model.model_name,
            "provider": model.provider_code,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "fallback_used": fallback_used, "attempt_no": attempt_no,
        }
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("System One model %s failed: %s", model.model_name, type(exc).__name__)
        try:
            await key_pool.record_generic_failure(lease.id, type(exc).__name__)
        except Exception:
            logger.warning("System One key health update failed")
        await log_attempt(success=False, error_code=type(exc).__name__)
        return "next_model", None


async def decide_system_one(
    state: str, *, registry: ModelRegistry, key_pool: KeyPool,
    questions: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Resolve the live Jev task chain and fall back locally if none succeeds."""
    settings = get_settings()
    if not settings.jev_enabled:
        return None
    # Custom decisions must see the complete bounded state; truncation can
    # remove a negation/action at the end and change the routing decision.
    if questions is not None and (
        not 1 <= len(questions) <= 8 or len(state) > 4000
        or any(not isinstance(k, str) or not k.isidentifier()
               or not isinstance(v, str) or not v.strip() or len(v) > 2000
               for k, v in questions.items())
    ):
        return None
    prompt = state.strip() if questions is not None else state.strip()[:900]
    if not prompt:
        return None

    try:
        chain = await registry.get_binding_chain(TASK_JEV_DECISION)
    except Exception as exc:
        logger.warning("System One task lookup failed: %s", type(exc).__name__)
        return None

    for index, binding in enumerate(chain):
        model = binding.model
        if model.config.get("api_protocol") != "system_one":
            logger.warning("Skipping non-System-One model bound to %s: %s",
                           TASK_JEV_DECISION, model.model_name)
            continue
        try:
            provider = await registry.get_provider(model.provider_id)
            if provider is None or not provider.enabled:
                continue
            endpoint = _system_one_url(
                provider.base_url, model.config.get("endpoint_path", "systemone")
            )
            if endpoint is None:
                logger.warning("System One provider %s has no valid HTTPS endpoint",
                               model.provider_code)
                continue
            excluded: set[int] = set()
            for key_attempt in range(MAX_KEYS_PER_MODEL):
                try:
                    lease = await key_pool.lease(provider.id, exclude_ids=excluded.copy())
                except NoKeyAvailableError:
                    break
                excluded.add(lease.id)
                outcome, decision = await _attempt(
                    prompt=prompt, model=model, endpoint=endpoint, lease=lease,
                    key_pool=key_pool, timeout=settings.jev_timeout_seconds,
                    attempt_no=key_attempt + 1, fallback_used=index > 0,
                    questions=questions,
                )
                if outcome == "success":
                    return decision
                if outcome != "next_key":
                    break
        except Exception as exc:  # Decision service must never block chat.
            logger.warning("System One binding failed: %s", type(exc).__name__)
    return None
