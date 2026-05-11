"""
Mentor Tool: summarize_past_turns

Allows the agent to compress old STM messages into a summary.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.agents.memory.stm import stm

logger = logging.getLogger(__name__)

class SummarizePastTurnsTool(BaseTool):
    name = "summarize_past_turns"
    description = (
        "Nén các lượt hội thoại cũ thành một bản tóm tắt ngắn gọn. "
        "Sử dụng công cụ này KHI hệ thống cảnh báo rằng bộ nhớ sắp đầy. "
        "Bản tóm tắt sẽ thay thế các tin nhắn cũ để giải phóng không gian bộ nhớ."
    )
    parameters = {
        "type": "object",
        "properties": {
            "summary_text": {
                "type": "string",
                "description": "Bản tóm tắt cực kỳ ngắn gọn của các trao đổi cũ, giữ lại các thông tin ngữ cảnh quan trọng."
            }
        },
        "required": ["summary_text"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        session_id = kwargs.get("_session_id")
        
        if not session_id:
            return ToolResult(
                status="error",
                data={},
                message="Internal error: session_id is missing."
            )
            
        summary_text = kwargs["summary_text"]
        
        try:
            await stm.summarize_and_replace(
                session_id=session_id,
                summary_text=summary_text,
                keep_last=4  # Keep last 4 messages (2 user, 2 assistant)
            )
            
            return ToolResult(
                status="success",
                data={},
                message="Đã tóm tắt và dọn dẹp các tin nhắn cũ thành công để giải phóng bộ nhớ."
            )
                
        except Exception as exc:
            logger.error("summarize_past_turns failed: %s", exc)
            return ToolResult(
                status="error",
                data={"error": str(exc)},
                message=f"Lỗi khi tóm tắt tin nhắn: {exc}"
            )
