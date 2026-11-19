from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core.llm_gateway.mistral_catalog import bootstrap_mistral, bootstrap_mistral_bindings, catalog_models
from app.core.llm_gateway.types import ALL_TASK_CODES
from app.api.endpoints.admin_llm import BindingIn, upsert_binding


def test_catalog_matches_operator_capabilities_and_separates_protocols():
    models = list(catalog_models())
    by_name = {m["model_name"]: m for m in models}
    assert len(models) == len(by_name) == 62
    assert by_name["codestral-latest"]["context_window"] == 256000
    assert by_name["mistral-large-latest"]["context_window"] == 1048576
    assert by_name["mistral-large-latest"]["config"]["capabilities"]["reasoning"]
    assert not by_name["zai-glm-5-3"]["supports_vision"]
    assert by_name["zai-glm-5-3-flash"]["supports_vision"]
    assert not by_name["mistral-ocr-4"]["supports_vision"]
    assert by_name["mistral-ocr-4"]["config"]["input_modalities"] == ["image", "document"]
    for m in models:
        cfg = m["config"]
        chat = cfg["capabilities"]["completion_chat"]
        supported = chat or m["model_name"] in ("voxtral-mini-tts-3-0", "voxtral-mini-tts-3")
        assert m["enabled"] == supported
        assert cfg["catalog_only"] == (not supported)
        if any(cfg["capabilities"][flag] for flag in (
            "audio", "audio_transcription", "audio_transcription_realtime", "audio_speech",
        )):
            assert m["family"] == "audio"
        for alias in cfg["aliases"]:
            assert by_name[alias]["config"]["capabilities"] == cfg["capabilities"]
            assert by_name[alias]["context_window"] == m["context_window"]


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_and_preserves_admin_changes():
    rows = {"mistral-large-latest": {"model_name": "mistral-large-latest", "enabled": False}}
    provider = SimpleNamespace(id=8)

    async def upsert(**spec):
        rows[spec["model_name"]] = spec

    registry = SimpleNamespace(
        get_provider_by_code=AsyncMock(side_effect=[None, provider]),
        upsert_provider=AsyncMock(return_value=provider),
        list_models=AsyncMock(side_effect=lambda **kw: [SimpleNamespace(**row) for row in rows.values()]),
        upsert_model=AsyncMock(side_effect=upsert),
    )
    assert await bootstrap_mistral(registry) == 62
    assert await bootstrap_mistral(registry) == 62
    assert len(rows) == 62
    assert registry.upsert_model.await_count == 61
    registry.upsert_provider.assert_awaited_once()
    assert rows["mistral-large-latest"] == {"model_name": "mistral-large-latest", "enabled": False}


@pytest.mark.asyncio
async def test_catalog_only_model_cannot_be_bound_to_chat():
    registry = SimpleNamespace(
        get_model=AsyncMock(return_value=SimpleNamespace(config={"catalog_only": True})),
        upsert_binding=AsyncMock(),
    )
    with patch("app.api.endpoints.admin_llm._verify"), patch(
        "app.api.endpoints.admin_llm.get_registry", return_value=registry,
    ):
        with pytest.raises(HTTPException) as error:
            await upsert_binding(BindingIn(task_code="agent_react", model_id=1), None)
    assert error.value.status_code == 400
    registry.upsert_binding.assert_not_awaited()


