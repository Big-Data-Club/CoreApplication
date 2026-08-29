"""
ai-service/mcp/router.py

FastAPI router for the BDC MCP Server.

Endpoints:
  GET  /mcp/health      — Health check (no auth)
  GET  /mcp/info        — Server capabilities (no auth, for discovery)
  POST /mcp             — Main JSON-RPC 2.0 endpoint (requires API key)
  GET  /mcp/sse         — Optional SSE stream for server-initiated messages

Transport:
  The primary transport is HTTP POST (Streamable HTTP).
  Clients send JSON-RPC requests as POST body and get back a JSON response.
  This is the recommended approach for web-hosted MCP servers.

  SSE is also available for clients that need to receive unsolicited
  notifications (currently none, but included for spec completeness).

Content-Type:
  - Request:  application/json
  - Response: application/json
  - SSE:      text/event-stream

Security notes:
  - Auth is enforced by `get_mcp_user_id` FastAPI dependency.
  - Health and info endpoints are unauthenticated (safe — no data returned).
  - All other endpoints require a valid MCP API key.
  - CORS is handled at the ai-service level (main.py).

Metrics:
  - mcp_requests_total{method, status}
  - mcp_tool_calls_total{tool_name, status}
  These are registered on the Prometheus registry used by main.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from typing import Any, AsyncGenerator

import orjson
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from mcp.auth import get_mcp_user_id
from mcp.server import (
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_CAPABILITIES,
    MCP_SERVER_INFO,
    dispatch,
    dispatch_batch,
)
from mcp.tool_adapter import get_mcp_tool_names
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/mcp", tags=["mcp"])


# --------------------------------------------------------------------------
# Prometheus metrics (optional, gracefully skipped if not available)
# --------------------------------------------------------------------------

try:
    from prometheus_client import Counter

    _mcp_requests_total = Counter(
        "bdc_mcp_requests_total",
        "Total MCP JSON-RPC requests received.",
        ("method", "status"),
    )
    _mcp_tool_calls_total = Counter(
        "bdc_mcp_tool_calls_total",
        "Total MCP tool/call invocations.",
        ("tool_name", "is_error"),
    )
    _METRICS_ENABLED = True
except Exception:
    _METRICS_ENABLED = False


def _record_request(method: str, ok: bool) -> None:
    if _METRICS_ENABLED:
        _mcp_requests_total.labels(method=method, status="ok" if ok else "error").inc()


def _record_tool_call(tool_name: str, is_error: bool) -> None:
    if _METRICS_ENABLED:
        _mcp_tool_calls_total.labels(tool_name=tool_name, is_error=str(is_error)).inc()


# --------------------------------------------------------------------------
# Unauthenticated endpoints
# --------------------------------------------------------------------------

@router.get("/health")
async def mcp_health():
    """
    MCP server health check.

    Returns 200 with tool count when the MCP server is healthy.
    """
    try:
        tool_names = get_mcp_tool_names()
        return {
            "status": "ok",
            "server": MCP_SERVER_INFO["name"],
            "version": MCP_SERVER_INFO["version"],
            "protocol_version": MCP_PROTOCOL_VERSION,
            "tools_count": len(tool_names),
        }
    except Exception as exc:
        logger.error("MCP health check error: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "error": str(exc)},
        )


@router.get("/info")
async def mcp_info():
    """
    Return server metadata and capabilities for discovery.
    This endpoint is unauthenticated — clients can probe it without a key.
    """
    return {
        "serverInfo": MCP_SERVER_INFO,
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": MCP_SERVER_CAPABILITIES,
        "transport": {
            "http": {
                "endpoint": "/mcp",
                "method": "POST",
                "contentType": "application/json",
            },
            "sse": {
                "endpoint": "/mcp/sse",
                "method": "GET",
            },
        },
        "authentication": {
            "type": "bearer",
            "header": "Authorization",
            "scheme": "Bearer",
        },
    }


# --------------------------------------------------------------------------
# Self-Service API Key Management (for UI / LMS Frontend)
# --------------------------------------------------------------------------

class CreateKeyRequest(BaseModel):
    name: str = Field(default="MCP Key", min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


def _require_internal_identity(x_user_id: int | None, x_ai_secret: str | None) -> int:
    """Only the authenticated frontend BFF may manage a user's credentials."""
    expected = settings.ai_service_secret
    if (
        not x_user_id
        or not x_ai_secret
        or not expected
        or not secrets.compare_digest(x_ai_secret, expected)
    ):
        raise HTTPException(401, "Authenticated frontend session required")
    return int(x_user_id)


