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