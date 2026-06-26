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
from app.core.llm_gateway.errors import (
    AuthError,
    ContextLengthError,
    LLMGatewayError,
    NoKeyAvailableError,
    NoModelAvailableError,
    ProviderError,
    RateLimitedError,
)
from app.core.llm_gateway.key_pool import LeasedKey, get_key_pool
from app.core.llm_gateway.registry import ModelRegistry, get_registry
from app.core.llm_gateway.types import ChatRequest, ChatResponse, TaskBinding, Usage
from app.core.llm_gateway.usage import record_usage
 
logger = logging.getLogger(__name__)
 
 
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
            except ContextLengthError:
                # A bigger model might have more context - try the next one.
                last_error = ContextLengthError("Context window exceeded")
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
        max_tokens = int(_resolve(
            req.max_tokens, binding.max_tokens, model.default_max_tokens,
        ))
        json_mode = (
            req.json_mode if req.json_mode is not None
            else binding.json_mode
        )
 
        last_key_error: Exception | None = None
        for _ in range(MAX_KEYS_PER_MODEL):
            lease = await self.key_pool.lease(model.provider_id)
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
        max_tokens = int(_resolve(
            req.max_tokens, binding.max_tokens, model.default_max_tokens,
        ))
        json_mode = (
            req.json_mode if req.json_mode is not None
            else binding.json_mode
        )

        last_key_error: Exception | None = None
        for _ in range(MAX_KEYS_PER_MODEL):
            lease = await self.key_pool.lease(model.provider_id)
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
 
 
def _resolve(*values: Any) -> Any:
    """Return the first non-None value."""
    for v in values:
        if v is not None:
            return v
    return None
 
 
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