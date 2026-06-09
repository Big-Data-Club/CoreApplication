"""
ai-service/app/agents/events.py

SSE Event Schema for the Agent chat system.

Defined once and used by the ReAct loop, FastAPI endpoint, and frontend.
Each event type maps to a specific frontend rendering behaviour:

  text_delta     -> append to streaming text bubble
  thinking       -> show reasoning indicator (collapsible)
  scope          -> show resolved course scope (which course is in focus)
  tool_start     -> show tool loading spinner
  tool_result    -> show tool result summary
  ui_component   -> render dynamic widget (QuizPreview, Chart, etc.)
  clarification  -> show clarification question with options
  hitl_request   -> show human-in-the-loop approval widget
  done           -> mark message as complete
  error          -> show error state
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class AgentEventType(str, Enum):
    TEXT_DELTA     = "text_delta"
    THINKING       = "thinking"
    SCOPE          = "scope"
    TOOL_START     = "tool_start"
    TOOL_RESULT    = "tool_result"
    UI_COMPONENT   = "ui_component"
    CLARIFICATION  = "clarification"
    HITL_REQUEST   = "hitl_request"
    SESSION        = "session"
    TITLE_UPDATE   = "title_update"
    SUBAGENT_SPAWN = "subagent_spawn"
    SUBAGENT_THINK = "subagent_thinking"
    SUBAGENT_DONE  = "subagent_done"
    SUBAGENT_ERROR = "subagent_error"
    CRITIQUE_PHASE = "critique_phase"
    CONSOLIDATION  = "context_consolidation"
    DONE           = "done"
    ERROR          = "error"


class AgentEvent(BaseModel):
    type: AgentEventType
    data: Any
    session_id: str
    turn_id: Optional[str] = None

    def to_sse(self) -> str:
        """Format as SSE data line."""
        import json
        payload = self.model_dump(mode="json")
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
