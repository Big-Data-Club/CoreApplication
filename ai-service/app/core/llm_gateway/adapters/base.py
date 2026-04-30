"""Common adapter interface. Each provider subclass implements `chat`."""
from __future__ import annotations
 
import abc
from typing import Any, Optional
 
from app.core.llm_gateway.types import ChatResponse, Model, Usage
 
 
class LLMAdapter(abc.ABC):
    """
    Stateless facade around a provider's chat endpoint.
 
    Adapters are instantiated per-call so they can carry the leased API key
    cleanly. They must NOT cache secrets across calls.
    """
 
    def __init__(self, *, api_key: str, base_url: Optional[str] = None, provider_config: Optional[dict[str, Any]] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.provider_config = provider_config or {}
 
    @abc.abstractmethod
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
        """Return (content, usage, raw_response)."""
        raise NotImplementedError

    @abc.abstractmethod
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
        """Yield (delta_text, final_usage_if_any, raw_chunk)."""
        raise NotImplementedError
        yield  # type: ignore
 
    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _build_response(
        *,
        content: str,
        model: Model,
        api_key_id: int,
        usage: Usage,
        latency_ms: int,
        fallback_used: bool,
        attempt_no: int,
        raw: Any = None,
    ) -> ChatResponse:
        return ChatResponse(
            content=content,
            model=model,
            api_key_id=api_key_id,
            usage=usage,
            latency_ms=latency_ms,
            fallback_used=fallback_used,
            attempt_no=attempt_no,
            raw=raw,
        )