@pytest.mark.asyncio
async def test_mistral_promoted_once_without_replacing_fallbacks_or_admin_settings():
    models = [SimpleNamespace(id=i, **spec) for i, spec in enumerate(catalog_models(), 1) if spec["enabled"]]
    by_name = {model.model_name: model for model in models}
    fallback = SimpleNamespace(id=999, priority=-5, notes="admin", model=SimpleNamespace(id=999),
        enabled=True, pinned=True, max_tokens=4000, temperature=0.1, json_mode=True)
    flash = SimpleNamespace(id=998, priority=30, notes="my flash", model=by_name["ministral-8b-2512"],
        enabled=True, pinned=False, max_tokens=2000, temperature=0.2, json_mode=True)
    chains = {task: [fallback] for task in ALL_TASK_CODES}
    chains["agent_flash"] = [fallback, flash]

    async def upsert(**values):
        binding = SimpleNamespace(id=len(chains[values["task_code"]]),
            model=next(m for m in models if m.id == values["model_id"]), **values)
        chains[values["task_code"]].append(binding)

    async def update(binding_id, **values):
        assert binding_id == flash.id
        for key, value in values.items():
            setattr(flash, key, value)

    registry = SimpleNamespace(
        get_provider_by_code=AsyncMock(return_value=SimpleNamespace(id=8, enabled=True)),
        list_models=AsyncMock(return_value=models),
        list_bindings=AsyncMock(side_effect=lambda task: chains[task]),
        upsert_binding=AsyncMock(side_effect=upsert), update_binding=AsyncMock(side_effect=update),
    )
    await bootstrap_mistral_bindings(registry)
    for task in ALL_TASK_CODES:
        if task == "jev_decision":
            assert chains[task] == [fallback]
            continue
        first = min(chains[task], key=lambda b: b.priority)
        assert first.model.id in {m.id for m in models}
        assert first.priority < fallback.priority
        assert fallback in chains[task]
    assert min(chains["agent_react"], key=lambda b: b.priority).model.model_name == "mistral-large-latest"
    assert min(chains["vlm_describe"], key=lambda b: b.priority).model.supports_vision
    assert min(chains["text_to_speech"], key=lambda b: b.priority).model.model_name == "voxtral-mini-tts-3-0"
    assert (flash.max_tokens, flash.temperature, flash.json_mode) == (2000, 0.2, True)
    assert fallback.pinned  # Bootstrap must not silently revoke an explicit Pin.
    writes = registry.upsert_binding.await_count
    flash.priority, flash.enabled = 99, False  # Later admin override survives restart.
    await bootstrap_mistral_bindings(registry)
    assert registry.upsert_binding.await_count == writes
    registry.update_binding.assert_awaited_once()
    assert (flash.priority, flash.enabled) == (99, False)


@pytest.mark.asyncio
async def test_disabled_mistral_provider_is_not_promoted():
    registry = SimpleNamespace(
        get_provider_by_code=AsyncMock(return_value=SimpleNamespace(id=8, enabled=False)),
        list_models=AsyncMock(),
    )
    await bootstrap_mistral_bindings(registry)
    registry.list_models.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_catalog_tts_is_activated_once_using_same_model_id():
    rows = {spec["model_name"]: SimpleNamespace(id=i, **spec)
        for i, spec in enumerate(catalog_models(), 1)}
    for name in ("voxtral-mini-tts-3-0", "voxtral-mini-tts-3"):
        rows[name].config = {"api_protocol": "mistral_speech", "catalog_only": True, "voice_id": "custom"}
        rows[name].enabled = False
    ids = {m.id: m for m in rows.values()}

    async def update(model_id, **values):
        for key, value in values.items():
            setattr(ids[model_id], key, value)

    registry = SimpleNamespace(
        get_provider_by_code=AsyncMock(return_value=SimpleNamespace(id=8)),
        list_models=AsyncMock(side_effect=lambda **kw: list(rows.values())),
        upsert_model=AsyncMock(), update_model=AsyncMock(side_effect=update),
    )
    await bootstrap_mistral(registry)
    tts = rows["voxtral-mini-tts-3-0"]
    assert tts.enabled and not tts.config["catalog_only"]
    assert tts.config["voice_id"] == "custom"
    assert tts.config["voices_by_language"] == {}  # Custom voice takes precedence.
    tts.enabled = False  # Later admin choice must survive restart.
    await bootstrap_mistral(registry)
    assert not tts.enabled
    assert registry.update_model.await_count == 2
    registry.upsert_model.assert_not_awaited()
