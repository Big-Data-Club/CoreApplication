"""Neural speech providers. Credentials never accompany output downloads."""
from __future__ import annotations

import asyncio
from urllib.parse import quote, urlparse

import httpx

from app.core.llm_gateway.errors import AuthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, SpeechRequest

SPEECH_ADAPTERS = {"runway", "elevenlabs"}
MAX_AUDIO_BYTES = 32 * 1024 * 1024


def check_response(response: httpx.Response) -> None:
    status = response.status_code
    if status in (401, 403):
        raise AuthError("Speech provider rejected credentials", status_code=status)
    if status == 429:
        try:
            retry = float(response.headers.get("retry-after", "60"))
        except ValueError:
            retry = 60.0
        raise RateLimitedError("Speech provider quota reached", retry_after=retry)
    if status >= 400:
        raise ProviderError("Speech provider request failed", status_code=status, retryable=status >= 500)


async def _audio(client: httpx.AsyncClient, url: str, **kwargs) -> bytes:
    async with client.stream("GET", url, **kwargs) as response:
        check_response(response)
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > MAX_AUDIO_BYTES:
                raise ProviderError("Speech output exceeds size limit")
    if not data:
        raise ProviderError("Speech provider returned empty audio")
    return bytes(data)


async def synthesize(model: Model, api_key: str, req: SpeechRequest) -> bytes:
    config = model.config or {}
    voice = config.get("voice_id")
    try:
        speed = req.speed if req.speed is not None else float(config.get("speed", 0.97))
    except (TypeError, ValueError):
        raise ProviderError("Invalid model.config.speed")
    if not 0.7 <= speed <= 1.2:
        raise ProviderError("Speech speed must be 0.7–1.2")
    language = req.language.split("-")[0].lower()
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
        if model.adapter_type == "elevenlabs":
            if not voice:
                raise ProviderError("Configure ElevenLabs model.config.voice_id before synthesis")
            base = (model.base_url or "https://api.elevenlabs.io").rstrip("/")
            response = await client.post(
                f"{base}/v1/text-to-speech/{quote(str(voice), safe='')}",
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": api_key},
                json={"text": req.text, "model_id": model.model_name,
                      "language_code": language, "voice_settings": {"speed": speed}},
            )
            check_response(response)
            data = response.content
            if not data or len(data) > MAX_AUDIO_BYTES:
                raise ProviderError("Invalid speech output size")
            return data
        if model.adapter_type != "runway":
            raise ProviderError("Model does not support text_to_speech")
        base = (model.base_url or "https://api.dev.runwayml.com").rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}", "X-Runway-Version": "2024-11-06"}
        response = await client.post(f"{base}/v1/text_to_speech", headers=headers, json={
            "model": model.model_name, "promptText": req.text,
            "voice": {"type": "runway-preset", "presetId": voice or "Niki"},
            "languageCode": language, "speed": speed,
        })
        check_response(response)
        task_id = response.json().get("id")
        if not task_id:
            raise ProviderError("Runway returned no speech task id")
        # A single absolute deadline covers polling and download.
        async with asyncio.timeout(240):
            while True:
                response = await client.get(f"{base}/v1/tasks/{quote(str(task_id), safe='')}", headers=headers)
                check_response(response)
                task = response.json()
                if task.get("status") == "SUCCEEDED":
                    outputs = task.get("output") or []
                    if not outputs:
                        raise ProviderError("Runway task returned no audio")
                    url = outputs[0]
                    parsed = urlparse(url)
                    # Output URLs are supplied by Runway, never by browser input.
                    if parsed.scheme != "https" or not parsed.hostname:
                        raise ProviderError("Runway returned an invalid output URL")
                    return await _audio(client, url)
                if task.get("status") in {"FAILED", "CANCELED", "CANCELLED"}:
                    raise ProviderError("Runway speech task failed")
                await asyncio.sleep(2)
