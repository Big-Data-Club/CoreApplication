"""
Bootstrap - called once on application startup to guarantee that:
 
  1. The default Groq provider exists (idempotent).
  2. The two legacy models (chat + quiz) are registered with their current
     env-var values so callers that upgrade mid-flight still work.
  3. If GROQ_API_KEY is set, it's migrated into llm_api_keys as alias
     'groq-env' - but only if no key for that provider exists yet.
  4. Default task bindings are created so every known task_code resolves to
     at least one model.
 
This preserves current behaviour for existing deployments while switching
the runtime to the new gateway.
"""
from __future__ import annotations
 
import logging
 
from app.core.config import get_settings
from app.core.llm_gateway.registry import get_registry
from app.core.llm_gateway.types import (
    ALL_TASK_CODES,
    TASK_AGENT_REACT,
    TASK_AGENT_ROUTER,
    TASK_CHAT,
    TASK_CLARIFICATION,
    TASK_DIAGNOSIS,
    TASK_FLASHCARD_GEN,
    TASK_GRAPH_LINK,
    TASK_LANGUAGE_DETECT,
    TASK_MEMORY_COMPRESS,
    TASK_NODE_EXTRACT,
    TASK_QUIZ_GEN,
    TASK_MICRO_LESSON_GEN,
    TASK_VLM_DESCRIBE,
    TASK_SECTION_OVERVIEW_GEN,
)
 
logger = logging.getLogger(__name__)
 
 
# Model catalog based on GroqCloud production models (April 2026).
# All entries are upserted on every startup - safe to add/update freely.
# Admins assign task bindings via the Admin UI; bootstrap only seeds the catalog.
_DEFAULT_GROQ_MODELS = [
    # ── Llama family ─────────────────────────────────────────────────────────
    {
        "model_name": "llama-3.1-8b-instant",
        "display_name": "Llama 3.1 8B Instant",
        "family": "llama",
        "context_window": 131072,
        "supports_tools": True,
        "default_temperature": 0.3,
        "default_max_tokens": 8192,
        "input_cost_per_1k": 0.00005,
        "output_cost_per_1k": 0.00008,
    },
    {
        "model_name": "llama-3.3-70b-versatile",
        "display_name": "Llama 3.3 70B Versatile",
        "family": "llama",
        "context_window": 131072,
        "supports_tools": True,
        "default_temperature": 0.3,
        "default_max_tokens": 32768,
        "input_cost_per_1k": 0.00059,
        "output_cost_per_1k": 0.00079,
    },
    # ── OpenAI GPT-OSS (hosted on Groq) ──────────────────────────────────────
    {
        "model_name": "openai/gpt-oss-120b",
        "display_name": "OpenAI GPT-OSS 120B",
        "family": "gpt-oss",
        "context_window": 131072,
        "supports_tools": True,
        "supports_json": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.00015,
        "output_cost_per_1k": 0.00060,
    },
    {
        "model_name": "openai/gpt-oss-20b",
        "display_name": "OpenAI GPT-OSS 20B",
        "family": "gpt-oss",
        "context_window": 131072,
        "supports_tools": True,
        "supports_json": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.000075,
        "output_cost_per_1k": 0.00030,
    },
    # ── Groq Compound Systems ─────────────────────────────────────────────────
    {
        "model_name": "groq/compound",
        "display_name": "Groq Compound",
        "family": "compound",
        "context_window": 131072,
        "supports_tools": True,   # has built-in web search + code execution
        "supports_json": True,
        "default_temperature": 0.3,
        "default_max_tokens": 8192,
        "input_cost_per_1k": 0.0,   # billed differently - no per-token price
        "output_cost_per_1k": 0.0,
    },
    {
        "model_name": "groq/compound-mini",
        "display_name": "Groq Compound Mini",
        "family": "compound",
        "context_window": 131072,
        "supports_tools": True,
        "supports_json": True,
        "default_temperature": 0.3,
        "default_max_tokens": 8192,
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
    },
]


