"""Open the teacher's editable material-inbox workflow.

The tool intentionally does not upload, create content, or index anything.
Those are irreversible/external actions and are performed only from the
human-reviewed workspace rendered by the frontend.
"""
from __future__ import annotations

from app.agents.tools.base_tool import BaseTool, ToolResult


class PrepareCourseMaterialsTool(BaseTool):
    name = "prepare_course_materials"
    description = (
        "Open an editable material inbox for a teacher to drop multiple files, "
        "review AI title/description/type/index suggestions, then explicitly "
        "confirm upload and indexing. Use when the teacher wants to organize, "
        "upload, prepare, classify, or index course materials. This tool never "
        "writes to the LMS by itself."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "integer",
                "description": "Course to prepare materials for. Use the verified current course when available.",
            },
            "section_id": {
                "type": "integer",
                "description": "Optional preferred chapter/section for the uploaded files.",
            },
        },
        "required": [],
    }

    async def execute(self, **kwargs) -> ToolResult:
        course_id = kwargs.get("_course_id") or kwargs.get("course_id")
        section_id = kwargs.get("section_id")
        if not course_id:
            return ToolResult(
                status="error",
                data={"error": "course_required"},
                message="Cần chọn khóa học trước khi chuẩn bị tài liệu.",
            )

        return ToolResult(
            status="pending_human_approval",
            data={"course_id": int(course_id), "section_id": section_id},
            message=(
                "Hãy thả các file vào hộp tài liệu. Tôi sẽ gợi ý tiêu đề, mô tả, "
                "loại nội dung và tài liệu nên index; bạn có thể sửa mọi đề xuất "
                "trước khi tải lên."
            ),
            ui_instruction={
                "component": "MaterialPreparationWorkspace",
                "props": {"course_id": int(course_id), "section_id": section_id},
            },
        )
