"""
Teacher Tool: list_my_courses

Lists the courses owned by the authenticated teacher.
"""
from __future__ import annotations

import logging
import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ListMyCoursesTool(BaseTool):
    name = "list_my_courses"
    description = (
        "List all courses that the teacher owns or has access to. "
        "Use this tool when you need to know which courses the teacher teaches, "
        "especially if the teacher asks to do something (like create a quiz) "
        "but hasn't specified the course yet."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs) -> ToolResult:
        user_id = kwargs.get("_user_id")
        if not user_id:
            return ToolResult(
                status="error",
                data={"error": "missing_user_id"},
                message="Không xác định được ID của giáo viên.",
            )

        url = f"{settings.lms_service_url}/api/v1/courses/my"
        headers = {
            "X-API-Secret": settings.ai_service_secret,
            "X-User-Id": str(user_id),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                
                courses = data.get("data", []) if isinstance(data, dict) and "data" in data else data
                if isinstance(courses, dict):
                    courses = courses.get("items", [])
                if not isinstance(courses, list):
                    courses = []

                if not courses:
                    return ToolResult(
                        status="success",
                        data={"courses": []},
                        message="Giáo viên hiện chưa có khóa học nào.",
                    )

                course_list = []
                for c in courses:
                    c_id = c.get("id")
                    sec_resp = await client.get(f"{settings.lms_service_url}/api/v1/courses/{c_id}/sections", headers=headers)
                    sec_json = sec_resp.json() if sec_resp.status_code == 200 else None
                    sections = sec_json.get("data", []) if isinstance(sec_json, dict) else []
                    if not isinstance(sections, list):
                        sections = []
                    course_list.append({
                        "id": c_id,
                        "title": c.get("title"),
                        "status": c.get("status"),
                        "sections": [{"id": s.get("id"), "title": s.get("title")} for s in sections]
                    })
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error calling LMS ListMyCourses: %s - %s", e.response.status_code, e.response.text)
            return ToolResult(
                status="error",
                data={"status_code": e.response.status_code},
                message=f"Lỗi khi lấy danh sách khóa học từ LMS (HTTP {e.response.status_code}).",
            )
        except Exception as e:
            logger.error("Error calling LMS ListMyCourses: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi kết nối tới LMS: {e}",
            )

        # Format a nice readable message for the LLM
        lines = [f"Tìm thấy {len(course_list)} khóa học:"]
        for c in course_list:
            lines.append(f"- Course ID: {c['id']}, Tên: {c['title']}, Trạng thái: {c['status']}")
            for s in c["sections"]:
                lines.append(f"  + Section ID: {s['id']}, Tên: {s['title']}")

        return ToolResult(
            status="success",
            data={"courses": course_list},
            message="\n".join(lines),
        )
