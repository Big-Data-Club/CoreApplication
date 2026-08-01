"""Open the same review-first course-blueprint UI from teacher chat."""
from __future__ import annotations

from app.agents.tools.base_tool import BaseTool, ToolResult


class CreateCourseFromMaterialsTool(BaseTool):
    name = "create_course_from_materials"
    description = (
        "Open the course blueprint workspace where a teacher can bulk-upload "
        "teaching materials, receive a grounded course/chapter roadmap, edit it, "
        "and explicitly approve or cancel before any course is created. Use when "
        "the teacher wants to create a new course from files or a syllabus."
    )
    parameters = {
        "type": "object",
        "properties": {
            "language": {"type": "string", "description": "Preferred output language, usually vi or en."},
        },
        "required": [],
    }

    async def execute(self, **kwargs) -> ToolResult:
        language = kwargs.get("language", "vi")
        return ToolResult(
            status="pending_human_approval",
            data={"owner_id": int(kwargs.get("_user_id", 0)), "origin": "chatbot", "language": language},
            message=(
                "Hãy tải các giáo trình/tài liệu lên. Tôi sẽ tạo một bản đề xuất để bạn xem, "
                "sửa hoặc hủy; khóa học chỉ được tạo sau khi bạn duyệt."
            ),
            ui_instruction={
                "component": "CourseBlueprintWorkspace",
                "props": {"origin": "chatbot", "language": language},
            },
        )
