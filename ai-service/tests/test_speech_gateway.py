from __future__ import annotations

import asyncio
import base64
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from app.core.llm_gateway.adapters.speech import synthesize
from app.core.llm_gateway.errors import ProviderError, RateLimitedError
from app.core.llm_gateway.gateway import LLMGateway
from app.core.llm_gateway.types import Model, SpeechRequest, TaskBinding


def mistral_model():
    return replace(model(), provider_id=42, provider_code="mistral", adapter_type="openai_compat",
        base_url="https://api.mistral.ai/v1", model_name="voxtral-mini-tts-3-0", family="audio",
        config={"api_protocol": "mistral_speech", "voice_id": "voice_3144", "response_format": "mp3",
                "voices_by_language": {"vi": "voice_3144", "en": "voice_478"}})


@pytest.mark.parametrize("language,voice", [("vi-VN", "voice_3144"), ("en-US", "voice_478")])
def test_mistral_uses_voice_id_and_decodes_json_audio(language, voice):
    import json
    from app.core.llm_gateway.adapters.speech import is_speech_model, speech_media_type
    def handle(req):
        assert str(req.url) == "https://api.mistral.ai/v1/audio/speech"
        assert req.headers["authorization"] == "Bearer fixture-key"
        assert json.loads(req.content) == {"model": "voxtral-mini-tts-3-0", "input": "Hello",
            "voice_id": voice, "response_format": "mp3", "stream": False}
        return httpx.Response(200, json={"audio_data": base64.b64encode(b"mp3-audio").decode()})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with patch("app.core.llm_gateway.adapters.speech.httpx.AsyncClient", return_value=client):
        audio = asyncio.run(synthesize(mistral_model(), "fixture-key", SpeechRequest(text="Hello", language=language)))
    assert audio == b"mp3-audio"
    assert speech_media_type(mistral_model()) == "audio/mpeg"
    assert is_speech_model(mistral_model())
    assert not is_speech_model(replace(mistral_model(), config={"api_protocol": "chat"}))


@pytest.mark.parametrize("payload", [{}, {"audio_data": ""}, {"audio_data": "not base64 private text"},
                                     {"audio_data": None}, ["unexpected schema"]])
def test_mistral_rejects_invalid_audio_without_exposing_response(payload):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload)))
    with patch("app.core.llm_gateway.adapters.speech.httpx.AsyncClient", return_value=client):
        with pytest.raises(ProviderError) as raised:
            asyncio.run(synthesize(mistral_model(), "fixture-key", SpeechRequest(text="Private input")))
    assert "private" not in str(raised.value).lower()


def test_mistral_numeric_speed_is_applied_locally_without_unsupported_api_fields():
    from pathlib import Path
    def handle(req):
        import json
        assert "speed" not in json.loads(req.content)
        return httpx.Response(200, json={"audio_data": base64.b64encode(b"input-mp3").decode()})

    async def ffmpeg(*args, **kwargs):
        assert args[:4] == ("ffmpeg", "-y", "-v", "error")
        assert "atempo=0.800" in args
        assert Path(args[5]).read_bytes() == b"input-mp3"
        Path(args[-1]).write_bytes(b"slower-mp3")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with patch("app.core.llm_gateway.adapters.speech.httpx.AsyncClient", return_value=client), patch(
        "app.services.studio.browser_renderer.command", side_effect=ffmpeg,
    ):
        audio = asyncio.run(synthesize(mistral_model(), "fixture-key", SpeechRequest(text="Hello", speed=.8)))
    assert audio == b"slower-mp3"


def test_gateway_reuses_mistral_provider_key_and_falls_back_after_tts_rejection():
    async def run():
        first, fallback = mistral_model(), model()
        chain = [TaskBinding(1, "text_to_speech", first, 0, None, None, False, False, True, None),
                 TaskBinding(2, "text_to_speech", fallback, 10, None, None, False, False, True, None)]
        gateway = LLMGateway.__new__(LLMGateway)
        gateway.registry = SimpleNamespace(get_binding_chain=AsyncMock(return_value=chain))
        gateway.key_pool = SimpleNamespace(lease=AsyncMock(return_value=SimpleNamespace(id=1, plaintext="fixture-key")),
            record_success=AsyncMock())
        gateway._log = AsyncMock()
        with patch("app.core.llm_gateway.adapters.speech.synthesize", side_effect=[ProviderError("rejected", retryable=False), b"backup"]):
            response = await gateway.speech(SpeechRequest(text="Hello"))
        assert response.audio == b"backup" and response.model == fallback
        assert gateway.key_pool.lease.call_args_list[0].args[0] == 42
        assert gateway.key_pool.lease.call_args_list[1].args[0] == fallback.provider_id
    asyncio.run(run())


