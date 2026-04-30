"""Google Gemini (AI Studio) adapter.
 
Uses the REST generateContent endpoint directly via httpx — no extra SDK.
The OpenAI-style messages array is translated into Gemini's `contents`
schema, and system messages become `systemInstruction`.
"""
from __future__ import annotations
 
from typing import Any
 
import httpx
 
from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.errors import AuthError, ContextLengthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, Usage
 
 
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
DEFAULT_API_VERSION = "v1beta"
TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=5.0)
 
 
class GeminiAdapter(LLMAdapter):
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
        version = self.provider_config.get("api_version") or DEFAULT_API_VERSION
        url = f"{base}/{version}/models/{model.model_name}:generateContent"
 
        system_text, contents = _translate(messages)
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode and model.supports_json:
            generation_config["responseMimeType"] = "application/json"
        for k in ("topP", "topK", "stopSequences"):
            if k in extra:
                generation_config[k] = extra[k]
 
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_text:
            body["systemInstruction"] = {"role": "system", "parts": [{"text": system_text}]}
        if "tools" in extra:
            body["tools"] = extra["tools"]
 
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
 
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error calling Gemini: {exc}", retryable=True) from exc
 
        if resp.status_code == 429:
            raise RateLimitedError(resp.text)
        if resp.status_code in (401, 403):
            raise AuthError(resp.text, status_code=resp.status_code)
        if resp.status_code >= 400:
            txt = resp.text
            if "context" in txt.lower() or "exceeds" in txt.lower():
                raise ContextLengthError(txt)
            raise ProviderError(txt, status_code=resp.status_code, retryable=resp.status_code >= 500)
 
        data = resp.json()
        candidates = data.get("candidates") or []
        content = ""
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            content = "".join(p.get("text", "") for p in parts if "text" in p)
 
        u = data.get("usageMetadata") or {}
        prompt_tok = int(u.get("promptTokenCount") or 0)
        completion_tok = int(u.get("candidatesTokenCount") or 0)
        total_tok = int(u.get("totalTokenCount") or (prompt_tok + completion_tok))
        return content, Usage(prompt_tokens=prompt_tok, completion_tokens=completion_tok, total_tokens=total_tok), data
 
 
def _translate(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Convert OpenAI-style messages into Gemini `contents` + systemInstruction text."""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
 
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        
        if isinstance(content, list):
            parts = []
            for item in content:
                if item.get("type") == "text":
                    parts.append({"text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        try:
                            header, b64 = url.split(",", 1)
                            mime_type = header.split(";")[0].replace("data:", "")
                            parts.append({
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": b64
                                }
                            })
                        except Exception:
                            parts.append({"text": f"[Image URL: {url}]"})
                    else:
                        parts.append({"text": f"[Image at {url}]"})
            contents.append({"role": gemini_role, "parts": parts})
        else:
            text = str(content)
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
 
    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Continue."}]})
    return ("\n\n".join(p for p in system_parts if p).strip(), contents)