# ── Google Gemini text-generation models (April 2026) ────────────────────────
# Only models useful for LMS text tasks are included.
# TTS, image-gen, video, audio-only, embedding, and robotics models are excluded.
_DEFAULT_GEMINI_MODELS = [
    # ── Gemini 3.x family ─────────────────────────────────────────────────────
    {
        "model_name": "gemini-3.1-pro-preview",
        "display_name": "Gemini 3.1 Pro Preview",
        "family": "gemini-3",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.002,
        "output_cost_per_1k": 0.012,
    },
    {
        "model_name": "gemini-3.1-flash-lite-preview",
        "display_name": "Gemini 3.1 Flash-Lite Preview",
        "family": "gemini-3",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.00025,
        "output_cost_per_1k": 0.0015,
    },
    {
        "model_name": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash Preview",
        "family": "gemini-3",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.0005,
        "output_cost_per_1k": 0.003,
    },
    # ── Gemini 2.5 family ─────────────────────────────────────────────────────
    {
        "model_name": "gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "family": "gemini-2.5",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.00125,
        "output_cost_per_1k": 0.010,
    },
    {
        "model_name": "gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "family": "gemini-2.5",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.0003,
        "output_cost_per_1k": 0.0025,
    },
    {
        "model_name": "gemini-2.5-flash-lite",
        "display_name": "Gemini 2.5 Flash-Lite",
        "family": "gemini-2.5",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 65536,
        "input_cost_per_1k": 0.0001,
        "output_cost_per_1k": 0.0004,
    },
    # ── Gemini 2.0 (deprecated June 2026 - kept for existing bindings) ────────
    {
        "model_name": "gemini-2.0-flash",
        "display_name": "Gemini 2.0 Flash (deprecated)",
        "family": "gemini-2.0",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 8192,
        "input_cost_per_1k": 0.0001,
        "output_cost_per_1k": 0.0004,
    },
]
# ── Anthropic Claude models (April 2026) ──────────────────────────────────────
_DEFAULT_CLAUDE_MODELS = [
    {
        "model_name": "claude-4.7-opus-latest",
        "display_name": "Claude Opus 4.7",
        "family": "claude-4",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 128000,
        "input_cost_per_1k": 0.005,
        "output_cost_per_1k": 0.025,
    },
    {
        "model_name": "claude-4.6-sonnet-latest",
        "display_name": "Claude Sonnet 4.6",
        "family": "claude-4",
        "context_window": 1048576,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 64000,
        "input_cost_per_1k": 0.003,
        "output_cost_per_1k": 0.015,
    },
    {
        "model_name": "claude-4.5-haiku-latest",
        "display_name": "Claude Haiku 4.5",
        "family": "claude-4",
        "context_window": 200000,
        "supports_tools": True,
        "supports_json": True,
        "supports_vision": True,
        "default_temperature": 0.3,
        "default_max_tokens": 64000,
        "input_cost_per_1k": 0.001,
        "output_cost_per_1k": 0.005,
    },
]