def test_mistral_speech_binding_is_accepted_but_not_for_chat():
    from fastapi import HTTPException
    from app.api.endpoints.admin_llm import BindingIn, upsert_binding

    async def run():
        voice = mistral_model()
        binding = TaskBinding(1, "text_to_speech", voice, 0, None, None, False, False, True, None)
        registry = SimpleNamespace(get_model=AsyncMock(return_value=voice),
            upsert_binding=AsyncMock(return_value=binding))
        with patch("app.api.endpoints.admin_llm._verify"), patch(
            "app.api.endpoints.admin_llm.get_registry", return_value=registry,
        ):
            await upsert_binding(BindingIn(task_code="text_to_speech", model_id=voice.id), None)
            registry.upsert_binding.assert_awaited_once()
            with pytest.raises(HTTPException) as raised:
                await upsert_binding(BindingIn(task_code="chat", model_id=voice.id), None)
        assert raised.value.status_code == 400
        registry.upsert_binding.assert_awaited_once()
    asyncio.run(run())


def model():
    return Model(1, 1, "runway", "runway", None, "eleven_v3", "Voice", "speech", 2400,
                 False, False, False, False, 0, 0, .2, 1, True, {"voice_id": "Niki"})


def test_runway_polls_audio_task_without_leaking_key_to_asset_host():
    import json
    requests = []
    def handle(req):
        requests.append(req)
        if req.url.path.endswith("text_to_speech"):
            data = json.loads(req.content)
            assert data["voice"] == {"type": "runway-preset", "presetId": "Niki"}
            assert data["speed"] == .97 and data["languageCode"] == "vi"
            return httpx.Response(200, json={"id": "fixture"})
        if req.url.path.endswith("/tasks/fixture"):
            return httpx.Response(200, json={"status": "SUCCEEDED", "output": ["https://asset.example/speech.mp3"]})
        assert "Authorization" not in req.headers
        return httpx.Response(200, content=b"audio")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with patch("app.core.llm_gateway.adapters.speech.httpx.AsyncClient", return_value=client):
        data = asyncio.run(synthesize(model(), "fixture-not-a-real-key", SpeechRequest(text="Xin chào")))
    assert data == b"audio" and len(requests) == 3


def test_elevenlabs_requires_real_voice_id_not_runway_preset():
    with pytest.raises(ProviderError, match="voice_required"):
        asyncio.run(synthesize(replace(model(), adapter_type="elevenlabs", config={}), "fixture", SpeechRequest(text="x")))


def test_gateway_rotates_keys_on_rate_limit_and_uses_measured_provider_output():
    async def run():
        binding = TaskBinding(1, "text_to_speech", model(), 10, None, None, False, False, True)
        gateway = LLMGateway(registry=SimpleNamespace(get_binding_chain=AsyncMock(return_value=[binding])))
        gateway.key_pool = SimpleNamespace(lease=AsyncMock(side_effect=[SimpleNamespace(id=10, plaintext="fixture-a"), SimpleNamespace(id=11, plaintext="fixture-b")]),
                                          record_rate_limit=AsyncMock(), record_success=AsyncMock())
        gateway._log = AsyncMock()
        with patch("app.core.llm_gateway.adapters.speech.synthesize", new=AsyncMock(side_effect=[RateLimitedError("quota", retry_after=3600), b"audio"])):
            result = await gateway.speech(SpeechRequest(text="x"))
        assert result.api_key_id == 11 and result.audio == b"audio"
        gateway.key_pool.record_rate_limit.assert_awaited_once_with(10, retry_after_seconds=3600)
        gateway.key_pool.record_success.assert_awaited_once_with(11, tokens_used=0)
    asyncio.run(run())


def test_runway_failure_is_not_masked_by_missing_fallback_key():
    from app.core.llm_gateway.errors import NoKeyAvailableError
    from app.core.llm_gateway.speech_errors import SpeechProviderError
    async def run():
        first = TaskBinding(1,"text_to_speech",model(),10,None,None,False,False,True)
        second = replace(first,id=2,model=replace(model(),provider_id=2,adapter_type="elevenlabs"))
        gateway = LLMGateway(registry=SimpleNamespace(get_binding_chain=AsyncMock(return_value=[first,second])))
        gateway.key_pool = SimpleNamespace(lease=AsyncMock(side_effect=[SimpleNamespace(id=10,plaintext="fixture"),NoKeyAvailableError("no fallback key")]))
        gateway._log = AsyncMock()
        error = SpeechProviderError("request_rejected",provider="runway",status_code=422)
        with patch("app.core.llm_gateway.adapters.speech.synthesize",new=AsyncMock(side_effect=error)):
            with pytest.raises(SpeechProviderError) as raised:
                await gateway.speech(SpeechRequest(text="Xin chào"))
        assert raised.value is error
        assert gateway.key_pool.lease.await_count == 2
    asyncio.run(run())


