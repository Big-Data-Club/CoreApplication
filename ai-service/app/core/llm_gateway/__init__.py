"""
LLM multi-provider gateway.
 
Public surface
--------------
    from app.core.llm_gateway import (
        get_gateway, ChatRequest, ChatResponse,
        TASK_CHAT, TASK_QUIZ_GEN, ...
    )
 
The `get_gateway()` singleton holds the repository + key pool; call
`reset_gateway()` after entering a fresh asyncio loop (Celery worker pattern).
"""
from app.core.llm_gateway.errors import (
    AuthError,
    ContextLengthError,
    LLMGatewayError,
    NoKeyAvailableError,
    NoModelAvailableError,
    ProviderError,
    RateLimitedError,
)
from app.core.llm_gateway.gateway import LLMGateway, get_gateway, reset_gateway
from app.core.llm_gateway.key_pool import KeyPool, get_key_pool
from app.core.llm_gateway.registry import ModelRegistry, get_registry
from app.core.llm_gateway.types import (
    ALL_TASK_CODES,
    ApiKey,
    ChatRequest,
    ChatResponse,
    Model,
    Provider,
    TASK_AGENT_REACT,
    TASK_AGENT_ROUTER,
    TASK_CHAT,
    TASK_CLARIFICATION,
    TASK_DIAGNOSIS,
    TASK_FLASHCARD_GEN,
    TASK_GRAPH_LINK,
    TASK_LANGUAGE_DETECT,
    TASK_MEMORY_COMPRESS,
    TASK_MICRO_LESSON_GEN,
    TASK_MICRO_QUIZ_GEN,
    TASK_NODE_EXTRACT,
    TASK_QUIZ_GEN,
    TASK_VLM_DESCRIBE,
    TASK_SECTION_OVERVIEW_GEN,
    TaskBinding,
    Usage,
)
 
__all__ = [
    # core
    "LLMGateway", "get_gateway", "reset_gateway",
    "ModelRegistry", "get_registry",
    "KeyPool", "get_key_pool",
    # types
    "ChatRequest", "ChatResponse", "Usage",
    "Provider", "Model", "ApiKey", "TaskBinding",
    # task codes
    "ALL_TASK_CODES",
    "TASK_CHAT", "TASK_QUIZ_GEN", "TASK_DIAGNOSIS", "TASK_FLASHCARD_GEN",
    "TASK_AGENT_REACT", "TASK_AGENT_ROUTER", "TASK_CLARIFICATION",
    "TASK_GRAPH_LINK", "TASK_MEMORY_COMPRESS", "TASK_LANGUAGE_DETECT",
    "TASK_NODE_EXTRACT", "TASK_MICRO_LESSON_GEN", "TASK_MICRO_QUIZ_GEN", "TASK_VLM_DESCRIBE",
    "TASK_SECTION_OVERVIEW_GEN",
    # errors
    "LLMGatewayError", "NoModelAvailableError", "NoKeyAvailableError",
    "ProviderError", "RateLimitedError", "AuthError", "ContextLengthError",
]