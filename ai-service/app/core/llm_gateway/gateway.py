"""
LLMGateway - single entry point for every LLM call in the service.
 
Responsibilities:
  * Resolve the fallback chain for a task (ordered by binding priority).
  * Lease a healthy key from the KeyPool for the chosen provider.
  * Instantiate the right adapter, run the call, record usage.
  * On failure: mark the key (cooldown / invalid), try the next key or the
    next model in the chain, and log the fallback.
 
Callers normally invoke `gateway.chat(task=…, messages=…)`. The legacy
module `app.core.llm` still exposes `chat_complete`, `chat_complete_json`
and `chat_complete_structured`; they all delegate here so the existing
call sites get multi-model support for free.
"""
from __future__ import annotations
 
import logging
import time
from typing import Any, Optional
 
from app.core.llm_gateway.adapters import get_adapter_class
from app.core.config import get_settings
from app.core.llm_gateway.errors import (
    AuthError,
    ContextLengthError,
    EmptyCompletionError,
    LLMGatewayError,
    NoKeyAvailableError,
    NoModelAvailableError,
    ProviderError,
    RateLimitedError,
)
from app.core.llm_gateway.key_pool import LeasedKey, get_key_pool
from app.core.llm_gateway.registry import ModelRegistry, get_registry
from app.core.llm_gateway.types import ChatRequest, ChatResponse, TaskBinding, Usage
from app.core.llm_gateway.token_budget import estimate_messages_tokens
from app.core.llm_gateway.usage import record_usage
 
