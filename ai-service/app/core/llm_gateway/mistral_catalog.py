"""Mistral /v1/models snapshot supplied by the operator, 2026-11-19.

Alias groups share the exact supplied capability flags and context length.
Catalog seeding creates missing rows only; binding promotion is separate.
Neither operation creates keys or makes paid calls.
"""
from __future__ import annotations

from app.core.llm_gateway.registry import ModelRegistry
from app.core.llm_gateway.types import ALL_TASK_CODES, TASK_JEV_DECISION, TASK_TEXT_TO_SPEECH

_FLAGS = (
    "completion_chat function_calling reasoning completion_fim fine_tuning vision ocr "
    "classification moderation audio audio_transcription audio_transcription_realtime "
    "audio_speech unified_resources"
).split()

_TTS_MODELS = {"voxtral-mini-tts-3-0", "voxtral-mini-tts-3"}
_TTS_CONFIG = {
    "voice_id": "voice_3144", "response_format": "mp3", "speed": 1.0,
    "voices_by_language": {"vi": "voice_3144", "en": "voice_478"},
    "speech_integration_version": 1,
}

# (canonical name + aliases, max_context_length, true capabilities)
_GROUPS = [
    ("codestral-2508 codestral-latest mistral-code-latest mistral-code-fim-latest", 256000, "completion_chat function_calling completion_fim"),
    ("deepseek-v4-1-flash-1017", 1048576, "completion_chat function_calling reasoning vision unified_resources"),
    ("glm-5-2 zai-glm-5-2", 1048576, "completion_chat function_calling reasoning unified_resources"),
    ("zai-glm-5-3 zai-glm-5 zai-glm-latest", 1048576, "completion_chat function_calling reasoning unified_resources"),
    ("zai-glm-5-3-flash", 1048576, "completion_chat function_calling reasoning vision unified_resources"),
    ("ministral-14b-2512 ministral-14b-latest", 262144, "completion_chat function_calling fine_tuning vision"),
    ("ministral-3b-2512 ministral-3b-latest", 131072, "completion_chat function_calling fine_tuning vision"),
    ("ministral-8b-2512 ministral-8b-latest", 262144, "completion_chat function_calling fine_tuning vision"),
    ("mistral-large-2512", 262144, "completion_chat function_calling fine_tuning vision"),
    ("mistral-large-4 mistral-large-4-0 mistral-large-latest", 1048576, "completion_chat function_calling reasoning vision unified_resources"),
    ("mistral-medium-latest mistral-medium mistral-medium-3-5 mistral-medium-3.5 mistral-medium-3 mistral-medium-2604 mistral-vibe-cli-latest mistral-vibe-cli-with-tools magistral-medium-latest", 262144, "completion_chat function_calling reasoning vision"),
    ("mistral-small-2603 mistral-small-latest mistral-vibe-cli-fast magistral-small-latest", 262144, "completion_chat function_calling reasoning vision"),
    ("voxtral-small-2507 voxtral-small-latest", 32768, "completion_chat function_calling audio"),
    ("codestral-embed codestral-embed-2505", 8192, ""),
    ("mistral-embed-2312 mistral-embed", 8192, ""),
    ("mistral-moderation-2603", 131071, "classification moderation"),
    ("mistral-ocr-2512 mistral-ocr-3-0 mistral-ocr-3", 16384, "function_calling vision ocr"),
    ("mistral-ocr-latest mistral-ocr-4 mistral-ocr-4-1", 16384, "function_calling ocr"),
    ("voxtral-mini-2602 voxtral-mini-latest", 16384, "audio_transcription"),
    ("voxtral-mini-transcribe-3 voxtral-mini-transcribe-3-0", 65536, "audio_transcription"),
    ("voxtral-mini-transcribe-realtime-2602 voxtral-mini-realtime-2602 voxtral-mini-realtime-latest", 32768, "audio_transcription_realtime"),
    ("voxtral-mini-transcribe-realtime-3 voxtral-mini-transcribe-realtime-3-0", 65536, "audio_transcription_realtime"),
    ("voxtral-small-transcribe-3 voxtral-small-transcribe-3-0", 65536, "audio_transcription"),
    ("voxtral-mini-tts-2603 voxtral-mini-tts-latest", 4096, "function_calling fine_tuning audio_speech"),
    ("voxtral-mini-tts-3-0 voxtral-mini-tts-3", 4096, "audio_speech"),
]


