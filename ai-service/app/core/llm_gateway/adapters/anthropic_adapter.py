"""Anthropic (Claude) adapter.
 
Uses the official /v1/messages REST endpoint directly via httpx so we don't
add an SDK dependency just for this. System messages are hoisted out of the
messages array into the top-level `system` field as Anthropic requires.
"""
from __future__ import annotations
 
from typing import Any
 
import httpx
 
from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.errors import AuthError, ContextLengthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, Usage
 
 
DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_VERSION = "2023-06-01"
TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=5.0)
 
 
class AnthropicAdapter(LLMAdapter):
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
        base = (self.base_url or DEFAULT_BASE_URL).rstrip("/")
        url = f"{base}/v1/messages"
        version = self.provider_config.get("anthropic_version") or DEFAULT_VERSION
 
        system_text, normalised = _normalise_messages(messages, json_mode=json_mode)
 
        body: dict[str, Any] = {
            "model": model.model_name,
            "messages": normalised,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_text:
            body["system"] = system_text
        for k in ("stop_sequences", "top_p", "top_k", "tools", "tool_choice"):
            if k in extra:
                body[k] = extra[k]
 
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": version,
            "Content-Type": "application/json",
        }
 
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error calling Anthropic: {exc}", retryable=True) from exc
 
        if resp.status_code == 429:
            raise RateLimitedError(resp.text)
        if resp.status_code in (401, 403):
            raise AuthError(resp.text, status_code=resp.status_code)
        if resp.status_code >= 400:
            txt = resp.text
            if "context" in txt.lower() and ("length" in txt.lower() or "window" in txt.lower()):
                raise ContextLengthError(txt)
            raise ProviderError(txt, status_code=resp.status_code, retryable=resp.status_code >= 500)
 
        data = resp.json()
        blocks = data.get("content") or []
        content = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        u = data.get("usage") or {}
        prompt_tok = int(u.get("input_tokens") or 0)
        completion_tok = int(u.get("output_tokens") or 0)
        usage = Usage(
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
            total_tokens=prompt_tok + completion_tok,
        )
        return content, usage, data
 
 
def _normalise_messages(
    messages: list[dict[str, Any]], *, json_mode: bool
) -> tuple[str, list[dict[str, Any]]]:
    """Hoist system messages; coalesce into Anthropic schema."""
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
 
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            continue
        # Anthropic accepts 'user' and 'assistant' only.
        if role not in ("user", "assistant"):
            role = "user"
            
        if isinstance(content, list):
            parts = []
            for item in content:
                if item.get("type") == "text":
                    parts.append({"type": "text", "text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        try:
                            header, b64 = url.split(",", 1)
                            mime_type = header.split(";")[0].replace("data:", "")
                            parts.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": b64
                                }
                            })
                        except Exception:
                            parts.append({"type": "text", "text": f"[Image URL: {url}]"})
                    else:
                        parts.append({"type": "text", "text": f"[Image at {url}]"})
            out.append({"role": role, "content": parts})
        else:
            out.append({"role": role, "content": str(content)})
 
    if json_mode:
        system_parts.append(
            "You MUST respond with a single valid JSON document and no prose, "
            "code fences, or markdown around it."
        )
 
    # Anthropic requires the conversation to start with a user message.
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "Continue."})
 
    return ("\n\n".join(p for p in system_parts if p).strip(), out)