@pytest.mark.parametrize("status,code",[(400,"request_rejected"),(402,"credits_required"),(404,"not_found"),(422,"request_rejected")])
def test_speech_provider_failure_reports_status_without_echoing_body(status,code):
    from app.core.llm_gateway.adapters.speech import check_response
    from app.core.llm_gateway.speech_errors import SpeechProviderError,speech_failure_message
    response = httpx.Response(status,json={"error":"secret-key-and-private-narration"})
    with pytest.raises(SpeechProviderError) as raised: check_response(response,"runway")
    assert raised.value.status_code == status and raised.value.code == code
    assert "secret-key" not in str(raised.value)+speech_failure_message(raised.value)


def test_download_forbidden_does_not_invalidate_a_working_runway_key():
    from app.core.llm_gateway.adapters.speech import check_response
    from app.core.llm_gateway.errors import AuthError
    from app.core.llm_gateway.speech_errors import SpeechProviderError
    with pytest.raises(SpeechProviderError) as raised:
        check_response(httpx.Response(403),"runway",credentials=False)
    assert not isinstance(raised.value,AuthError)
    assert raised.value.code == "asset_download"


def test_http_429_keeps_key_rotation_even_with_a_quota_code():
    from app.core.llm_gateway.adapters.speech import check_response
    with pytest.raises(RateLimitedError) as raised:
        check_response(httpx.Response(429,json={"code":"quota_exceeded"},headers={"Retry-After":"90"}),"runway")
    assert raised.value.retry_after == 90


def test_speech_ui_distinguishes_configuration_from_media_failures():
    from app.core.llm_gateway.speech_errors import SpeechProviderError,speech_failure_message
    assert "credit" in speech_failure_message(SpeechProviderError("credits_required",provider="runway"))
    assert "FFmpeg" in speech_failure_message(FileNotFoundError("secret path"),stage="audio_processing")
    assert "MinIO" in speech_failure_message(ValueError("secret endpoint"),stage="storage")


def test_failed_card_persists_specific_diagnostic_and_correlates_gateway_job():
    from uuid import uuid4
    from app.services import speech_service
    from app.core.llm_gateway.speech_errors import SpeechProviderError
    async def run():
        job_id = uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = {"id":job_id,"owner_id":1,"attempts":1,"request":{"text":"Xin chào","language":"vi","speed":0.97}}
        gateway = SimpleNamespace(speech=AsyncMock(side_effect=SpeechProviderError("credits_required",provider="runway",status_code=402)))
        with patch.object(speech_service,"get_ai_conn") as pool, patch.object(speech_service,"get_gateway",return_value=gateway):
            pool.return_value.__aenter__.return_value = conn
            assert await speech_service.run_next_speech()
        request = gateway.speech.call_args.args[0]
        assert request.request_id == str(job_id)
        query,*parameters = conn.execute.call_args.args
        assert "error=$3" in query
        assert "credit" in parameters[-1] and str(job_id) in parameters[-1]
        assert "Xin chào" not in parameters[-1]
    asyncio.run(run())


def test_speech_status_rejects_missing_secret_and_cross_owner():
    from app.api.endpoints import speech
    from uuid import uuid4
    app = FastAPI(); app.include_router(speech.router)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            url = f"/speech/jobs/{uuid4()}?user_id=2"
            assert (await client.get(url)).status_code == 401
            with patch("app.api.endpoints.speech.get_ai_conn") as pool:
                conn = AsyncMock(); conn.fetchrow.return_value = None
                pool.return_value.__aenter__.return_value = conn
                from app.core.config import get_settings
                with patch.object(get_settings(), "ai_service_secret", "fixture-secret"):
                    assert (await client.get(url, headers={"X-AI-Secret": "fixture-secret"})).status_code == 404
                assert conn.fetchrow.call_args.args[-1] == 2
    asyncio.run(run())


