"""
tests/test_mcp/test_tools.py

Unit tests for the MCP tool adapter.

Tests:
  - get_mcp_tool_list returns tools in MCP schema format
  - get_mcp_tool_list applies whitelist filter
  - call_mcp_tool: success path → isError=False
  - call_mcp_tool: tool returns error → isError=True
  - call_mcp_tool: unknown tool → isError=True
  - call_mcp_tool: tool not on whitelist → isError=True
  - call_mcp_tool: tool raises exception → isError=True
  - _tool_result_to_mcp: message + data → combined text
  - _tool_result_to_mcp: ui_instruction is included
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.tools.base_tool import ToolResult
from mcp.tool_adapter import (
    WRITE_TOOLS,
    _tool_result_to_mcp,
    call_mcp_tool,
    get_mcp_tool_list,
    get_mcp_tool_names,
)


USER_ID = 42


def test_quiz_creation_requires_write_scoped_key():
    assert "mcp_batch_generate_quiz" in WRITE_TOOLS


# ── _tool_result_to_mcp ──────────────────────────────────────────────────────

def test_tool_result_to_mcp_success():
    result = ToolResult(status="success", data={"key": "value"}, message="Done!")
    mcp = _tool_result_to_mcp(result)
    assert mcp["isError"] is False
    assert len(mcp["content"]) == 1
    assert mcp["content"][0]["type"] == "text"
    text = mcp["content"][0]["text"]
    assert "Done!" in text
    assert "value" in text


def test_tool_result_to_mcp_error():
    result = ToolResult(status="error", data={"error": "Not found"}, message="Failed")
    mcp = _tool_result_to_mcp(result)
    assert mcp["isError"] is True
    assert "Failed" in mcp["content"][0]["text"]


def test_tool_result_to_mcp_string_data():
    result = ToolResult(status="success", data="plain text data", message="")
    mcp = _tool_result_to_mcp(result)
    assert "plain text data" in mcp["content"][0]["text"]


def test_tool_result_to_mcp_ui_instruction():
    result = ToolResult(
        status="success",
        data={},
        message="",
        ui_instruction={"component": "QuizDraftPreview", "props": {"quiz_id": 5}},
    )
    mcp = _tool_result_to_mcp(result)
    text = mcp["content"][0]["text"]
    assert "UI_INSTRUCTION" in text
    assert "QuizDraftPreview" in text


def test_tool_result_to_mcp_empty_data():
    result = ToolResult(status="success", data=None, message="")
    mcp = _tool_result_to_mcp(result)
    assert "Tool executed successfully." in mcp["content"][0]["text"]


def test_tool_result_to_mcp_error_empty():
    result = ToolResult(status="error", data=None, message="")
    mcp = _tool_result_to_mcp(result)
    assert "Error executing tool." in mcp["content"][0]["text"]


# ── get_mcp_tool_list ────────────────────────────────────────────────────────

def _make_mock_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.to_function_schema.return_value = {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Description of {name}",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
    return tool


def test_get_mcp_tool_list_returns_allowed_tools():
    mock_tools = [_make_mock_tool("tool_a"), _make_mock_tool("tool_b")]
    with (
        patch("mcp.tool_adapter.get_tools", return_value=mock_tools),
        patch("mcp.tool_adapter._ALLOWED_TOOLS", {"tool_a", "tool_b"}),
    ):
        tools = get_mcp_tool_list()

    names = [t["name"] for t in tools]
    assert "tool_a" in names
    assert "tool_b" in names


def test_get_mcp_tool_list_schema_shape():
    mock_tools = [_make_mock_tool("tool_a")]
    with (
        patch("mcp.tool_adapter.get_tools", return_value=mock_tools),
        patch("mcp.tool_adapter._ALLOWED_TOOLS", {"tool_a"}),
    ):
        tools = get_mcp_tool_list()

    t = tools[0]
    assert "name" in t
    assert "description" in t
    assert "inputSchema" in t
    assert t["inputSchema"]["type"] == "object"


def test_get_mcp_tool_list_whitelist():
    mock_tools = [_make_mock_tool("tool_a"), _make_mock_tool("tool_b")]
    with (
        patch("mcp.tool_adapter.get_tools", return_value=mock_tools),
        patch("mcp.tool_adapter._ALLOWED_TOOLS", {"tool_a"}),
    ):
        tools = get_mcp_tool_list()

    names = [t["name"] for t in tools]
    assert "tool_a" in names
    assert "tool_b" not in names


def test_get_mcp_tool_list_deduplicates():
    """Tools shared between teacher and mentor appear only once."""
    shared_tool = _make_mock_tool("shared_tool")
    with (
        patch(
            "mcp.tool_adapter.get_tools",
            side_effect=lambda agent_type: [shared_tool],
        ),
        patch("mcp.tool_adapter._ALLOWED_TOOLS", {"shared_tool"}),
    ):
        tools = get_mcp_tool_list()

    assert len([t for t in tools if t["name"] == "shared_tool"]) == 1


# ── call_mcp_tool ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_mcp_tool_success():
    success_result = ToolResult(status="success", data={"content": "Draft"}, message="Done")
    with (
        patch("mcp.tool_adapter._is_allowed", return_value=True),
        patch("mcp.tool_adapter.get_tool_by_name", return_value=MagicMock()),
        patch("mcp.tool_adapter.execute_tool", new=AsyncMock(return_value=success_result)),
    ):
        result = await call_mcp_tool("generate_content_draft", {"course_id": 1}, USER_ID)

    assert result["isError"] is False
    assert "Draft" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_call_mcp_tool_error_result():
    error_result = ToolResult(status="error", data={"error": "DB timeout"}, message="Failed")
    with (
        patch("mcp.tool_adapter._is_allowed", return_value=True),
        patch("mcp.tool_adapter.get_tool_by_name", return_value=MagicMock()),
        patch("mcp.tool_adapter.execute_tool", new=AsyncMock(return_value=error_result)),
    ):
        result = await call_mcp_tool("some_tool", {}, USER_ID)

    assert result["isError"] is True


@pytest.mark.asyncio
async def test_call_mcp_tool_unknown_tool():
    with (
        patch("mcp.tool_adapter._is_allowed", return_value=True),
        patch("mcp.tool_adapter.get_tool_by_name", return_value=None),
    ):
        result = await call_mcp_tool("nonexistent_tool", {}, USER_ID)

    assert result["isError"] is True
    assert "Unknown tool" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_call_mcp_tool_not_on_whitelist():
    with patch("mcp.tool_adapter._is_allowed", return_value=False):
        result = await call_mcp_tool("blocked_tool", {}, USER_ID)

    assert result["isError"] is True
    assert "not exposed via MCP" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_call_mcp_tool_unexpected_exception():
    with (
        patch("mcp.tool_adapter._is_allowed", return_value=True),
        patch("mcp.tool_adapter.get_tool_by_name", return_value=MagicMock()),
        patch(
            "mcp.tool_adapter.execute_tool",
            new=AsyncMock(side_effect=RuntimeError("Unexpected crash")),
        ),
    ):
        result = await call_mcp_tool("some_tool", {}, USER_ID)

    assert result["isError"] is True
    assert "Unexpected crash" not in result["content"][0]["text"]
    assert "could not be completed" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_call_mcp_tool_rejects_reserved_arguments():
    with patch("mcp.tool_adapter._is_allowed", return_value=True):
        result = await call_mcp_tool("some_tool", {"_user_id": 999}, USER_ID)
    assert result["isError"] is True
    assert "reserved" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_enrolled_student_can_use_course_read_tool():
    success_result = ToolResult(status="success", data={"chunks": []}, message="Done")
    with (
        patch("mcp.tool_adapter._is_allowed", return_value=True),
        patch("mcp.tool_adapter.get_tool_by_name", return_value=MagicMock()),
        patch("mcp.tool_adapter._user_can_read_course", new=AsyncMock(return_value=True)),
        patch("mcp.tool_adapter._user_owns_course", new=AsyncMock(return_value=False)),
        patch("mcp.tool_adapter._audit", new=AsyncMock()),
        patch("mcp.tool_adapter.execute_tool", new=AsyncMock(return_value=success_result)),
    ):
        result = await call_mcp_tool("search_course_materials", {"course_id": 58, "query": "paging"}, USER_ID)

    assert result["isError"] is False


@pytest.mark.asyncio
async def test_enrolled_student_cannot_use_course_owner_tool():
    with (
        patch("mcp.tool_adapter._is_allowed", return_value=True),
        patch("mcp.tool_adapter.get_tool_by_name", return_value=MagicMock()),
        patch("mcp.tool_adapter._user_owns_course", new=AsyncMock(return_value=False)),
        patch("mcp.tool_adapter._audit", new=AsyncMock()),
    ):
        result = await call_mcp_tool("mcp_create_lesson", {"course_id": 58}, USER_ID)

    assert result["isError"] is True
    assert "own or co-teach" in result["content"][0]["text"]
