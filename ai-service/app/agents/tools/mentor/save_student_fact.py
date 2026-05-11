"""
Mentor Tool: save_student_fact

Allows the agent to persist long-term facts about a student.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.agents.memory.ltm import ltm

logger = logging.getLogger(__name__)

class SaveStudentFactTool(BaseTool):
    name = "save_student_fact"
    description = (
        "Lưu trữ vĩnh viễn một thông tin quan trọng về học viên vào Long-Term Memory. "
        "Chỉ sử dụng khi học viên tiết lộ điểm yếu, sở thích, mục tiêu hoặc ghi chú cá nhân quan trọng."
    )
    parameters = {
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "Nội dung cần ghi nhớ (ví dụ: 'Học viên rất yếu phần OOP')."
            },
            "category": {
                "type": "string",
                "enum": ["weakness", "preference", "goal", "personal", "note"],
                "description": "Phân loại thông tin."
            }
        },
        "required": ["fact", "category"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        user_id = kwargs.get("_user_id")
        course_id = kwargs.get("_course_id")
        
        if not user_id:
            return ToolResult(
                status="error",
                data={},
                message="Internal error: user_id is missing."
            )
            
        fact = kwargs["fact"]
        category = kwargs["category"]
        
        try:
            fact_id = await ltm.save_fact(
                user_id=user_id,
                fact=fact,
                category=category,
                course_id=course_id
            )
            
            if fact_id:
                return ToolResult(
                    status="success",
                    data={"fact_id": fact_id, "category": category},
                    message=f"Đã lưu thành công thông tin vào bộ nhớ dài hạn ({category})."
                )
            else:
                return ToolResult(
                    status="error",
                    data={},
                    message="Không thể lưu thông tin vào cơ sở dữ liệu."
                )
                
        except Exception as exc:
            logger.error("save_student_fact failed: %s", exc)
            return ToolResult(
                status="error",
                data={"error": str(exc)},
                message=f"Lỗi khi lưu thông tin: {exc}"
            )