def test_flashcard_speech_uses_server_owned_text_and_checks_course():
    from app.services.speech_service import request_flashcard_speech
    async def run():
        with patch("app.services.speech_service.get_ai_conn") as pool:
            conn = AsyncMock(); conn.fetchrow.return_value = None
            pool.return_value.__aenter__.return_value = conn
            with pytest.raises(LookupError): await request_flashcard_speech(2, 99, 8, "front", .97)
            assert conn.fetchrow.call_args.args[-3:] == (99, 2, 8)
    asyncio.run(run())


def test_speech_bootstrap_preserves_existing_admin_voice_and_binding():
    from app.core.llm_gateway.bootstrap import _bootstrap_speech
    speech_settings = SimpleNamespace(
        ai_gateway_base_url="https://bdc.example/aimodels/v1",
        ai_gateway_api_key="",
        ai_gateway_tts_model="vieneu-v3-turbo",
        ai_gateway_tts_voice="",
    )

    async def run():
        registry = _FakeRegistry()
        provider = await registry.upsert_provider(
            code="runway", display_name="Runway Speech", adapter_type="runway",
            base_url="https://api.dev.runwayml.com",
        )
        custom = await registry.upsert_model(
            provider_id=provider.id, model_name="eleven_v3", config={"voice_id": "custom", "speed": .9},
        )
        admin_binding = await registry.upsert_binding(
            task_code="text_to_speech", model_id=custom.id, priority=10, notes="admin",
        )
        with patch("app.core.llm_gateway.bootstrap.get_settings", return_value=speech_settings):
            await _bootstrap_speech(registry)
        assert custom.config == {"voice_id": "custom", "speed": .9}
        assert admin_binding.priority == 10
        gateway = registry.providers["bdc-tts"]
        gateway_model = next(m for m in registry.models[gateway.id] if m.model_name == "vieneu-v3-turbo")
        gateway_binding = next(b for b in registry.bindings if b.model.id == gateway_model.id)
        # Without a usable key the self-hosted model is a fallback, never first.
        assert gateway_binding.priority > admin_binding.priority

    asyncio.run(run())


def test_speech_bootstrap_binds_self_hosted_tts_first_when_gateway_key_exists():
    from app.core.llm_gateway.bootstrap import _bootstrap_speech
    speech_settings = SimpleNamespace(
        ai_gateway_base_url="https://bdc.example/aimodels/v1",
        ai_gateway_api_key="fixture-gateway-key-not-a-placeholder",
        ai_gateway_tts_model="vieneu-v3-turbo",
        ai_gateway_tts_voice="",
    )

    async def run():
        registry = _FakeRegistry()
        with patch("app.core.llm_gateway.bootstrap.get_settings", return_value=speech_settings):
            await _bootstrap_speech(registry)
        gateway = registry.providers["bdc-tts"]
        assert registry.providers["bdc-tts"].base_url == "https://bdc.example/aimodels/v1"
        gateway_model = next(m for m in registry.models[gateway.id] if m.model_name == "vieneu-v3-turbo")
        assert registry.keys[gateway.id][0].alias == "bdc-ai-gateway-env"
        assert registry.bindings[0].model.id == gateway_model.id
        assert registry.bindings[0].priority < registry.bindings[1].priority

    asyncio.run(run())


def test_speech_bootstrap_reuses_an_existing_self_hosted_speech_provider():
    from app.core.llm_gateway.bootstrap import _bootstrap_speech
    speech_settings = SimpleNamespace(
        ai_gateway_base_url="https://bdc.example/aimodels/v1",
        ai_gateway_api_key="",
        ai_gateway_tts_model="vieneu-v3-turbo",
        ai_gateway_tts_voice="",
    )

    async def run():
        registry = _FakeRegistry()
        existing = await registry.upsert_provider(
            code="bdc", display_name="BDC AI Models", adapter_type="openai_speech",
            base_url="https://custom.example/v1",
        )
        with patch("app.core.llm_gateway.bootstrap.get_settings", return_value=speech_settings):
            await _bootstrap_speech(registry)
        assert "bdc-tts" not in registry.providers
        assert registry.providers["bdc"].base_url == "https://custom.example/v1"
        assert any(m.model_name == "vieneu-v3-turbo" for m in registry.models[existing.id])
        assert any(b.model.id == next(m.id for m in registry.models[existing.id]) for b in registry.bindings)

    asyncio.run(run())


