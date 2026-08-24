"""
ai-service/app/agents/tools/base_tool.py

Abstract base class for all Agent tools.

Every tool MUST:
  1. Declare `name`, `description`, and `parameters` (JSON Schema).
  2. Implement `execute(**kwargs) -> ToolResult`.
  3. Return a ToolResult with status, data, and optional ui_instruction.

The JSON Schema in `parameters` is sent to the LLM via function calling.
The LLM selects the tool and fills in the arguments.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel


def sanitize_query(value: Any, max_len: int = 240) -> str:
    """
    Normalise an LLM-supplied search query/concept.

    Small models love pasting the entire user request (or a whole topic
    outline) into the ``query`` argument. Search engines and embedding
    models both degrade badly on that, so we collapse whitespace and cap
    the length at a keyword-friendly size.
    """
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        cut = text.rfind(" ", 0, max_len)
        text = text[: cut if cut > int(max_len * 0.6) else max_len].rstrip(" ,;")
    return text


class ToolResult(BaseModel):
    """Standard result returned by every tool."""

    status: str
    """One of: 'success', 'error', 'pending_human_approval'."""

    data: Any
    """Raw data for the LLM to reason about."""

    message: str = ""
    """Human-readable summary of what happened."""

    ui_instruction: Optional[dict] = None
    """
    If set, the frontend renders a dynamic widget.
    Format: {"component": "QuizDraftPreview", "props": {...}}
    """


class BaseTool(ABC):
    """Abstract base for agent tools."""

    name: str = ""
    """Unique tool name (snake_case). Used in function calling."""

    description: str = ""
    """Description shown to the LLM. Should explain when to use this tool."""

    parameters: dict = {}
    """
    JSON Schema for function calling parameters.
    Example:
    {
        "type": "object",
        "properties": {
            "course_id": {"type": "integer", "description": "..."},
            "query": {"type": "string", "description": "..."},
        },
        "required": ["course_id", "query"]
    }
    """

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with validated arguments."""
        ...

    def to_function_schema(self) -> dict:
        """
        Convert to OpenAI-compatible function calling schema.

        This is passed to the LLM in the `tools` parameter.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
