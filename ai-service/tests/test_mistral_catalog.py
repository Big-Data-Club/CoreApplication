from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core.llm_gateway.mistral_catalog import bootstrap_mistral, catalog_models
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
        assert m["enabled"] == chat
        assert cfg["catalog_only"] == (not chat)
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
