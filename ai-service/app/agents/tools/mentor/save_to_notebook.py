"""
Mentor Tool: save_to_notebook

Saves synthesized summaries, concepts, or cheat sheets to the student's notebook.
Communicates via HTTP with personalize-service.
"""
from __future__ import annotations

import logging
import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SaveToNotebookTool(BaseTool):
    name = "save_to_notebook"
    description = (
        "Save a summarized note, cheat sheet, outline, or key concept "
        "to the student's personal notebook. Use this tool when the student "
        "asks you to save a summary of a lesson, create a cheat sheet, or write "
        "down key points they can review later. Always synthesize the content "
        "clearly in markdown format before saving."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short, clear title for the notebook entry (e.g. 'Tóm tắt Đa hình trong OOP').",
            },
            "content": {
                "type": "string",
                "description": "The rich educational content/notes to save, written in markdown. Keep it clear, structured, and informative.",
            },
            "course_id": {
                "type": "integer",
                "description": "Optional course ID to scope this note.",
            },
            "node_id": {
                "type": "integer",
                "description": "Optional concept/node ID related to this note.",
            },
        },
        "required": ["title", "content"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        student_id = kwargs.get("_user_id", 0)
        course_id = kwargs.get("_course_id") or kwargs.get("course_id")
        node_id = kwargs.get("node_id")
        title = kwargs["title"]
        content = kwargs["content"]

        if not student_id:
            return ToolResult(
                status="error",
                data={"error": "Missing student identification context"},
                message="Không tìm thấy thông tin tài khoản người dùng."
            )

        payload = {
            "user_id": int(student_id),
            "title": title,
            "content": content,
            "course_id": int(course_id) if course_id is not None else None,
            "node_id": int(node_id) if node_id is not None else None
        }

        # Query personalize-service over HTTP
        url = f"{settings.personalize_service_url}/personalize/notebook"
        headers = {
            "X-AI-Secret": settings.ai_service_secret,
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                
            if res.status_code != 200:
                logger.error(f"personalize-service returned {res.status_code}: {res.text}")
                return ToolResult(
                    status="error",
                    data={"error": res.text},
                    message="Không thể lưu ghi chú vào personalize-service."
                )
                
            entry = res.json()
            return ToolResult(
                status="success",
                data={
                    "entry_id": entry.get("id"),
                    "title": title
                },
                message=f"Đã lưu ghi chú '{title}' vào notebook của bạn thành công!",
                ui_instruction={
                    "component": "NotebookSaveSuccess",
                    "props": {
                        "entry_id": entry.get("id"),
                        "title": title,
                        "content": content
                    }
                }
            )

        except Exception as e:
            logger.error(f"HTTP call to personalize-service failed: {str(e)}")
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi kết nối tới hệ thống lưu trữ notebook: {str(e)}"
            )
