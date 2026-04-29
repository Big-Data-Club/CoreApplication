"""Groq adapter.
 
Uses `groq.AsyncGroq` directly (already a project dependency) rather than
sharing the legacy singleton in `app.core.llm`, so each call can use an
admin-configurable key.
"""
from __future__ import annotations
 
from typing import Any
 
from groq import AsyncGroq
from groq._exceptions import APIStatusError, AuthenticationError, RateLimitError
 
from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.errors import AuthError, ContextLengthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, Usage
 
 
class GroqAdapter(LLMAdapter):
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
        client = AsyncGroq(api_key=self.api_key, base_url=self.base_url, max_retries=0) if self.base_url \
            else AsyncGroq(api_key=self.api_key, max_retries=0)
 
        kwargs: dict[str, Any] = {
            "model": model.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode and model.supports_json:
            kwargs["response_format"] = {"type": "json_object"}
        # Pass-through for tool calling / streaming etc.
        for k in ("tools", "tool_choice", "stream", "stop", "top_p"):
            if k in extra:
                kwargs[k] = extra[k]
 
        try:
            response = await client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            raise RateLimitedError(str(exc)) from exc
        except AuthenticationError as exc:
            raise AuthError(str(exc)) from exc
        except APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            msg = str(exc)
            if status in (401, 403):
                raise AuthError(msg, status_code=status) from exc
            if status == 429:
                raise RateLimitedError(msg) from exc
            if status == 400:
                msg_lower = msg.lower()
                if "context_length" in msg_lower:
                    raise ContextLengthError(msg) from exc
                if "organization_restricted" in msg_lower:
                    raise AuthError(msg, status_code=status) from exc
            raise ProviderError(msg, status_code=status, retryable=(status or 0) >= 500) from exc
        finally:
            try:
                await client.close()
            except Exception:
                pass
 
        choice = response.choices[0]
        content = choice.message.content or ""
        usage_obj = getattr(response, "usage", None)
        usage = Usage(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
        )
        return content, usage, response