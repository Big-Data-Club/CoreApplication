"""
ai-service/mcp/tool_adapter.py

Bridge between BDC's BaseTool/ToolRegistry and the MCP Tool protocol.

MCP Tool schema (tools/list response):
  {
    "name": "generate_content_draft",
    "description": "...",
    "inputSchema": {  ← JSON Schema, same shape as BaseTool.parameters
      "type": "object",
      "properties": {...},
      "required": [...]
    }
  }

MCP CallToolResult:
  {
    "content": [{"type": "text", "text": "..."}],
    "isError": false
  }

Strategy:
  - BaseTool.to_function_schema() already produces OpenAI function-calling
    format, which is structurally identical to MCP inputSchema.
  - BaseTool.execute() → ToolResult is converted to MCP CallToolResult.
  - All BDC tools (teacher + mentor) are exposed unless MCP_ALLOWED_TOOLS
    restricts the list.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.agents.tools.base_tool import ToolResult
from app.agents.tools.registry import (
    execute_tool,
    get_tools,
    get_tool_by_name,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SAFE_DEFAULT_TOOLS = {
    "list_accessible_courses",
    "list_my_courses",
    "list_knowledge_nodes",
    "search_course_materials",
    "create_course_section",
    "mcp_index_files",
    "mcp_create_course_from_files",
    "mcp_batch_generate_quiz",
    "mcp_generate_slide_deck",
    "mcp_create_lesson",
}
WRITE_TOOLS = {
    "create_course_section",
    "mcp_index_files",
    "mcp_create_course_from_files",
    "mcp_create_lesson",
}

COURSE_READ_TOOLS = {
    "list_knowledge_nodes",
    "search_course_materials",
}

COURSE_OWNER_TOOLS = {
    "create_course_section",
    "mcp_index_files",
    "mcp_batch_generate_quiz",
    "mcp_create_lesson",
}


# ---------------------------------------------------------------------------
# Allowed-tool whitelist
# ---------------------------------------------------------------------------

def _build_allowed_set() -> set[str]:
    """
    Return the configured allowlist, falling back to a conservative default.
    """
    raw = settings.mcp_allowed_tools.strip()
    if not raw:
        return set(SAFE_DEFAULT_TOOLS)
    return {name.strip() for name in raw.split(",") if name.strip()}


_ALLOWED_TOOLS: set[str] = _build_allowed_set()


def _is_allowed(tool_name: str) -> bool:
    return tool_name in _ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# MCP schema helpers
# ---------------------------------------------------------------------------

def get_mcp_tool_list() -> list[dict]:
    """
    Return all BDC tools as MCP tool descriptors.

    Aggregates teacher + mentor tools, de-duplicates shared tools,
    and applies the MCP_ALLOWED_TOOLS whitelist.
    """
    seen: set[str] = set()
    mcp_tools: list[dict] = []

    for agent_type in ("teacher", "mentor"):
        for tool in get_tools(agent_type):
            if tool.name in seen:
                continue
            seen.add(tool.name)

            if not _is_allowed(tool.name):
                continue

            fn_schema = tool.to_function_schema()
            mcp_tools.append({
                "name": fn_schema["function"]["name"],
                "description": fn_schema["function"]["description"],
                "inputSchema": fn_schema["function"]["parameters"],
                "annotations": {
                    "readOnlyHint": tool.name not in WRITE_TOOLS,
                    "destructiveHint": False,
                    "idempotentHint": tool.name in {"list_my_courses", "list_knowledge_nodes", "search_course_materials", "mcp_generate_slide_deck"},
                    "openWorldHint": False,
                },
            })

    return mcp_tools


def get_mcp_tool_names() -> list[str]:
    """Return names of all exposed MCP tools."""
    return [t["name"] for t in get_mcp_tool_list()]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _tool_result_to_mcp(result: ToolResult) -> dict:
    """
    Convert a BDC ToolResult to an MCP CallToolResult.

    MCP spec:
      content: list of Content objects (type="text" | "image" | "resource")
      isError: bool
    """
    is_error = result.status == "error"

    # Compose a human-readable text block from all ToolResult fields.
    parts: list[str] = []

    if result.message:
        parts.append(result.message)

    if result.data is not None:
        if isinstance(result.data, str):
            parts.append(result.data)
        else:
            try:
                parts.append(json.dumps(result.data, ensure_ascii=False, indent=2))
            except TypeError:
                parts.append(str(result.data))

    if result.ui_instruction is not None:
        try:
            ui_str = json.dumps(result.ui_instruction, ensure_ascii=False, indent=2)
            parts.append(f"[UI_INSTRUCTION]\n{ui_str}")
        except TypeError:
            pass

    text = "\n\n".join(parts) if parts else (
        "Error executing tool." if is_error else "Tool executed successfully."
    )

    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: int,
) -> dict:
    """
    Execute a BDC tool by name and return an MCP CallToolResult.

    Args:
        tool_name:  Name of the tool to call (must match BaseTool.name).
        arguments:  Caller-supplied arguments from MCP tools/call.
        user_id:    The user acting on behalf of the API key.

    Returns:
        MCP CallToolResult dict ready to be sent back to the client.
    """
    if not _is_allowed(tool_name):
        return _tool_result_to_mcp(
            ToolResult(
                status="error",
                data={"error": f"Tool '{tool_name}' is not exposed via MCP."},
                message=f"Tool '{tool_name}' is not exposed via MCP.",
            )
        )

    from mcp.auth import get_current_scopes

    if tool_name in WRITE_TOOLS and "write" not in get_current_scopes():
        return _tool_result_to_mcp(ToolResult(
            status="error",
            data={"error": "write_scope_required"},
            message="This credential is read-only. Create a write-enabled key to use this tool.",
        ))

    if any(str(key).startswith("_") for key in arguments):
        return _tool_result_to_mcp(ToolResult(
            status="error",
            data={"error": "reserved_argument"},
            message="Arguments beginning with '_' are reserved by the server.",
        ))

    tool = get_tool_by_name(tool_name)
    if tool is None:
        return _tool_result_to_mcp(
            ToolResult(
                status="error",
                data={"error": f"Unknown tool: '{tool_name}'"},
                message=f"Unknown tool: '{tool_name}'",
            )
        )

    logger.info(
        "MCP tool call",
        extra={
            "tool": tool_name,
            "user_id": user_id,
            "arg_keys": list(arguments.keys()),
        },
    )

    course_id = arguments.get("course_id")
    if tool_name in COURSE_READ_TOOLS | COURSE_OWNER_TOOLS:
        if not isinstance(course_id, int) or course_id <= 0:
            return _tool_result_to_mcp(ToolResult(
                status="error",
                data={"error": "course_id_required"},
                message="A valid course_id is required for this MCP tool.",
            ))
        has_access = (
            await _user_can_read_course(user_id, course_id)
            if tool_name in COURSE_READ_TOOLS
            else await _user_owns_course(user_id, course_id)
        )
        if not has_access:
            await _audit(user_id, tool_name, False, {"course_id": course_id, "reason": "forbidden"})
            return _tool_result_to_mcp(ToolResult(
                status="error",
                data={"error": "forbidden"},
                message=(
                    "This course is not readable by your account."
                    if tool_name in COURSE_READ_TOOLS
                    else "You may only use this tool with a course you own or co-teach."
                ),
            ))

    try:
        result = await asyncio.wait_for(
            execute_tool(
                name=tool_name,
                arguments=dict(arguments),
                user_id=user_id,
            ),
            timeout=settings.mcp_tool_timeout_seconds,
        )
        await _audit(user_id, tool_name, result.status != "error", {"course_id": course_id})
    except asyncio.TimeoutError:
        result = ToolResult(
            status="error",
            data={"error": "tool_timeout"},
            message="The tool did not finish within the allowed time.",
        )
    except Exception as exc:
        logger.exception("MCP tool execution error: tool=%s", tool_name)
        result = ToolResult(
            status="error",
            data={"error": "tool_execution_failed"},
            message=f"Tool '{tool_name}' could not be completed.",
        )

    return _tool_result_to_mcp(result)


async def _user_owns_course(user_id: int, course_id: int) -> bool:
    """Resolve authorization through LMS instead of trusting caller-supplied IDs."""
    try:
        from mcp.course_access import user_owns_course
        return await user_owns_course(user_id, course_id)
    except Exception as exc:
        logger.warning("MCP ownership check failed closed: %s", exc)
        return False


async def _user_can_read_course(user_id: int, course_id: int) -> bool:
    """Allow read-only MCP knowledge tools for owners/co-teachers and enrolled students."""
    try:
        from mcp.course_access import user_can_read_course
        return await user_can_read_course(user_id, course_id)
    except Exception as exc:
        logger.warning("MCP course read-access check failed closed: %s", exc)
        return False


async def _audit(user_id: int, action: str, success: bool, metadata: dict) -> None:
    try:
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            await conn.execute(
                "INSERT INTO mcp_audit_log (user_id, action, success, metadata) VALUES ($1, $2, $3, $4::jsonb)",
                user_id, action[:160], success, json.dumps(metadata),
            )
    except Exception as exc:
        logger.warning("MCP audit write failed: %s", exc)
