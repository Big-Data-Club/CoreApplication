"""
ai-service/app/core/llm.py

Thin backwards-compatible façade over app.core.llm_gateway.

All LLM calls in the codebase go through `chat_complete`, `chat_complete_json`
or `chat_complete_structured`. They now route through the multi-provider
gateway (app.core.llm_gateway), picking up:
  * admin-configured fallback chains per task,
  * a shared pool of API keys with cooldowns,
  * usage logging and cost tracking.

Prompt builders and system prompts are unchanged - they live in
`app.core.prompts` now to keep this module focused on call mechanics.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Type, TypeVar

from groq import AsyncGroq
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.llm_gateway import (
    ChatRequest,
    TASK_CHAT,
    TASK_QUIZ_GEN,
    get_gateway,
    reset_gateway,
)

# Re-export embedding API (backward compat)
from app.core.embeddings import ( 
    get_embed_model,
    create_embedding,
    create_passage_embedding,
    create_embeddings_batch,
    create_passage_embeddings_batch,
    warm_up_models,
)

# Re-export prompt builders (moved to prompts.py, kept importable from here)
from app.core.prompts import (             # noqa: F401
    SYSTEM_PROMPT_TUTOR,
    SYSTEM_PROMPT_QUIZ_GEN,
    SYSTEM_PROMPT_FLASHCARD_GEN,
    SYSTEM_PROMPT_CONCEPT_CHECK,
    build_diagnosis_prompt,
    build_quiz_generation_prompt,
    build_flashcard_generation_prompt,
    build_concept_check_prompt,
)

logger = logging.getLogger(__name__)
settings = get_settings()

M = TypeVar("M", bound=BaseModel)


# ── Legacy Groq client (still used by react_loop's streaming tool-calls) ────
# Keeps the env-var path alive so existing streaming code doesn't break. New
# code should prefer `gateway.chat(...)`.
_groq: AsyncGroq | None = None
_instructor_client = None


def get_groq_client() -> AsyncGroq:
    global _groq
    if _groq is None:
        _groq = AsyncGroq(api_key=settings.groq_api_key, max_retries=0)
    return _groq


def get_instructor_client():
    """Instructor wrapper around the env Groq client (structured JSON path)."""
    global _instructor_client
    if _instructor_client is None:
        import instructor
        _instructor_client = instructor.from_groq(
            get_groq_client(), mode=instructor.Mode.JSON,
        )
    return _instructor_client


def reset_async_clients() -> None:
    """
    Reset async clients when entering a new event loop.
    MUST be called at the start of each Celery task before any LLM calls.
    Also resets the gateway singleton so its DB pool references rebind.
    """
    global _groq, _instructor_client
    _groq = None
    _instructor_client = None
    reset_gateway()
    logger.debug("Async clients reset for new event loop")


# ── Primary entrypoints ────────────────────────────────────────────────────

async def chat_complete(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    json_mode: bool = False,
    *,
    task: str = TASK_CHAT,
    request_id: str | None = None,
    **extra: Any,
) -> str:
    """
    Multi-provider chat completion.

    `task` selects the fallback chain (see app.core.llm_gateway.types for
    canonical task codes). `model` is honoured as a soft preference - if the
    name matches a bound model for the task it's tried first, otherwise the
    chain's priority order wins.
    """
    gateway = get_gateway()
    response = await gateway.chat(ChatRequest(
        task=task,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
        model_hint=model,
        request_id=request_id,
        extra=extra or {},
    ))
    return response.content


async def chat_complete_json(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    *,
    task: str = TASK_CHAT,
    request_id: str | None = None,
) -> dict | list:
    """JSON-returning completion with defensive parsing."""
    raw = await chat_complete(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
        task=task,
        request_id=request_id,
    )
    try:
        return _extract_json(raw)
    except ValueError as exc:
        logger.error("JSON parse error: %s\nRaw: %s", exc, raw[:300])
        raise


async def chat_complete_structured(
    messages: list[dict],
    response_model: Type[M],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    max_retries: int = 2,
    *,
    task: str = TASK_QUIZ_GEN,
    request_id: str | None = None,
) -> M:
    """
    Structured-output call that returns a validated Pydantic model.

    Routes through the gateway (full multi-model support) and validates the
    JSON payload. Retries up to `max_retries` with a corrective reminder if
    validation fails.
    """
    schema_hint = _compact_schema_hint(response_model)
    attempts: list[str] = []

    for attempt in range(max_retries + 1):
        local_messages = list(messages)
        if attempts:
            local_messages.append({
                "role": "user",
                "content": (
                    "Your previous response failed JSON schema validation:\n"
                    f"{attempts[-1][:500]}\n\n"
                    f"Return a single valid JSON document matching:\n{schema_hint}"
                ),
            })

        raw = await chat_complete(
            messages=local_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            task=task,
            request_id=request_id,
        )
        try:
            data = _extract_json(raw)
            return response_model.model_validate(data)
        except (ValueError, ValidationError) as exc:
            attempts.append(f"{exc}")
            if attempt == max_retries:
                logger.error(
                    "chat_complete_structured gave up after %d retries: %s",
                    max_retries, exc,
                )
                raise
            await asyncio.sleep(0.2)
    raise RuntimeError("unreachable")   # pragma: no cover


# ── JSON extraction (defensive) ────────────────────────────────────────────
def _extract_json(raw: str) -> dict | list:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    fenced = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    fenced = re.sub(r"\s*```\s*$", "", fenced, flags=re.MULTILINE).strip()
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
    raise ValueError(f"LLM returned non-JSON output:\n{raw[:400]}")


def _compact_schema_hint(model_cls: type[BaseModel]) -> str:
    """Produce a trimmed JSON-schema hint for retry prompts."""
    try:
        schema = model_cls.model_json_schema()
        return json.dumps(
            {"required": schema.get("required", []),
             "properties": list((schema.get("properties") or {}).keys())},
            ensure_ascii=False,
        )
    except Exception:
        return model_cls.__name__