logger = logging.getLogger(__name__)
settings = get_settings()
 
 
# How many keys to try on the SAME model before moving to the next model.
# A failure from key[0] (rate-limit / auth) shouldn't abandon an otherwise
# healthy model - there may be 9 more keys to try.
MAX_KEYS_PER_MODEL = 3
 
 
class LLMGateway:
    def __init__(
        self,
        *,
        registry: Optional[ModelRegistry] = None,
    ) -> None:
        self.registry = registry or get_registry()
        self.key_pool = get_key_pool()
 
    # ── Public API ───────────────────────────────────────────────────────────
    async def chat(self, req: ChatRequest) -> ChatResponse:
        """Execute the request against the first successful model in the chain."""
        chain = await self._resolve_chain(req)
        if not chain:
            raise NoModelAvailableError(
                f"No model bindings configured for task '{req.task}'"
            )
 
        last_error: Exception | None = None
        attempt = 0
        for idx, binding in enumerate(chain):
            attempt += 1
            fallback_used = idx > 0
            try:
                return await self._call_binding(
                    binding=binding, req=req,
                    attempt_no=attempt, fallback_used=fallback_used,
                )
            except AuthError as exc:
                # AuthError is per-key; _call_binding already retried its own
                # key pool. We can still continue to other models.
                last_error = exc
                logger.warning(
                    "Model %s unusable for task=%s: auth error. Falling back.",
                    binding.model.model_name, req.task,
                )
                continue
            except NoKeyAvailableError as exc:
                last_error = exc
                logger.warning(
                    "No active key for provider=%s; moving to next model.",
                    binding.model.provider_code,
                )
                continue
            except RateLimitedError as exc:
                last_error = exc
                logger.warning(
                    "Model %s is rate-limited (task=%s). Falling back.",
                    binding.model.model_name, req.task,
                )
                continue
            except ContextLengthError as exc:
                # A bigger model might have more context - try the next one.
                last_error = exc
                continue
            except EmptyCompletionError as exc:
                # The model returned HTTP 200 but empty content (e.g. reasoning
                # exhausted the output budget). The API key is healthy; try
                # the next model in the chain.
                last_error = exc
                logger.warning(
                    "Empty completion from model=%s task=%s (finish_reason=%s). Falling back.",
                    binding.model.model_name, req.task, exc.finish_reason,
                )
                continue
            except ProviderError as exc:
                last_error = exc
                if exc.retryable:
                    continue
                # Non-retryable provider errors are not likely to succeed on
                # another model either, but we try one more time to be safe.
                if idx + 1 < len(chain):
                    continue
                raise
 
        if isinstance(last_error, LLMGatewayError):
            raise last_error
        raise NoModelAvailableError(
            f"All {len(chain)} models failed for task '{req.task}': {last_error!r}"
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[tuple[Optional[str], Optional[Usage], Any]]:
        """Stream the response from the first successful model in the chain."""
        chain = await self._resolve_chain(req)
        if not chain:
            raise NoModelAvailableError(
                f"No model bindings configured for task '{req.task}'"
            )

        last_error: Exception | None = None
        for idx, binding in enumerate(chain):
            attempt = idx + 1
            fallback_used = idx > 0
            try:
                # We use a nested generator to allow catching errors before/during the stream
                async for delta, usage, raw in self._stream_binding(
                    binding=binding, req=req,
                    attempt_no=attempt, fallback_used=fallback_used,
                ):
                    yield delta, usage, raw
                return  # Success
            except (AuthError, NoKeyAvailableError, RateLimitedError, ContextLengthError) as exc:
                last_error = exc
                logger.warning(
                    "Model %s failed at stream start (task=%s, err=%s). Falling back.",
                    binding.model.model_name, req.task, exc,
                )
                continue
            except ProviderError as exc:
                last_error = exc
                if exc.retryable or idx + 1 < len(chain):
                    continue
                raise

        if isinstance(last_error, LLMGatewayError):
            raise last_error
        raise NoModelAvailableError(
            f"All {len(chain)} models failed for task '{req.task}': {last_error!r}"
        )
 
    # ── Chain resolution ─────────────────────────────────────────────────────
    async def _resolve_chain(self, req: ChatRequest) -> list[TaskBinding]:
        chain = await self.registry.get_binding_chain(req.task)
 
        # Honour an explicit model_hint by surfacing it to the front of the chain,
        # if present among the task's bindings.
        if req.model_hint:
            hinted = [b for b in chain if b.model.model_name == req.model_hint]
            others = [b for b in chain if b.model.model_name != req.model_hint]
            if hinted:
                chain = hinted + others
        return chain
 
    # ── Per-model call with multi-key retry ──────────────────────────────────
    async def _call_binding(
        self,
        *,
        binding: TaskBinding,
        req: ChatRequest,
        attempt_no: int,
        fallback_used: bool,
    ) -> ChatResponse:
        model = binding.model
        adapter_cls = get_adapter_class(model.adapter_type)
 
        temperature = _resolve(
            req.temperature, binding.temperature, model.default_temperature,
        )
        requested_max_tokens = int(_resolve(
            req.max_tokens, binding.max_tokens, model.default_max_tokens,
        ))
        max_tokens = self._fit_completion_budget(req, model.context_window, requested_max_tokens)
        json_mode = (
            req.json_mode if req.json_mode is not None
            else binding.json_mode
        )
 
        last_key_error: Exception | None = None
        for _ in range(MAX_KEYS_PER_MODEL):
            lease = await self.key_pool.lease(model.provider_id)
            max_tokens = self._fit_completion_budget(
                req, model.context_window, requested_max_tokens, key_tpm_limit=lease.record.tpm_limit,
            )
            adapter = adapter_cls(
                api_key=lease.plaintext,
                base_url=model.base_url,
                provider_config=model.config,
            )
            start = time.monotonic()
            try:
                content, usage, raw = await adapter.chat(
                    model=model,
                    messages=req.messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    extra=req.extra,
                )
            except RateLimitedError as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                await self.key_pool.record_rate_limit(
                    lease.id, retry_after_seconds=exc.retry_after,
                )
                await self._log(
                    req=req, model=model, lease=lease, usage=Usage(),
                    latency_ms=elapsed, success=False,
                    fallback_used=fallback_used, attempt_no=attempt_no,
                    error_code="rate_limited", error_message=str(exc),
                )
                last_key_error = exc
                continue   # try another key on the same model
            except AuthError as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                logger.warning(
                    "LLM Gateway AuthError for task=%s model=%s provider=%s key_id=%d alias=%s: %s",
                    req.task, model.model_name, model.provider_code, lease.id, lease.record.alias, str(exc)
                )
                await self.key_pool.record_auth_failure(lease.id, str(exc))
                await self._log(
                    req=req, model=model, lease=lease, usage=Usage(),
                    latency_ms=elapsed, success=False,
                    fallback_used=fallback_used, attempt_no=attempt_no,
                    error_code="auth", error_message=str(exc),
                )
                last_key_error = exc
                continue
            except ContextLengthError as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                await self._log(
                    req=req, model=model, lease=lease, usage=Usage(),
                    latency_ms=elapsed, success=False,
                    fallback_used=fallback_used, attempt_no=attempt_no,
                    error_code="context_length", error_message=str(exc),
                )
                raise
            except ProviderError as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                logger.warning(
                    "LLM Gateway ProviderError for task=%s model=%s provider=%s key_id=%d alias=%s: %s",
                    req.task, model.model_name, model.provider_code, lease.id, lease.record.alias, str(exc)
                )
                await self.key_pool.record_generic_failure(lease.id, str(exc))
                await self._log(
                    req=req, model=model, lease=lease, usage=Usage(),
                    latency_ms=elapsed, success=False,
                    fallback_used=fallback_used, attempt_no=attempt_no,
                    error_code=f"provider_{exc.status_code or 'err'}",
                    error_message=str(exc),
                )
                if exc.retryable:
                    last_key_error = exc
                    continue
                raise
            except Exception as exc:  # pragma: no cover - defensive
                elapsed = int((time.monotonic() - start) * 1000)
                await self.key_pool.record_generic_failure(lease.id, str(exc))
                await self._log(
                    req=req, model=model, lease=lease, usage=Usage(),
                    latency_ms=elapsed, success=False,
                    fallback_used=fallback_used, attempt_no=attempt_no,
                    error_code="unexpected", error_message=repr(exc),
                )
                raise
 
            # Guard: reject empty completions before treating the call as
            # a success.  Reasoning models (e.g. GPT-OSS 120B on Groq) may
            # return HTTP 200 but an empty message.content when the output
            # budget is exhausted by chain-of-thought tokens.  We must NOT
            # record this as success or penalise the API key - the key is
            # healthy.  Raise EmptyCompletionError so the outer loop can
            # fall back to the next model in the chain.
            finish_reason = _extract_finish_reason(raw)
            has_tool_calls = _has_tool_calls(raw)
            valid_tool_response = bool(req.extra.get("tools")) and has_tool_calls

            if not (content or "").strip() and not valid_tool_response:
                elapsed = int((time.monotonic() - start) * 1000)
                choices = _get_field(raw, "choices")
                first_choice = choices[0] if (choices and isinstance(choices, (list, tuple)) and len(choices) > 0) else None
                msg = _get_field(first_choice, "message")
                reasoning = _get_field(msg, "reasoning") or _get_field(msg, "reasoning_content") or ""
                reasoning_len = len(reasoning) if isinstance(reasoning, str) else 0
                logger.warning(
                    "Empty completion from provider: task=%s model=%s "
                    "finish_reason=%s completion_tokens=%d reasoning_len=%d",
                    req.task, model.model_name,
                    finish_reason, usage.completion_tokens, reasoning_len,
                )
                await self._log(
                    req=req, model=model, lease=lease, usage=usage,
                    latency_ms=elapsed, success=False,
                    fallback_used=fallback_used, attempt_no=attempt_no,
                    error_code="empty_completion",
                    error_message=(
                        f"Provider returned empty content; "
                        f"finish_reason={finish_reason}; "
                        f"completion_tokens={usage.completion_tokens}"
                    ),
                )
                # Do not call record_generic_failure: the key is healthy.
                raise EmptyCompletionError(
                    f"Provider returned an empty completion "
                    f"(finish_reason={finish_reason}, "
                    f"completion_tokens={usage.completion_tokens})",
                    finish_reason=finish_reason,
                )

            # Success path
            elapsed = int((time.monotonic() - start) * 1000)
            await self.key_pool.record_success(
                lease.id, tokens_used=usage.total_tokens,
            )
            await self._log(
                req=req, model=model, lease=lease, usage=usage,
                latency_ms=elapsed, success=True,
                fallback_used=fallback_used, attempt_no=attempt_no,
            )
            return ChatResponse(
                content=content,
                model=model,
                api_key_id=lease.id,
                usage=usage,
                latency_ms=elapsed,
                fallback_used=fallback_used,
                attempt_no=attempt_no,
                raw=raw,
            )
 
        # Exhausted MAX_KEYS_PER_MODEL without success - bubble up so the outer
        # loop can try the next model in the chain.
        if last_key_error is None:
            raise NoKeyAvailableError(
                f"No usable key for provider={model.provider_code}"
            )
        raise last_key_error

    async def _stream_binding(
        self,
        *,
        binding: TaskBinding,
        req: ChatRequest,
        attempt_no: int,
        fallback_used: bool,
    ) -> AsyncIterator[tuple[Optional[str], Optional[Usage], Any]]:
        model = binding.model
        adapter_cls = get_adapter_class(model.adapter_type)

        temperature = _resolve(
            req.temperature, binding.temperature, model.default_temperature,
        )
        requested_max_tokens = int(_resolve(
            req.max_tokens, binding.max_tokens, model.default_max_tokens,
        ))
        max_tokens = self._fit_completion_budget(req, model.context_window, requested_max_tokens)
        json_mode = (
            req.json_mode if req.json_mode is not None
            else binding.json_mode
        )

        last_key_error: Exception | None = None
        for _ in range(MAX_KEYS_PER_MODEL):
            lease = await self.key_pool.lease(model.provider_id)
            max_tokens = self._fit_completion_budget(
                req, model.context_window, requested_max_tokens, key_tpm_limit=lease.record.tpm_limit,
            )
            adapter = adapter_cls(
                api_key=lease.plaintext,
                base_url=model.base_url,
                provider_config=model.config,
            )
            start = time.monotonic()
            try:
                first_chunk = True
                total_usage = Usage()
                async for delta, usage, raw in adapter.stream(
                    model=model,
                    messages=req.messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    extra=req.extra,
                ):
                    if first_chunk:
                        first_chunk = False
                    if usage:
                        total_usage = usage
                    yield delta, usage, raw

                # Success path
                elapsed = int((time.monotonic() - start) * 1000)
                await self.key_pool.record_success(
                    lease.id, tokens_used=total_usage.total_tokens,
                )
                await self._log(
                    req=req, model=model, lease=lease, usage=total_usage,
                    latency_ms=elapsed, success=True,
                    fallback_used=fallback_used, attempt_no=attempt_no,
                )
                return

            except RateLimitedError as exc:
                if not first_chunk: raise
                await self.key_pool.record_rate_limit(lease.id, retry_after_seconds=exc.retry_after)
                last_key_error = exc
                continue
            except AuthError as exc:
                if not first_chunk: raise
                await self.key_pool.record_auth_failure(lease.id, str(exc))
                last_key_error = exc
                continue
            except ProviderError as exc:
                if not first_chunk: raise
                await self.key_pool.record_generic_failure(lease.id, str(exc))
                if exc.retryable:
                    last_key_error = exc
                    continue
                raise
            except Exception:
                if not first_chunk: raise
                raise

        if last_key_error: raise last_key_error
        raise NoKeyAvailableError(f"No usable key for provider={model.provider_code}")
 
    async def _log(self, **kwargs: Any) -> None:
        req: ChatRequest = kwargs.pop("req")
        model = kwargs.pop("model")
        lease: Optional[LeasedKey] = kwargs.pop("lease", None)
        usage: Usage = kwargs.pop("usage")
        await record_usage(
            task_code=req.task,
            model=model,
            api_key_id=lease.id if lease else None,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            request_id=req.request_id,
            **kwargs,
        )

    @staticmethod
    def _fit_completion_budget(
        req: ChatRequest,
        context_window: int,
        requested: int,
        *,
        key_tpm_limit: int | None = None,
    ) -> int:
        """Keep every upstream request under a safe TPM-sized envelope.

        Input is deliberately never sliced here.  Callers that handle large
        documents must use a map/reduce workflow so every source is preserved.
        Only unused completion headroom is trimmed.
        """
        prompt_tokens = estimate_messages_tokens(req.messages)
        request_budget = min(settings.llm_request_token_budget, context_window)
        if key_tpm_limit:
            # Keep a small guard band for provider-side accounting/tokenizer
            # differences. Admins manage this limit per key in the gateway UI.
            request_budget = min(request_budget, max(256, int(key_tpm_limit * 0.9)))
        available = request_budget - prompt_tokens
        if available < settings.llm_min_completion_tokens:
            raise ContextLengthError(
                "Prompt preflight exceeds the safe request budget "
                f"({prompt_tokens} estimated input tokens; budget={request_budget}). "
                "Use a coverage-preserving hierarchical reduction instead of truncating source material."
            )
        return min(requested, available)
 
 
def _resolve(*values: Any) -> Any:
    """Return the first non-None value."""
    for v in values:
        if v is not None:
            return v
    return None


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_finish_reason(raw: Any) -> str | None:
    """Best-effort extraction of finish_reason from any provider response."""
    try:
        choices = _get_field(raw, "choices")
        if choices and isinstance(choices, (list, tuple)) and len(choices) > 0:
            return _get_field(choices[0], "finish_reason")
    except Exception:
        pass
    return None


def _has_tool_calls(raw: Any) -> bool:
    """Return True when the response contains at least one tool call."""
    try:
        choices = _get_field(raw, "choices")
        if not choices or not isinstance(choices, (list, tuple)) or len(choices) == 0:
            return False
        message = _get_field(choices[0], "message")
        tool_calls = _get_field(message, "tool_calls")
        return bool(tool_calls)
    except Exception:
        return False
 
 
# ── Singleton ──────────────────────────────────────────────────────────────
_gateway: Optional[LLMGateway] = None
 
 
def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
 
 
def reset_gateway() -> None:
    """Called by `llm.reset_async_clients` to drop cached state in a new loop."""
    global _gateway
    _gateway = None
