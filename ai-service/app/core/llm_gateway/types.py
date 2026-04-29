"""Shared dataclasses / Pydantic models for the LLM gateway."""
from __future__ import annotations
 
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional
 
 
# ── Task codes used throughout the codebase ──────────────────────────────────
# Keep this list in sync with the default bindings created on startup.
TASK_CHAT             = "chat"              # short explanations, casual tutor
TASK_QUIZ_GEN         = "quiz_gen"          # high-stakes quiz generation
TASK_MICRO_LESSON_GEN = "micro_lesson_gen"  # generating micro-lessons from nodes
TASK_DIAGNOSIS        = "diagnosis"         # error diagnosis for wrong answers
TASK_FLASHCARD_GEN    = "flashcard_gen"
TASK_AGENT_REACT      = "agent_react"       # teacher/mentor tool-calling loop
TASK_AGENT_ROUTER     = "agent_router"      # tiny classifier used to pick agent
TASK_CLARIFICATION    = "clarification"
TASK_GRAPH_LINK       = "graph_link"        # knowledge graph relation extraction
TASK_MEMORY_COMPRESS  = "memory_compress"
TASK_LANGUAGE_DETECT  = "language_detect"
TASK_NODE_EXTRACT     = "node_extract"
TASK_VLM_DESCRIBE     = "vlm_describe"      # vision model image description
 
ALL_TASK_CODES: tuple[str, ...] = (
    TASK_CHAT, TASK_QUIZ_GEN, TASK_MICRO_LESSON_GEN, TASK_DIAGNOSIS, TASK_FLASHCARD_GEN,
    TASK_AGENT_REACT, TASK_AGENT_ROUTER, TASK_CLARIFICATION,
    TASK_GRAPH_LINK, TASK_MEMORY_COMPRESS, TASK_LANGUAGE_DETECT,
    TASK_NODE_EXTRACT, TASK_VLM_DESCRIBE,
)
 
 
# ── Provider / model / key data objects ─────────────────────────────────────
@dataclass(slots=True)
class Provider:
    id: int
    code: str
    display_name: str
    adapter_type: str
    base_url: Optional[str]
    enabled: bool
    config: dict[str, Any]
 
 
@dataclass(slots=True)
class Model:
    id: int
    provider_id: int
    provider_code: str
    adapter_type: str
    base_url: Optional[str]
    model_name: str
    display_name: Optional[str]
    family: Optional[str]
    context_window: int
    supports_json: bool
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    input_cost_per_1k: float
    output_cost_per_1k: float
    default_temperature: float
    default_max_tokens: int
    enabled: bool
    config: dict[str, Any]
 
 
@dataclass(slots=True)
class ApiKey:
    id: int
    provider_id: int
    alias: str
    encrypted_key: str
    fingerprint: str
    status: Literal["active", "cooldown", "disabled", "invalid"]
    rpm_limit: Optional[int]
    tpm_limit: Optional[int]
    daily_token_limit: Optional[int]
    used_today_requests: int
    used_today_tokens: int
    cooldown_until: Optional[datetime]
    consecutive_failures: int
 
 
@dataclass(slots=True)
class TaskBinding:
    id: int
    task_code: str
    model: Model
    priority: int
    temperature: Optional[float]
    max_tokens: Optional[int]
    json_mode: bool
    pinned: bool
    enabled: bool
 
 
# ── Gateway request / response ──────────────────────────────────────────────
@dataclass(slots=True)
class ChatRequest:
    task: str
    messages: list[dict[str, Any]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    json_mode: Optional[bool] = None
    request_id: Optional[str] = None
    # Model hint — if set, gateway will try to honour it before consulting bindings.
    # Accepts either a `model_name` string (legacy) or an explicit Model id.
    model_hint: Optional[str] = None
    # Extra provider-specific kwargs (e.g. tools, tool_choice). Passed through
    # to the adapter verbatim.
    extra: dict[str, Any] = field(default_factory=dict)
 
 
@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
 
 
@dataclass(slots=True)
class ChatResponse:
    content: str
    model: Model
    api_key_id: int
    usage: Usage
    latency_ms: int
    fallback_used: bool
    attempt_no: int
    raw: Any = None   # raw provider response, useful for streaming / tool calls