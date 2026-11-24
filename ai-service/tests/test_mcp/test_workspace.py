from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp import auth, workspace
from mcp.router import router
from mcp import tool_adapter


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(auth.settings, "mcp_enabled", True)
    monkeypatch.setattr(workspace.settings, "workspace_mcp_secret", "x" * 32)
    monkeypatch.setattr(auth, "_KEY_MAP", {"lms-key": 10})
    scopes = {
        "read-key": (10, frozenset({auth.WORKSPACE_READ})),
        "create-key": (10, frozenset(auth.WORKSPACE_SCOPES)),
    }
    monkeypatch.setattr(auth, "_resolve_db_key", AsyncMock(side_effect=scopes.get))
    monkeypatch.setattr(auth, "_check_rate_limit", AsyncMock())
    monkeypatch.setattr(tool_adapter, "_ALLOWED_TOOLS", tool_adapter.SAFE_DEFAULT_TOOLS)
    monkeypatch.setattr(tool_adapter, "_audit", AsyncMock())
    return TestClient(app)


def rpc(client, method, params=None, *, key="create-key", path="/mcp/workspace"):
    return client.post(path, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                       headers={"Authorization": f"Bearer {key}"})


def test_discovery_is_scoped_to_key(client):
    read = rpc(client, "tools/list", key="read-key").json()["result"]["tools"]
    assert [item["name"] for item in read] == ["workspace_list_destinations"]
    assert read[0]["annotations"]["readOnlyHint"] is True
    write = rpc(client, "tools/list").json()["result"]["tools"]
    assert {item["name"] for item in write} == set(workspace.TOOLS)
    assert rpc(client, "tools/list", key="lms-key").status_code == 403
    assert rpc(client, "tools/list", path="/mcp").status_code == 403
    assert rpc(client, "tools/list", key="unknown").status_code == 401


def test_workspace_key_cannot_call_lms_or_read_course_resources(client):
    assert rpc(client, "tools/call", {"name": "list_my_courses"}).json()["result"]["isError"]
    assert "error" in rpc(client, "resources/read", {"uri": "bdc://courses/1/contents"}).json()
    guide = rpc(client, "resources/list").json()["result"]["resources"]
    assert [resource["uri"] for resource in guide] == [workspace.GUIDE_URI]


def test_write_requires_scope_and_confirmation(client, monkeypatch):
    call = AsyncMock()
    monkeypatch.setattr(workspace.httpx, "AsyncClient", call)
    arguments = {
        "destination_id": str(uuid4()), "request_id": str(uuid4()),
        "title": "Test", "markdown": "# Test", "confirmed": False,
    }
    params = {"name": "workspace_create_page", "arguments": arguments}
    assert rpc(client, "tools/call", params, key="read-key").json()["result"]["isError"]
    rejected = rpc(client, "tools/call", params).json()["result"]
    assert rejected["isError"] and "confirmation_required" in rejected["content"][0]["text"]
    arguments["confirmed"] = True
    arguments["user_id"] = 20
    assert rpc(client, "tools/call", params).json()["result"]["isError"]
    call.assert_not_called()


def test_markdown_is_forwarded_to_workspace_without_fetching_source(client, monkeypatch):
    page_id = str(uuid4())
    source = "https://example.test/article"
    async_client = httpx.AsyncClient

    def handle(request):
        assert request.url.path == "/internal/mcp/workspace/pages"
        assert request.headers["X-Workspace-Actor"] == "10"
        assert request.headers["X-Workspace-Scope"] == auth.WORKSPACE_CREATE
        assert b"# Ghi" in request.content and source.encode() in request.content
        return httpx.Response(201, json={"page_id": page_id, "created": True})

    monkeypatch.setattr(workspace.httpx, "AsyncClient", lambda **kw: async_client(transport=httpx.MockTransport(handle), **kw))
    created = rpc(client, "tools/call", {"name": "workspace_create_page", "arguments": {
        "destination_id": str(uuid4()), "request_id": str(uuid4()),
        "title": "Ghi chu", "markdown": "# Ghi chu", "confirmed": True, "source_url": source,
    }}).json()["result"]
    assert created["isError"] is False
    assert f"/workspace?page={page_id}" in created["content"][0]["text"]
