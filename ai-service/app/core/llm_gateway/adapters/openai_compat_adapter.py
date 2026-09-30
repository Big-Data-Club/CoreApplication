"""OpenAI-compatible adapter - works for Ollama, vLLM, LMStudio, TGI, OpenAI itself.
 
We don't pull a heavy SDK in; we call the REST endpoint with httpx. This keeps
the adapter's dependency surface minimal and lets operators point at arbitrary
self-hosted endpoints by setting the provider's base_url.
"""
from __future__ import annotations
 
import logging
import json
from typing import Any, AsyncIterator, Optional
 
import httpx
 
from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.errors import AuthError, ContextLengthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, Usage
 
logger = logging.getLogger(__name__)
 
 
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)
 
 
class OpenAICompatAdapter(LLMAdapter):
    """Generic /v1/chat/completions client."""
 
    async def chat(
        self,
        *,
        model: Model,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        extra: dict[str, Any],
    ) -> tuple[str, Usage, Any]:
        base = (self.base_url or "http://localhost:11434").rstrip("/")
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"
 
        body: dict[str, Any] = {
            "model": model.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode and model.supports_json:
            body["response_format"] = {"type": "json_object"}
        for k in ("tools", "tool_choice", "stop", "top_p"):
            if k in extra:
                body[k] = extra[k]
 
        headers: dict[str, str] = {"Content-Type": "application/json"}
        # Ollama ignores the auth header, but sending an empty token is fine
        # for OpenAI-compatible servers too.
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Inject custom headers from config if provided (e.g. Cloudflare Access, Custom proxies)
        config_headers = self.provider_config.get("headers")
        if isinstance(config_headers, dict):
            for k, v in config_headers.items():
                headers[str(k)] = str(v)

 
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("OpenAICompatAdapter network error calling %s: %s", url, exc)
            raise ProviderError(f"Network error calling {url}: {exc}", retryable=True) from exc

        if resp.status_code >= 400:
            logger.warning(
                "OpenAICompatAdapter HTTP %d for url=%s model=%s: %s",
                resp.status_code, url, model.model_name, resp.text[:500]
            )

        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("retry-after"))
            raise RateLimitedError(resp.text, retry_after=retry_after)
        if resp.status_code in (401, 403):
            raise AuthError(resp.text, status_code=resp.status_code)
        if resp.status_code >= 400:
            txt = resp.text
            if "context" in txt.lower() and "length" in txt.lower():
                raise ContextLengthError(txt)
            raise ProviderError(
                txt, status_code=resp.status_code, retryable=resp.status_code >= 500
            )
 
        try:
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "OpenAICompatAdapter failed to parse JSON response from url=%s status=%d body=%r: %s",
                url, resp.status_code, resp.text[:500], exc
            )
            raise ProviderError(
                f"Invalid JSON response from {url} (status={resp.status_code}): {resp.text[:200]}",
                status_code=resp.status_code,
                retryable=True,
            ) from exc
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content")) or ""
        usage_obj = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_obj.get("prompt_tokens") or 0),
            completion_tokens=int(usage_obj.get("completion_tokens") or 0),
            total_tokens=int(usage_obj.get("total_tokens") or 0),
        )
        return content, usage, data

    async def stream(
        self,
        *,
        model: Model,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        extra: dict[str, Any],
    ) -> AsyncIterator[tuple[Optional[str], Optional[Usage], Any]]:
        """Relay OpenAI-compatible SSE chunks as they arrive.

        Calling :meth:`chat` here used to make every OpenAI-compatible model
        appear to stream while buffering its entire completion first.  Besides
        hiding useful progress from the learner, that turned a long generation
        into minutes of apparent inactivity.  Keep the response context open
        for the lifetime of this generator and pass text and tool-call deltas
        through unchanged so the ReAct loop can process them incrementally.
        """
        base = (self.base_url or "http://localhost:11434").rstrip("/")
        url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"

        body: dict[str, Any] = {
            "model": model.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if json_mode and model.supports_json:
            body["response_format"] = {"type": "json_object"}
        for key in ("tools", "tool_choice", "stop", "top_p"):
            if key in extra:
                body[key] = extra[key]

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        config_headers = self.provider_config.get("headers")
        if isinstance(config_headers, dict):
            headers.update({str(key): str(value) for key, value in config_headers.items()})

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode(errors="replace")
                        if response.status_code == 429:
                            raise RateLimitedError(
                                detail,
                                retry_after=_parse_retry_after(response.headers.get("retry-after")),
                            )
                        if response.status_code in (401, 403):
                            raise AuthError(detail, status_code=response.status_code)
                        if "context" in detail.lower() and "length" in detail.lower():
                            raise ContextLengthError(detail)
                        raise ProviderError(
                            detail,
                            status_code=response.status_code,
                            retryable=response.status_code >= 500,
                        )

                    # A few compatible gateways accept stream=true but return
                    # a regular JSON completion.  Preserve compatibility with
                    # those providers rather than silently ending with an
                    # empty answer.  Real SSE providers follow the path below.
                    content_type = response.headers.get("content-type", "").lower()
                    if "application/json" in content_type:
                        try:
                            chunk = json.loads((await response.aread()).decode())
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise ProviderError(
                                f"Invalid JSON stream response from {url}",
                                retryable=True,
                            ) from exc
                        choice = (chunk.get("choices") or [{}])[0]
                        content = ((choice.get("message") or {}).get("content")) or ""
                        usage_obj = chunk.get("usage") or {}
                        usage = Usage(
                            prompt_tokens=int(usage_obj.get("prompt_tokens") or 0),
                            completion_tokens=int(usage_obj.get("completion_tokens") or 0),
                            total_tokens=int(usage_obj.get("total_tokens") or 0),
                        )
                        yield content, usage, chunk
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":") or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            logger.warning("Ignoring malformed SSE chunk from %s", url)
                            continue

                        choices = chunk.get("choices") or []
                        delta = (choices[0].get("delta") or {}) if choices else {}
                        content = delta.get("content")
                        usage_obj = chunk.get("usage") or {}
                        usage = None
                        if usage_obj:
                            usage = Usage(
                                prompt_tokens=int(usage_obj.get("prompt_tokens") or 0),
                                completion_tokens=int(usage_obj.get("completion_tokens") or 0),
                                total_tokens=int(usage_obj.get("total_tokens") or 0),
                            )
                        yield content if isinstance(content, str) else None, usage, chunk
        except (AuthError, ContextLengthError, ProviderError, RateLimitedError):
            raise
        except httpx.HTTPError as exc:
            logger.warning("OpenAICompatAdapter stream error calling %s: %s", url, exc)
            raise ProviderError(f"Network error calling {url}: {exc}", retryable=True) from exc
 
 
def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
