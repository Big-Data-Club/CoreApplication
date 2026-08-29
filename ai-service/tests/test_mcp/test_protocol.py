"""
tests/test_mcp/test_protocol.py

Unit tests for MCP JSON-RPC 2.0 protocol compliance.

Tests:
  - initialize handshake returns correct capabilities
  - ping returns empty result
  - notifications return None (no response body)
  - tools/list returns list of tools
  - tools/call routes to tool adapter
  - resources/list returns resources
  - Unknown method → -32601 Method not found
  - Missing jsonrpc field → -32600 Invalid Request
  - Batch requests
  - Batch with notifications only → empty list
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mcp.server import dispatch, dispatch_batch, MCP_PROTOCOL_VERSION, MCP_SERVER_INFO


USER_ID = 42


# ── initialize ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initialize_returns_capabilities():
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = await dispatch(body, USER_ID)
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "result" in resp
    result = resp["result"]
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["serverInfo"] == MCP_SERVER_INFO
    assert "tools" in result["capabilities"]
    assert "instructions" in result
    assert "explicit confirmation" in result["instructions"]


# ── ping ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_returns_empty():
    body = {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}}
    resp = await dispatch(body, USER_ID)
    assert resp["result"] == {}


# ── notifications (no id) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notification_returns_none():
    """Requests without 'id' are notifications — no response body."""
    body = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    resp = await dispatch(body, USER_ID)
    assert resp is None


@pytest.mark.asyncio
async def test_unknown_notification_returns_none():
    """Unknown notification method is silently accepted."""
    body = {"jsonrpc": "2.0", "method": "notifications/unknown", "params": {}}
    resp = await dispatch(body, USER_ID)
    assert resp is None


# ── tools/list ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tools_list_returns_tools():
    mock_tools = [
        {"name": "generate_content_draft", "description": "...", "inputSchema": {}},
        {"name": "generate_quiz_draft", "description": "...", "inputSchema": {}},
    ]
    with patch("mcp.server.get_mcp_tool_list", return_value=mock_tools):
        body = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        resp = await dispatch(body, USER_ID)

    assert "result" in resp
    assert "tools" in resp["result"]
    assert len(resp["result"]["tools"]) == 2


# ── tools/call ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tools_call_success():
    mock_call_result = {
        "content": [{"type": "text", "text": "Quiz generated!"}],
        "isError": False,
    }
    with patch("mcp.server.call_mcp_tool", new=AsyncMock(return_value=mock_call_result)):
        body = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "generate_quiz_draft",
                "arguments": {"course_id": 1, "section_id": 2, "num_questions": 5},
            },
        }
        resp = await dispatch(body, USER_ID)

    assert "result" in resp
    assert resp["result"]["isError"] is False
    assert resp["result"]["content"][0]["text"] == "Quiz generated!"


@pytest.mark.asyncio
async def test_tools_call_missing_name():
    body = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"arguments": {}},  # missing 'name'
    }
    resp = await dispatch(body, USER_ID)
    assert "error" in resp
    assert resp["error"]["code"] == -32602  # Invalid params


@pytest.mark.asyncio
async def test_tools_call_non_dict_arguments():
    body = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "some_tool", "arguments": "not_a_dict"},
    }
    resp = await dispatch(body, USER_ID)
    assert "error" in resp
    assert resp["error"]["code"] == -32602


# ── resources/list ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resources_list():
    mock_resources = [
        {"uri": "bdc://courses/1", "name": "Python Basics", "mimeType": "application/json"},
    ]
    with patch("mcp.server.list_mcp_resources", new=AsyncMock(return_value=mock_resources)):
        body = {"jsonrpc": "2.0", "id": 7, "method": "resources/list", "params": {}}
        resp = await dispatch(body, USER_ID)

    assert "result" in resp
    assert len(resp["result"]["resources"]) == 1


# ── resources/read ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resources_read_success():
    mock_content = {
        "contents": [{"uri": "bdc://courses/1", "mimeType": "application/json", "text": "{}"}]
    }
    with patch("mcp.server.read_mcp_resource", new=AsyncMock(return_value=mock_content)):
        body = {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "resources/read",
            "params": {"uri": "bdc://courses/1"},
        }
        resp = await dispatch(body, USER_ID)

    assert "result" in resp
    assert len(resp["result"]["contents"]) == 1


@pytest.mark.asyncio
async def test_resources_read_missing_uri():
    body = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "resources/read",
        "params": {},  # missing 'uri'
    }
    resp = await dispatch(body, USER_ID)
    assert "error" in resp
    assert resp["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_resources_read_invalid_uri():
    with patch("mcp.server.read_mcp_resource", new=AsyncMock(side_effect=ValueError("bad uri"))):
        body = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "resources/read",
            "params": {"uri": "http://bad-scheme"},
        }
        resp = await dispatch(body, USER_ID)
    assert "error" in resp
    assert resp["error"]["code"] == -32602


# ── Method not found ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_method_not_found():
    body = {"jsonrpc": "2.0", "id": 11, "method": "does_not_exist", "params": {}}
    resp = await dispatch(body, USER_ID)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


# ── Invalid jsonrpc version ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_jsonrpc_version():
    body = {"jsonrpc": "1.0", "id": 12, "method": "ping"}
    resp = await dispatch(body, USER_ID)
    assert "error" in resp
    assert resp["error"]["code"] == -32600


# ── Batch requests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_request():
    """Batch of two requests → two responses."""
    mock_tools = []
    with patch("mcp.server.get_mcp_tool_list", return_value=mock_tools):
        batch = [
            {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        responses = await dispatch_batch(batch, USER_ID)

    assert len(responses) == 2
    ids = {r["id"] for r in responses}
    assert ids == {1, 2}


@pytest.mark.asyncio
async def test_batch_notifications_only():
    """Batch with only notifications → empty response list."""
    batch = [
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    ]
    responses = await dispatch_batch(batch, USER_ID)
    assert responses == []
