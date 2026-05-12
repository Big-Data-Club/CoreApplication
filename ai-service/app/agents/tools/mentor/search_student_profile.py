"""
Mentor Tool: search_student_profile

Allows the agent to query past facts about a student.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.agents.memory.ltm import ltm

logger = logging.getLogger(__name__)

class SearchStudentProfileTool(BaseTool):
    name = "search_student_profile"
    description = (
        "Tra cứu hồ sơ của học viên từ Long-Term Memory (bộ nhớ dài hạn). "
        "Sử dụng công cụ này ĐỂ LẤY thông tin về điểm yếu, sở thích, "
        "mục tiêu đã được ghi nhớ từ trước."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Câu truy vấn ngữ nghĩa (ví dụ: 'điểm yếu của học viên', 'mục tiêu của học viên')."
            },
            "category": {
                "type": "string",
                "enum": ["weakness", "preference", "goal", "personal", "note"],
                "description": "(Tuỳ chọn) Lọc theo loại thông tin."
            }
        },
        "required": ["query"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        user_id = kwargs.get("_user_id")
        
        if not user_id:
            return ToolResult(
                status="error",
                data={},
                message="Internal error: user_id is missing."
            )
            
        query = kwargs["query"]
        category = kwargs.get("category")
        
        try:
            results = await ltm.search_facts(
                user_id=user_id,
                query=query,
                top_k=3,
                category=category
            )
            
            if not results:
                return ToolResult(
                    status="success",
                    data={"results": [], "query": query},
                    message=f"Không tìm thấy thông tin nào liên quan đến '{query}' trong bộ nhớ dài hạn."
                )
                
            return ToolResult(
                status="success",
                data={"results": results, "query": query},
                message=f"Đã tìm thấy {len(results)} thông tin liên quan trong bộ nhớ dài hạn."
            )
                
        except Exception as exc:
            logger.error("search_student_profile failed: %s", exc)
            return ToolResult(
                status="error",
                data={"error": str(exc)},
                message=f"Lỗi khi tra cứu thông tin: {exc}"
            )
