"""
Teacher Tool: create_section

Creates a new section (module) in a course in the LMS.
"""
from __future__ import annotations

import logging
import httpx
from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CreateSectionTool(BaseTool):
    name = "create_course_section"
    description = (
        "Create a new section (module/chapter) in a course. "
        "Use when the teacher explicitly asks to add a new section, "
        "chapter, or module to their course."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "integer",
                "description": "The course ID to add the section to.",
            },
            "title": {
                "type": "string",
                "description": "The title of the new section.",
            },
            "description": {
                "type": "string",
                "description": "Optional description of what this section covers.",
            },
            "order_index": {
                "type": "integer",
                "description": "Optional order index. If omitted, it will be added to the end.",
            }
        },
        "required": ["course_id", "title"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        course_id = kwargs.get("_course_id") or kwargs["course_id"]
        title = kwargs["title"]
        desc = kwargs.get("description", "")
        order = kwargs.get("order_index")

        try:
            lms_base = settings.lms_service_url.rstrip("/")
            
            # 1. If order_index is not provided, fetch existing sections to determine end
            from app.core.llm import ensure_dict
            if order is None:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"{lms_base}/api/v1/courses/{course_id}/sections",
                        headers={"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(kwargs.get("_user_id") or "")},
                    )
                    if resp.status_code == 200:
                        body = resp.json()
                        sections = (body.get("data") if isinstance(body, dict) else body) or []
                        sections = [s for s in sections if isinstance(s, dict)]
                        order = len(sections) + 1
                    else:
                        order = 1

            # 2. Create the section
            payload = {
                "title": title,
                "description": desc,
                "order_index": order or 1
            }
            
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{lms_base}/api/v1/courses/{course_id}/sections",
                    json=payload,
                    headers={"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(kwargs.get("_user_id") or "")},
                )

            if resp.status_code in (200, 201):
                body = ensure_dict(resp.json())
                data = ensure_dict(body.get("data", body))
                return ToolResult(
                    status="success",
                    data=data,
                    message=f"Đã tạo chương mới: '{title}' (ID: {data.get('id')})."
                )
            else:
                body = resp.json()
                error_msg = (
                    body.get("message", resp.text) if isinstance(body, dict)
                    else str(body) if body else resp.text
                )
                return ToolResult(
                    status="error",
                    data={"error": error_msg},
                    message=f"Lỗi khi tạo chương: {error_msg}"
                )

        except Exception as e:
            logger.error("create_course_section failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi hệ thống khi tạo chương: {e}"
            )