async def bootstrap_llm_registry() -> None:
    settings = get_settings()
    registry = get_registry()
 
    # 1. Provider
    provider = await registry.upsert_provider(
        code="groq",
        display_name="Groq",
        adapter_type="groq",
        base_url=None,
        enabled=True,
    )
 
    # 2. Models - upsert with current env-var names so the task map still works
    chat_env = settings.chat_model
    quiz_env = settings.quiz_model
    vlm_env = settings.vlm_model

    models_by_name: dict[str, int] = {}
    for spec in _DEFAULT_GROQ_MODELS:
        m = await registry.upsert_model(provider_id=provider.id, **spec)
        models_by_name[m.model_name] = m.id
 
    # Make sure the exact env-var names exist even if they differ from the
    # hard-coded defaults above (operators may pin a specific slug).
    for env_name, default_temp, default_max, is_vision in (
        (chat_env, 0.3, 1024, False),
        (quiz_env, 0.3, 2048, False),
        (vlm_env, 0.1, 512, True),
    ):
        if env_name and env_name not in models_by_name:
            m = await registry.upsert_model(
                provider_id=provider.id,
                model_name=env_name,
                display_name=env_name,
                family="llama",
                context_window=131072,
                supports_tools=True,
                supports_vision=is_vision,
                default_temperature=default_temp,
                default_max_tokens=default_max,
            )
            models_by_name[m.model_name] = m.id
 
    chat_model_id = models_by_name.get(chat_env) or next(iter(models_by_name.values()))
    quiz_model_id = models_by_name.get(quiz_env) or chat_model_id
    vlm_model_id = models_by_name.get(vlm_env) or chat_model_id
    # openai/gpt-oss-120b is used for section overview generation (long-context synthesis).
    # Falls back to quiz_model_id if the model is not present in the catalog.
    section_overview_model_id = models_by_name.get("openai/gpt-oss-120b") or quiz_model_id
    section_overview_70b_model_id = models_by_name.get("llama-3.3-70b-versatile") or quiz_model_id
 
    # 3. Seed Groq API key from env if pool is empty
    existing_keys = await registry.list_api_keys(provider_id=provider.id)
    if not existing_keys and settings.groq_api_key:
        try:
            await registry.create_api_key(
                provider_id=provider.id,
                alias="groq-env",
                plaintext_key=settings.groq_api_key,
            )
            logger.info("Migrated GROQ_API_KEY from env into llm_api_keys (alias=groq-env)")
        except Exception as exc:
            logger.warning("Could not seed Groq env key: %s", exc)

    total_models = len(models_by_name)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Google Gemini provider + models
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    gemini_provider = await registry.upsert_provider(
        code="gemini",
        display_name="Google Gemini",
        adapter_type="gemini",
        base_url=None,
        enabled=True,
    )

    for spec in _DEFAULT_GEMINI_MODELS:
        await registry.upsert_model(provider_id=gemini_provider.id, **spec)
        total_models += 1

    # Seed Gemini API key from env
    gemini_keys = await registry.list_api_keys(provider_id=gemini_provider.id)
    if not gemini_keys and settings.gemini_api_key:
        try:
            await registry.create_api_key(
                provider_id=gemini_provider.id,
                alias="gemini-env",
                plaintext_key=settings.gemini_api_key,
            )
            logger.info("Migrated GEMINI_API_KEY from env into llm_api_keys (alias=gemini-env)")
        except Exception as exc:
            logger.warning("Could not seed Gemini env key: %s", exc)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Anthropic provider + models
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    anthropic_provider = await registry.upsert_provider(
        code="anthropic",
        display_name="Anthropic Claude",
        adapter_type="anthropic",
        base_url=None,
        enabled=True,
    )

    for spec in _DEFAULT_CLAUDE_MODELS:
        await registry.upsert_model(provider_id=anthropic_provider.id, **spec)
        total_models += 1

    # Seed Anthropic API key from env
    anthropic_keys = await registry.list_api_keys(provider_id=anthropic_provider.id)
    if not anthropic_keys and settings.anthropic_api_key:
        try:
            await registry.create_api_key(
                provider_id=anthropic_provider.id,
                alias="anthropic-env",
                plaintext_key=settings.anthropic_api_key,
            )
            logger.info("Migrated ANTHROPIC_API_KEY from env into llm_api_keys (alias=anthropic-env)")
        except Exception as exc:
            logger.warning("Could not seed Anthropic env key: %s", exc)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Default task bindings (Groq only - admins bind Gemini via the Admin UI)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    default_bindings: list[tuple[str, int, int]] = [
        (TASK_CHAT,             chat_model_id, 10),
        (TASK_CLARIFICATION,    chat_model_id, 10),
        (TASK_LANGUAGE_DETECT,  chat_model_id, 10),
        (TASK_NODE_EXTRACT,     chat_model_id, 10),
        (TASK_AGENT_ROUTER,     chat_model_id, 10),
        (TASK_MEMORY_COMPRESS,  chat_model_id, 10),
        (TASK_FLASHCARD_GEN,    chat_model_id, 10),
        (TASK_GRAPH_LINK,       chat_model_id, 10),
        (TASK_DIAGNOSIS,        chat_model_id, 10),
        (TASK_QUIZ_GEN,         quiz_model_id, 10),
        (TASK_MICRO_LESSON_GEN, quiz_model_id, 10),
        (TASK_AGENT_REACT,      quiz_model_id, 10),
        (TASK_VLM_DESCRIBE,     vlm_model_id, 10),
        (TASK_SECTION_OVERVIEW_GEN, section_overview_70b_model_id, 5),
        (TASK_SECTION_OVERVIEW_GEN, section_overview_model_id, 10),
    ]

    existing = {(b.task_code, b.model.id) for b in await registry.list_bindings()}
    for task_code, model_id, priority in default_bindings:
        if (task_code, model_id) in existing:
            continue
        # Only seed if the task currently has no bindings at all (or if we are adding the new 70b
        # to section overview gen where only the old 120b/quiz binding is present)
        chain = await registry.list_bindings(task_code)
        if chain and task_code != TASK_SECTION_OVERVIEW_GEN:
            continue
        if task_code == TASK_SECTION_OVERVIEW_GEN:
            has_this_model = any(b.model.id == model_id for b in chain)
            if has_this_model:
                continue
        await registry.upsert_binding(
            task_code=task_code,
            model_id=model_id,
            priority=priority,
            enabled=True,
            notes="seeded-default",
        )

    # Warm binding cache for every known task code
    registry.invalidate()
    warmed: list[str] = []
    for task_code in ALL_TASK_CODES:
        try:
            chain = await registry.get_binding_chain(task_code)
            if chain:
                warmed.append(task_code)
        except Exception as exc:
            logger.warning("Could not warm binding cache for task=%s: %s", task_code, exc)

    logger.info(
        "LLM registry bootstrapped: providers=[groq, gemini, anthropic] models=%d warmed=%s",
        total_models, warmed,
    )