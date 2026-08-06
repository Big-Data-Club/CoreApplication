"""Provider-agnostic exception hierarchy for the LLM gateway."""
from __future__ import annotations
 
 
class LLMGatewayError(Exception):
    """Base class for gateway errors."""
 
 
class NoModelAvailableError(LLMGatewayError):
    """Raised when no model in the fallback chain for a task is usable."""
 
 
class NoKeyAvailableError(LLMGatewayError):
    """Raised when every API key for a provider is disabled/cooling down."""
 
 
class ProviderError(LLMGatewayError):
    """Upstream provider returned an unexpected error."""
 
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
 
 
class RateLimitedError(ProviderError):
    """Provider returned a 429 / quota-exhausted signal."""
 
    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message, status_code=429, retryable=True)
        self.retry_after = retry_after
 
 
class AuthError(ProviderError):
    """Provider returned 401/403 - the API key is bad."""
 
    def __init__(self, message: str, *, status_code: int = 401):
        super().__init__(message, status_code=status_code, retryable=False)
 
 
class ContextLengthError(ProviderError):
    """Prompt exceeds the model's context window."""
 
    def __init__(self, message: str):
        super().__init__(message, status_code=400, retryable=False)
 
 
class EmptyCompletionError(ProviderError):
    """Provider returned a successful HTTP response but empty content.
 
    This is distinct from a network or key failure: the API key is healthy,
    so the gateway must NOT penalise it.  The most common cause on reasoning
    models is the completion budget being exhausted by chain-of-thought tokens
    before any visible output is produced.
 
    The gateway raises this instead of treating an empty response as success
    so the fallback chain can try the next model, and so upstream callers can
    surface a 502 rather than a misleading 422.
    """
 
    def __init__(self, message: str, *, finish_reason: str | None = None):
        super().__init__(message, status_code=502, retryable=False)
        self.finish_reason = finish_reason
 
 
class StructuredOutputError(LLMGatewayError):
    """Model failed to produce valid structured output after all retries.
 
    Raised by ``chat_complete_structured`` when every attempt yields a
    response that cannot be parsed or validated against the target Pydantic
    model.  Callers should surface this as a 502 upstream error, not 422,
    because the client request was well-formed.
    """