@router.post("/keys")
async def create_user_mcp_key(
    body: CreateKeyRequest,
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
    x_ai_secret: str | None = Header(default=None, alias="X-AI-Secret"),
):
    """
    Generate a new self-service MCP API key for the logged-in user.
    """
    user_id = _require_internal_identity(x_user_id, x_ai_secret)
    scopes = sorted(set(body.scopes))
    if not scopes or not set(scopes).issubset({"read", "write"}):
        raise HTTPException(422, "Scopes must contain only 'read' and/or 'write'")

    raw_key = f"bdc_mcp_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = f"{raw_key[:16]}…"

    try:
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            active_count = await conn.fetchval(
                "SELECT COUNT(*) FROM mcp_api_keys WHERE user_id = $1 AND revoked_at IS NULL",
                user_id,
            )
            if int(active_count or 0) >= 5:
                raise HTTPException(409, "Maximum of 5 active MCP keys reached")
            row = await conn.fetchrow(
                """INSERT INTO mcp_api_keys
                       (user_id, name, key_hash, key_prefix, scopes, expires_at)
                   VALUES ($1, $2, $3, $4, $5,
                           CASE WHEN $6::int IS NULL THEN NULL
                                ELSE NOW() + make_interval(days => $6) END)
                   RETURNING id, name, scopes, created_at, expires_at""",
                user_id, body.name.strip(), key_hash, key_prefix, scopes,
                body.expires_in_days,
            )
        return {
            "id": row["id"],
            "name": row["name"],
            "api_key": raw_key,
            "masked_key": key_prefix,
            "scopes": list(row["scopes"]),
            "created_at": row["created_at"].isoformat(),
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
            "message": "Copy this key now. It provides MCP access on behalf of your user account."
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create MCP key: %s", exc)
        raise HTTPException(500, "Failed to generate API key")


@router.get("/keys")
async def list_user_mcp_keys(
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
    x_ai_secret: str | None = Header(default=None, alias="X-AI-Secret"),
):
    """
    List all active MCP API keys for the logged-in user.
    """
    user_id = _require_internal_identity(x_user_id, x_ai_secret)

    try:
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """SELECT id, name, key_prefix, scopes, created_at, expires_at, last_used_at
                   FROM mcp_api_keys
                   WHERE user_id = $1 AND revoked_at IS NULL
                   ORDER BY created_at DESC""",
                user_id,
            )
        keys = []
        for r in rows:
            keys.append({
                "id": r["id"],
                "name": r["name"],
                "masked_key": r["key_prefix"],
                "scopes": list(r["scopes"]),
                "created_at": r["created_at"].isoformat(),
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            })
        return {"keys": keys}
    except Exception as exc:
        logger.exception("Failed to list MCP keys: %s", exc)
        raise HTTPException(500, "Failed to list API keys")