def test_openai_speech_uses_gateway_contract_and_reports_wav_media_type():
    from app.core.llm_gateway.adapters.speech import speech_media_type
    requests = []

    def handle(req):
        requests.append(req)
        assert req.url.path == "/aimodels/v1/audio/speech"
        assert req.headers["authorization"] == "Bearer fixture-key"
        import json
        assert json.loads(req.content) == {
            "model": "vieneu-v3-turbo",
            "input": "Xin chào",
            "response_format": "wav",
        }
        return httpx.Response(200, content=b"RIFFwav-bytes", headers={"content-type": "audio/wav"})

    speech_model = replace(
        model(), adapter_type="openai_speech", model_name="vieneu-v3-turbo",
        base_url="https://bdc.example/aimodels/v1",
        config={"voice_id": "", "response_format": "wav"},
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with patch("app.core.llm_gateway.adapters.speech.httpx.AsyncClient", return_value=client):
        data = asyncio.run(synthesize(speech_model, "fixture-key", SpeechRequest(text="Xin chào")))
    assert data == b"RIFFwav-bytes" and len(requests) == 1
    assert speech_media_type(speech_model) == "audio/wav"


def test_openai_speech_requires_a_base_url():
    from app.core.llm_gateway.speech_errors import SpeechProviderError
    broken = replace(model(), adapter_type="openai_speech", base_url=None, config={})
    with pytest.raises(SpeechProviderError, match="missing_base_url"):
        asyncio.run(synthesize(broken, "fixture", SpeechRequest(text="x")))


class _FakeRegistry:
    """Minimal in-memory registry for bootstrap seeding tests."""

    def __init__(self):
        self.providers: dict[str, SimpleNamespace] = {}
        self.models: dict[int, list[SimpleNamespace]] = {}
        self.bindings: list[SimpleNamespace] = []
        self.keys: dict[int, list[SimpleNamespace]] = {}
        self._next_id = 100

    def _new(self, **fields):
        self._next_id += 1
        return SimpleNamespace(id=self._next_id, **fields)

    async def get_provider_by_code(self, code):
        return self.providers.get(code)

    async def list_providers(self):
        return list(self.providers.values())

    async def update_provider(self, provider_id, **fields):
        provider = next(p for p in self.providers.values() if p.id == provider_id)
        for key, value in fields.items():
            setattr(provider, key, value)
        return provider

    async def upsert_provider(self, *, code, display_name, adapter_type, base_url=None, enabled=True, config=None):
        provider = self._new(code=code, display_name=display_name, adapter_type=adapter_type,
                             base_url=base_url, enabled=enabled, config=config or {})
        self.providers[code] = provider
        return provider

    async def list_models(self, provider_id=None, only_enabled=False):
        return list(self.models.get(provider_id, []))

    async def upsert_model(self, *, provider_id, model_name, config=None, **fields):
        existing = next((m for m in self.models.get(provider_id, []) if m.model_name == model_name), None)
        if existing is not None:
            return existing
        created = self._new(provider_id=provider_id, model_name=model_name, config=config or {}, **fields)
        self.models.setdefault(provider_id, []).append(created)
        return created

    async def list_api_keys(self, provider_id=None):
        return list(self.keys.get(provider_id, []))

    async def create_api_key(self, *, provider_id, alias, plaintext_key):
        created = self._new(provider_id=provider_id, alias=alias)
        self.keys.setdefault(provider_id, []).append(created)
        return created

    async def list_bindings(self, task_code=None):
        return list(self.bindings)

    async def upsert_binding(self, *, task_code, model_id, priority, notes=None):
        for binding in self.bindings:
            if binding.task_code == task_code and binding.model.id == model_id:
                binding.priority = priority
                return binding
        created = self._new(task_code=task_code, model=SimpleNamespace(id=model_id),
                            model_id=model_id, priority=priority, notes=notes)
        self.bindings.append(created)
        return created


def test_short_quota_wait_happens_only_in_worker_and_daily_quota_fails_fast():
    from app.services.studio.quota_retry import authoring_call
    from app.services.studio.jobs import active_lease
    async def run():
        call = AsyncMock(side_effect=[RateLimitedError("TPM", retry_after=2), {"ok": True}])
        token = active_lease.set(("job", "lease"))
        try:
            with patch("app.services.studio.quota_retry.asyncio.sleep", new=AsyncMock()) as sleep:
                assert await authoring_call(call) == {"ok": True}
                sleep.assert_awaited_once_with(2)
                with pytest.raises(RateLimitedError):
                    await authoring_call(AsyncMock(side_effect=RateLimitedError("TPD", retry_after=3600)))
                assert sleep.await_count == 1
        finally:
            active_lease.reset(token)
        with patch("app.services.studio.quota_retry.asyncio.sleep", new=AsyncMock()) as sleep:
            with pytest.raises(RateLimitedError):
                await authoring_call(AsyncMock(side_effect=RateLimitedError("quota")))
            sleep.assert_not_awaited()
    asyncio.run(run())