def catalog_models():
    for aliases, context, true_flags in _GROUPS:
        names = aliases.split()
        capabilities = {flag: flag in true_flags.split() for flag in _FLAGS}
        chat = capabilities["completion_chat"]
        audio = any(capabilities[flag] for flag in ("audio", "audio_transcription", "audio_transcription_realtime", "audio_speech"))
        if capabilities["audio_speech"]:
            family, protocol, label, inputs, outputs = "audio", "mistral_speech", "Text → Audio", ["text"], ["audio"]
        elif capabilities["audio_transcription_realtime"]:
            family, protocol, label, inputs, outputs = "audio", "mistral_realtime", "Audio → Text · Realtime", ["audio"], ["text"]
        elif capabilities["audio_transcription"]:
            family, protocol, label, inputs, outputs = "audio", "mistral_transcription", "Audio → Text", ["audio"], ["text"]
        elif chat:
            family = "audio" if audio else "mistral"
            protocol = "chat"
            inputs = ["text"] + (["image"] if capabilities["vision"] else []) + (["audio"] if audio else [])
            outputs = ["text"]
            label = " + ".join(item.title() for item in inputs) + " → Text"
        elif capabilities["ocr"]:
            family, protocol, label, inputs, outputs = "ocr", "mistral_ocr", "Image / PDF → Text · OCR", ["image", "document"], ["text"]
        elif capabilities["moderation"]:
            family, protocol, label, inputs, outputs = "moderation", "mistral_moderation", "Text → Classification", ["text"], ["classification"]
        else:
            family, protocol, label, inputs, outputs = "embedding", "mistral_embedding", "Text → Vector", ["text"], ["embedding"]
        for name in names:
            speech = name in _TTS_MODELS
            yield dict(
                model_name=name, display_name=f"{name} · {label}", family=family,
                context_window=context, supports_json=chat,
                supports_tools=capabilities["function_calling"],
                supports_vision=capabilities["vision"], supports_streaming=chat,
                default_max_tokens=8192 if chat else 1, enabled=chat or speech,
                config={
                    **(_TTS_CONFIG if speech else {}),
                    "api_protocol": protocol, "catalog_only": not (chat or speech),
                    "input_modalities": inputs, "output_modalities": outputs,
                    "capabilities": capabilities, "aliases": [alias for alias in names if alias != name],
                    "catalog_source": "operator:/v1/models:2026-11-19",
                },
            )


async def bootstrap_mistral(registry: ModelRegistry) -> int:
    provider = await registry.get_provider_by_code("mistral")
    if provider is None:
        provider = await registry.upsert_provider(
            code="mistral", display_name="Mistral AI", adapter_type="openai_compat",
            base_url="https://api.mistral.ai/v1", enabled=True,
        )
    existing = {model.model_name: model for model in await registry.list_models(provider_id=provider.id)}
    specs = list(catalog_models())
    for spec in specs:
        if spec["model_name"] not in existing:
            await registry.upsert_model(provider_id=provider.id, **spec)
        elif spec["model_name"] in _TTS_MODELS:
            model = existing[spec["model_name"]]
            if model.config.get("catalog_only") and not model.config.get("speech_integration_version"):
                # One-time activation of the previously catalog-only TTS rows.
                # Preserve their IDs, provider/key association and admin config.
                config = {
                    **_TTS_CONFIG, **model.config,
                    "catalog_only": False, "speech_integration_version": 1,
                }
                if model.config.get("voice_id") and "voices_by_language" not in model.config:
                    config["voices_by_language"] = {}
                await registry.update_model(model.id, enabled=True, config=config)
    return len(specs)


# Routing policy, not a claim about measured latency or quality. Use only
# chat-capable Mistral models; specialized protocols retain their own bindings.
_MISTRAL_TASK_MODELS = {
    TASK_TEXT_TO_SPEECH: "voxtral-mini-tts-3-0",
    **dict.fromkeys(("agent_router", "language_detect", "clarification"), "ministral-3b-2512"),
    "agent_flash": "ministral-8b-2512",
    "diagnosis": "mistral-small-2603",
    **dict.fromkeys((
        "agent_react", "quiz_gen", "create_lab", "create_lab_generator",
        "create_lab_testcase", "edit_testcase", "course_blueprint", "content_studio",
    ), "mistral-large-latest"),
}
_BINDING_SEED = "seeded-mistral-first:v1"


async def bootstrap_mistral_bindings(registry: ModelRegistry) -> None:
    """Promote once per task, retaining fallbacks and subsequent admin edits."""
    provider = await registry.get_provider_by_code("mistral")
    if provider is None or not provider.enabled:
        return
    models = {
        model.model_name: model
        for model in await registry.list_models(provider_id=provider.id, only_enabled=True)
        if not model.config.get("catalog_only")
    }
    for task in ALL_TASK_CODES:
        if task == TASK_JEV_DECISION:
            continue
        model = models.get(_MISTRAL_TASK_MODELS.get(task, "mistral-medium-latest"))
        if model is None or (task == "vlm_describe" and not model.supports_vision):
            continue
        chain = await registry.list_bindings(task)
        if any((binding.notes or "").startswith(_BINDING_SEED) for binding in chain):
            continue
        priority = min((binding.priority for binding in chain), default=10) - 10
        existing = next((binding for binding in chain if binding.model.id == model.id), None)
        if existing:
            # Do not reset JSON, max tokens, temperature or Pin on an existing row.
            await registry.update_binding(
                existing.id, priority=priority, enabled=True,
                notes=f"{_BINDING_SEED}; {existing.notes or ''}".rstrip(),
            )
        else:
            await registry.upsert_binding(
                task_code=task, model_id=model.id, priority=priority,
                enabled=True, pinned=False, notes=_BINDING_SEED,
            )