@router.delete("/keys/{key_id}")
async def revoke_user_mcp_key(
    key_id: int,
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
    x_ai_secret: str | None = Header(default=None, alias="X-AI-Secret"),
):
    """
    Revoke/delete an MCP API key for the logged-in user.
    """
    user_id = _require_internal_identity(x_user_id, x_ai_secret)

    try:
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """UPDATE mcp_api_keys SET revoked_at = NOW()
                   WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
                   RETURNING key_hash""",
                key_id, user_id,
            )
        if not row:
            raise HTTPException(404, "API key not found or belongs to another user")

        # Evict from Redis cache
        try:
            from app.core.cache import get_cache
            redis = await get_cache()
            await redis.delete(f"mcp:key:{row['key_hash']}")
        except Exception:
            pass

        return {"status": "ok", "message": f"API key #{key_id} revoked."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to revoke MCP key: %s", exc)
        raise HTTPException(500, "Failed to revoke API key")


# --------------------------------------------------------------------------
# Main JSON-RPC endpoint
# --------------------------------------------------------------------------

@router.post("")
async def mcp_jsonrpc(
    request: Request,
    user_id: int = Depends(get_mcp_user_id),
):
    """
    MCP Streamable HTTP Transport — main JSON-RPC 2.0 endpoint.

    Accepts:
      - Single JSON-RPC request object
      - JSON-RPC batch array

    Returns:
      - JSON-RPC response (or batch response array)
      - HTTP 204 if all requests are notifications (no id)
    """
    # Parse body
    raw = await request.body()
    if len(raw) > settings.mcp_max_body_bytes:
        raise HTTPException(413, "MCP request body is too large")
    try:
        body = orjson.loads(raw)
    except Exception as exc:
        logger.warning("MCP: JSON parse error: %s", exc)
        _record_request("parse", False)
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            },
        )

    # Dispatch
    try:
        if isinstance(body, list):
            # Batch request
            if not body:
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request: empty batch"},
                    },
                )
            if len(body) > settings.mcp_max_batch_size:
                raise HTTPException(413, "MCP batch is too large")
            responses = await dispatch_batch(body, user_id)
            if not responses:
                # All notifications — no response body
                return JSONResponse(status_code=204, content=None)

            # Record metrics for batch
            for resp in responses:
                method = next(
                    (b.get("method", "unknown") for b in body if b.get("id") == resp.get("id")),
                    "unknown",
                )
                _record_request(method, "error" not in resp)

            return JSONResponse(content=responses)

        elif isinstance(body, dict):
            method = body.get("method", "unknown")
            response = await dispatch(body, user_id)

            if response is None:
                # Notification — no id, no response body
                _record_request(method, True)
                return JSONResponse(status_code=204, content=None)

            _record_request(method, "error" not in response)

            # Track tool call metrics
            if method == "tools/call" and "result" in response:
                tool_name = body.get("params", {}).get("name", "unknown")
                is_error = response["result"].get("isError", False)
                _record_tool_call(tool_name, is_error)

            return JSONResponse(content=response)

        else:
            _record_request("unknown", False)
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"},
                },
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("MCP unhandled error")
        _record_request("unknown", False)
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": body.get("id") if isinstance(body, dict) else None,
                "error": {"code": -32603, "message": "Internal error"},
            },
        )


# --------------------------------------------------------------------------
# SSE endpoint (optional, for server-initiated messages)
# --------------------------------------------------------------------------

async def _sse_keepalive(
    user_id: int,
) -> AsyncGenerator[str, None]:
    """
    SSE generator — yields periodic keepalive pings.

    Currently we have no server-initiated messages, so this just
    maintains the connection and pings every 30s.
    """
    # Send initial connected event
    yield (
        "event: connected\n"
        f"data: {json.dumps({'server': MCP_SERVER_INFO['name']})}\n\n"
    )

    while True:
        await asyncio.sleep(30)
        yield "event: ping\ndata: {}\n\n"


@router.get("/sse")
async def mcp_sse(
    user_id: int = Depends(get_mcp_user_id),
):
    """
    Optional SSE stream for server-initiated MCP notifications.

    Most MCP workflows use POST only. Connect here if your client
    requires a persistent connection for push notifications.
    """
    return StreamingResponse(
        _sse_keepalive(user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )
