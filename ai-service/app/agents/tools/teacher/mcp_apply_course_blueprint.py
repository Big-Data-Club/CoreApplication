"""Materialise an explicitly approved legacy MCP blueprint as an LMS draft course."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

settings = get_settings()


class McpApplyCourseBlueprintTool(BaseTool):
    name = "mcp_apply_course_blueprint"
    description = (
        "After the teacher explicitly approves an existing course blueprint, materialize it as a real private LMS DRAFT course. "
        "Creates its sections and draft lessons, never publishes them. Safe to retry: an already-applied blueprint returns its existing course ID."
    )
    parameters = {
        "type": "object",
        "properties": {
            "blueprint_id": {"type": "string", "format": "uuid", "description": "The reviewed BDC course blueprint UUID."},
        },
        "required": ["blueprint_id"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = int(kwargs.get("_user_id") or 0)
        try:
            blueprint_id = str(UUID(str(kwargs.get("blueprint_id") or "")))
        except ValueError:
            return ToolResult(status="error", data={"error": "invalid_blueprint_id"}, message="A valid blueprint UUID is required.")
        if not user_id:
            return ToolResult(status="error", data={"error": "missing_identity"}, message="The MCP credential has no user identity.")

        headers = {"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                response = await client.post(
                    f"{settings.lms_service_url.rstrip('/')}/api/v1/course-blueprints/{blueprint_id}/apply",
                    json={}, headers=headers,
                )
        except httpx.HTTPError:
            return ToolResult(status="error", data={"error": "lms_unavailable"}, message="LMS could not be reached; no course was published.")
        try:
            body = response.json()
        except Exception:
            body = {}
        if response.status_code not in (200, 201):
            message = body.get("message") or body.get("error") or f"LMS HTTP {response.status_code}"
            return ToolResult(status="error", data={"error": "blueprint_apply_failed", "details": message}, message=str(message))
        data = body.get("data", body) if isinstance(body, dict) else {}
        course_id = data.get("course_id") if isinstance(data, dict) else None
        return ToolResult(
            status="success",
            data={"blueprint_id": blueprint_id, "course_id": course_id, "state": "DRAFT", "already_applied": bool(data.get("already_applied")) if isinstance(data, dict) else False},
            message=f"Blueprint approved and materialized as private DRAFT course {course_id}. Review it in LMS before publishing.",
        )
