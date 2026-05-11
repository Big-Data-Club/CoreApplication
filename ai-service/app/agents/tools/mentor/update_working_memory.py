"""
Mentor Tool: update_working_memory

Allows the agent to update the MTM working state (current topic, goals, gaps).
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.agents.memory.mtm import mtm

logger = logging.getLogger(__name__)

class UpdateWorkingMemoryTool(BaseTool):
    name = "update_working_memory"
    description = (
        "Cập nhật working memory để ghi nhớ bối cảnh hiện tại của phiên làm việc. "
        "Sử dụng công cụ này KHI VÀ CHỈ KHI học viên chuyển sang một chủ đề mới, "
        "đặt ra một mục tiêu mới, hoặc bạn phát hiện ra một lỗ hổng kiến thức "
        "mà bạn cần ghi nhớ trong suốt phiên này."
    )
    parameters = {
        "type": "object",
        "properties": {
            "active_learning_goal": {
                "type": "string",
                "description": "Mục tiêu học tập hiện tại (ví dụ: 'Hiểu về vòng lặp for')."
            },
            "identified_knowledge_gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sách các lỗ hổng kiến thức phát hiện được trong phiên."
            },
            "current_topic": {
                "type": "string",
                "description": "Chủ đề hiện tại đang trao đổi."
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú ngắn gọn cho phiên làm việc này."
            }
        }
    }

    async def execute(self, **kwargs) -> ToolResult:
        # ReAct loop should inject _session_id into kwargs. 
        # But wait, looking at execute_tool, it only injects _user_id and _course_id.
        # So we need to handle that.
        session_id = kwargs.get("_session_id")
        if not session_id:
            logger.error("update_working_memory: Missing _session_id in kwargs")
            return ToolResult(
                status="error",
                data={},
                message="Internal error: session_id is missing."
            )
            
        updates = {}
        for key in ["active_learning_goal", "identified_knowledge_gaps", "current_topic", "notes"]:
            if key in kwargs:
                updates[key] = kwargs[key]
                
        if not updates:
            return ToolResult(
                status="success",
                data={},
                message="Không có dữ liệu mới để cập nhật."
            )
            
        try:
            await mtm.update_working_state(session_id, updates)
            return ToolResult(
                status="success",
                data=updates,
                message="Đã cập nhật working memory thành công."
            )
        except Exception as exc:
            logger.error("update_working_memory failed: %s", exc)
            return ToolResult(
                status="error",
                data={"error": str(exc)},
                message=f"Lỗi khi cập nhật working memory: {exc}"
            )
