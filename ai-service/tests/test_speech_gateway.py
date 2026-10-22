from __future__ import annotations

import asyncio
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
    async def run():
        custom = replace(model(), config={"voice_id": "custom", "speed": .9})
        registry = SimpleNamespace(
            get_provider_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
            list_models=AsyncMock(return_value=[custom]), list_bindings=AsyncMock(return_value=["admin"]),
            upsert_provider=AsyncMock(), upsert_model=AsyncMock(), upsert_binding=AsyncMock(),
        )
        await _bootstrap_speech(registry)
        registry.upsert_provider.assert_not_awaited()
        registry.upsert_model.assert_not_awaited()
        registry.upsert_binding.assert_not_awaited()
        assert custom.config == {"voice_id": "custom", "speed": .9}
    asyncio.run(run())


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
