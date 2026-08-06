"""Groq adapter.

Uses `groq.AsyncGroq` directly (already a project dependency) rather than
sharing the legacy singleton in `app.core.llm`, so each call can use an
admin-configurable key.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Optional
import logging

from groq import AsyncGroq
from groq._exceptions import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.errors import AuthError, ContextLengthError, ProviderError, RateLimitedError
from app.core.llm_gateway.types import Model, Usage

logger = logging.getLogger(__name__)

# Extra keys forwarded verbatim to the Groq API.
# reasoning_effort / include_reasoning control GPT-OSS 120B chain-of-thought
# budget; seed provides deterministic sampling where supported.
_PASSTHROUGH_KEYS = (
    "tools",
    "tool_choice",
    "stream",
    "stop",
    "top_p",
    "seed",
    "reasoning_effort",
    "include_reasoning",
)


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
            # Groq deprecated `max_tokens`; `max_completion_tokens` is the
            # current field and correctly scopes only the output budget.
            "max_completion_tokens": max_tokens,
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

        for k in _PASSTHROUGH_KEYS:
            if k in extra:
                kwargs[k] = extra[k]

        try:
            response = await client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            raise RateLimitedError(str(exc), retry_after=self._get_retry_after(exc)) from exc
        except AuthenticationError as exc:
            raise AuthError(str(exc)) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            # Transient network failure; a different key or model may succeed.
            raise ProviderError(
                f"Groq network error: {exc}",
                retryable=True,
            ) from exc
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
            # 5xx and transient 4xx (408/409/425) are safe to retry.
            retryable = status in (408, 409, 425) or (status is not None and status >= 500)
            raise ProviderError(msg, status_code=status, retryable=retryable) from exc
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

        # Diagnostic metadata useful for debugging empty completions on
        # reasoning models (e.g. GPT-OSS 120B where reasoning tokens consume
        # the output budget before any visible content is produced).
        finish_reason = getattr(choice, "finish_reason", None)
        reasoning = getattr(choice.message, "reasoning", None)
        reasoning_len = len(reasoning) if isinstance(reasoning, str) else 0
        logger.debug(
            "Groq chat complete: model=%s finish_reason=%s content_len=%d "
            "reasoning_len=%d completion_tokens=%d",
            model.model_name, finish_reason, len(content),
            reasoning_len, usage.completion_tokens,
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
            "max_completion_tokens": max_tokens,
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

        for k in _PASSTHROUGH_KEYS:
            if k in extra and k != "stream":
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
        except (APIConnectionError, APITimeoutError) as exc:
            raise ProviderError(f"Groq network error: {exc}", retryable=True) from exc
        except APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            try:
                detail = exc.response.json()
                logger.error("Groq APIStatusError in stream status=%s detail=%s", status, detail)
            except Exception:
                pass
            if status == 429:
                raise RateLimitedError(str(exc), retry_after=self._get_retry_after(exc)) from exc
            retryable = status in (408, 409, 425) or (status is not None and status >= 500)
            raise ProviderError(str(exc), status_code=status, retryable=retryable) from exc
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
