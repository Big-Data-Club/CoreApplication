"""
Mentor Tool: filter_irrelevant_context

Allows the agent to drop noisy/stale messages from STM.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.agents.memory.stm import stm

logger = logging.getLogger(__name__)

class FilterIrrelevantContextTool(BaseTool):
    name = "filter_irrelevant_context"
    description = (
        "Xóa bỏ các tin nhắn hoặc kết quả của các công cụ cũ không còn liên quan. "
        "Sử dụng công cụ này khi bộ nhớ bị đầy bởi các thông báo lỗi, kết quả tìm kiếm "
        "quá dài hoặc các chi tiết không cần thiết, giúp giải phóng không gian bộ nhớ."
    )
    parameters = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Lý do vì sao các thông tin cũ bị lọc bỏ (ví dụ: 'Kết quả tìm kiếm quá dài và không liên quan')."
            }
        },
        "required": ["reason"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        session_id = kwargs.get("_session_id")
        
        if not session_id:
            return ToolResult(
                status="error",
                data={},
                message="Internal error: session_id is missing."
            )
            
        reason = kwargs["reason"]
        
        try:
            # We don't have the agent pass indices explicitly as that's too hard for the LLM.
            # Instead, we just keep the last 4 turns and remove everything else.
            # This is a simplified filtering.
            await stm.trim_to_recent(session_id, keep_last=4)
            
            return ToolResult(
                status="success",
                data={},
                message=f"Đã lọc bỏ các ngữ cảnh không liên quan thành công (Lý do: {reason})."
            )
                
        except Exception as exc:
            logger.error("filter_irrelevant_context failed: %s", exc)
            return ToolResult(
                status="error",
                data={"error": str(exc)},
                message=f"Lỗi khi lọc ngữ cảnh: {exc}"
            )
