"""List courses that the MCP caller can safely read."""
from __future__ import annotations

import logging
from typing import Any

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ListAccessibleCoursesTool(BaseTool):
    name = "list_accessible_courses"
    description = (
        "List courses the signed-in caller may read through MCP. The result includes courses "
        "owned or co-taught by a teacher and courses with an accepted student enrollment. "
        "Use this before read-only knowledge search; it does not grant write permission."
    )
    parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = kwargs.get("_user_id")
        if not isinstance(user_id, int) or user_id <= 0:
            return ToolResult(
                status="error",
                data={"error": "missing_user_id"},
                message="Could not resolve the signed-in MCP user.",
            )

        try:
            from mcp.course_access import list_accessible_courses

            courses = await list_accessible_courses(user_id)
        except Exception:
            logger.exception("Failed to list MCP-readable courses")
            return ToolResult(
                status="error",
                data={"error": "lms_unavailable"},
                message="Accessible courses are temporarily unavailable.",
            )

        return ToolResult(
            status="success",
            data={"courses": courses},
            message=(
                f"Found {len(courses)} readable course(s). "
                "ENROLLED_STUDENT access is read-only; LMS writes still require owner/co-teacher access."
            ),
        )
