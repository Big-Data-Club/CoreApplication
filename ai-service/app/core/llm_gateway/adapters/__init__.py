"""Adapter registry - maps `adapter_type` strings to concrete classes."""
from __future__ import annotations
 
from app.core.llm_gateway.adapters.anthropic_adapter import AnthropicAdapter
from app.core.llm_gateway.adapters.base import LLMAdapter
from app.core.llm_gateway.adapters.gemini_adapter import GeminiAdapter
from app.core.llm_gateway.adapters.groq_adapter import GroqAdapter
from app.core.llm_gateway.adapters.openai_compat_adapter import OpenAICompatAdapter
 
 
_ADAPTER_REGISTRY: dict[str, type[LLMAdapter]] = {
    "groq":          GroqAdapter,
    "anthropic":     AnthropicAdapter,
    "gemini":        GeminiAdapter,
    "ollama":        OpenAICompatAdapter,      # Ollama speaks OpenAI-compat
    "openai_compat": OpenAICompatAdapter,
    "openai":        OpenAICompatAdapter,      # same wire protocol
    "localhost":     OpenAICompatAdapter,      # alias for self-hosted
}
 
 
def get_adapter_class(adapter_type: str) -> type[LLMAdapter]:
    try:
        return _ADAPTER_REGISTRY[adapter_type]
    except KeyError as exc:
        raise ValueError(f"Unknown LLM adapter type: {adapter_type!r}") from exc
 
 
def supported_adapter_types() -> list[str]:
    return sorted(_ADAPTER_REGISTRY.keys())
 
 
__all__ = [
    "LLMAdapter",
    "GroqAdapter",
    "AnthropicAdapter",
    "GeminiAdapter",
    "OpenAICompatAdapter",
    "get_adapter_class",
    "supported_adapter_types",
]