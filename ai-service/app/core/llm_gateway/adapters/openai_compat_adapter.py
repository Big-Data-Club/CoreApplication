"""OpenAI-compatible adapter - works for Ollama, vLLM, LMStudio, TGI, OpenAI itself.
 
We don't pull a heavy SDK in; we call the REST endpoint with httpx. This keeps
the adapter's dependency surface minimal and lets operators point at arbitrary
self-hosted endpoints by setting the provider's base_url.
"""
from __future__ import annotations
 
from typing import Any, AsyncIterator, Optional
 
import httpx
 
from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.errors import AuthError, ContextLengthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, Usage
 
 
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
        # Ollama exposes both `/api/chat` (native) and `/v1/chat/completions`
        # (OpenAI-compatible). We always use the latter for portability.
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
 
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error calling {url}: {exc}", retryable=True) from exc
 
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
 
        data = resp.json()
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
        content, usage, raw = await self.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            extra=extra,
        )
        yield content, usage, raw
 
 
def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None