"""Groq adapter.
 
Uses `groq.AsyncGroq` directly (already a project dependency) rather than
sharing the legacy singleton in `app.core.llm`, so each call can use an
admin-configurable key.
"""
from __future__ import annotations
 
from typing import Any, AsyncIterator, Optional
import logging
 
from groq import AsyncGroq
from groq._exceptions import APIStatusError, AuthenticationError, RateLimitError
 
from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.errors import AuthError, ContextLengthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, Usage
 
logger = logging.getLogger(__name__)
 
 
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
 
        messages_copy = [dict(m) for m in messages]
        kwargs: dict[str, Any] = {
            "model": model.model_name,
            "messages": messages_copy,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode and model.supports_json:
            kwargs["response_format"] = {"type": "json_object"}
            has_json = any("json" in str(m.get("content") or "").lower() for m in messages_copy)
            if not has_json:
                system_msg = next((m for m in messages_copy if m.get("role") == "system"), None)
                if system_msg:
                    system_msg["content"] = (system_msg.get("content") or "") + " [Output must be in JSON format]"
                elif messages_copy:
                    messages_copy[0]["content"] = (messages_copy[0].get("content") or "") + " [Output must be in JSON format]"
        # Pass-through for tool calling / streaming etc.
        for k in ("tools", "tool_choice", "stream", "stop", "top_p"):
            if k in extra:
                kwargs[k] = extra[k]
 
        try:
            response = await client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            raise RateLimitedError(str(exc), retry_after=self._get_retry_after(exc)) from exc
        except AuthenticationError as exc:
            raise AuthError(str(exc)) from exc
        except APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            try:
                detail = exc.response.json()
                logger.error("Groq APIStatusError in chat status=%s detail=%s", status, detail)
            except Exception:
                pass
            msg = str(exc)
            if status in (401, 403):
                raise AuthError(msg, status_code=status) from exc
            if status == 429:
                raise RateLimitedError(msg, retry_after=self._get_retry_after(exc)) from exc
            if status == 400:
                msg_lower = msg.lower()
                if "context_length" in msg_lower:
                    raise ContextLengthError(msg) from exc
                if "organization_restricted" in msg_lower:
                    raise AuthError(msg, status_code=status) from exc
            raise ProviderError(msg, status_code=status) from exc
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
        client = AsyncGroq(api_key=self.api_key, base_url=self.base_url, max_retries=0) if self.base_url \
            else AsyncGroq(api_key=self.api_key, max_retries=0)

        messages_copy = [dict(m) for m in messages]
        kwargs: dict[str, Any] = {
            "model": model.model_name,
            "messages": messages_copy,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if json_mode and model.supports_json:
            kwargs["response_format"] = {"type": "json_object"}
            has_json = any("json" in str(m.get("content") or "").lower() for m in messages_copy)
            if not has_json:
                system_msg = next((m for m in messages_copy if m.get("role") == "system"), None)
                if system_msg:
                    system_msg["content"] = (system_msg.get("content") or "") + " [Output must be in JSON format]"
                elif messages_copy:
                    messages_copy[0]["content"] = (messages_copy[0].get("content") or "") + " [Output must be in JSON format]"
        for k in ("tools", "tool_choice", "stop", "top_p"):
            if k in extra:
                kwargs[k] = extra[k]

        try:
            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                content = delta.content if delta else None
                usage = None
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = Usage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
                yield content, usage, chunk
        except RateLimitError as exc:
            raise RateLimitedError(str(exc), retry_after=self._get_retry_after(exc)) from exc
        except AuthenticationError as exc:
            raise AuthError(str(exc)) from exc
        except APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            try:
                detail = exc.response.json()
                logger.error("Groq APIStatusError in stream status=%s detail=%s", status, detail)
            except Exception:
                pass
            if status == 429:
                raise RateLimitedError(str(exc), retry_after=self._get_retry_after(exc)) from exc
            raise ProviderError(str(exc), status_code=status) from exc
        finally:
            try:
                await client.close()
            except Exception:
                pass

    def _get_retry_after(self, exc: Any) -> float | None:
        """Extract retry-after from Groq error headers."""
        try:
            headers = getattr(exc, "headers", {})
            # Groq often uses 'retry-after-ms' or 'retry-after'
            if "retry-after-ms" in headers:
                return float(headers["retry-after-ms"]) / 1000.0
            if "retry-after" in headers:
                return float(headers["retry-after"])
        except (ValueError, TypeError):
            pass
        return None