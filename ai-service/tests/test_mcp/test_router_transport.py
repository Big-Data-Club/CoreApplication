"""HTTP regression coverage for MCP notification acknowledgements."""

import httpx
import pytest
from fastapi import FastAPI

from mcp.auth import get_mcp_user_id
from mcp.router import router
from mcp.server import MCP_PROTOCOL_VERSION


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)

    async def authenticated_user():
        return 42

    app.dependency_overrides[get_mcp_user_id] = authenticated_user

    # Exercise the BaseHTTPMiddleware response path used by production metrics.
    @app.middleware("http")
    async def pass_through(request, call_next):
        return await call_next(request)

    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "method": "notifications/unknown"},
        [
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "method": "notifications/unknown"},
        ],
    ],
    ids=["initialized", "unknown-notification", "notification-batch"],
)
async def test_notifications_return_empty_accepted_response(app, payload):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/mcp", json=payload)

    # JSONResponse(None) emits b"null", even with a no-content status code.
    assert response.content == b""
    assert response.status_code == 202
    assert response.headers["content-length"] == "0"
    assert "content-type" not in response.headers


@pytest.mark.asyncio
async def test_initialize_notification_then_ping(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        initialized = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": MCP_PROTOCOL_VERSION},
        })
        assert initialized.status_code == 200
        assert initialized.json()["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION

        acknowledged = await client.post("/mcp", json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        assert acknowledged.content == b""
        assert acknowledged.status_code == 202

        ping = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "ping",
        })
        assert ping.status_code == 200
        assert ping.json() == {"jsonrpc": "2.0", "id": 2, "result": {}}


@pytest.mark.asyncio
async def test_mixed_batch_returns_only_request_results(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/mcp", json=[
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        ])

    assert response.status_code == 200
    assert response.json() == [{"jsonrpc": "2.0", "id": 1, "result": {}}]
    assert int(response.headers["content-length"]) == len(response.content)
