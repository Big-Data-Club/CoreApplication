"""
Teacher Tool: trigger_auto_index

Publishes a Kafka event to trigger document indexing for newly
uploaded content. This is the async path - the actual indexing
is handled by the ai-worker Kafka consumer.

NOTE: This tool does NOT call the LMS to create content.
Content must already exist in lms-service. The teacher should
first upload content via the LMS UI, then use this tool to
trigger AI indexing if it wasn't triggered automatically.

HOW TO CREATE CONTENT IN LMS (manual steps):
1. Upload a document via POST /api/v1/courses/{id}/sections/{id}/content
2. The LMS automatically publishes a Kafka event (lms.document.uploaded)
3. ai-worker picks it up and indexes automatically

This tool is a MANUAL TRIGGER for re-indexing or forcing indexing
of content that wasn't auto-indexed.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class TriggerAutoIndexTool(BaseTool):
    name = "trigger_auto_index"
    description = (
        "Trigger AI indexing for a document or content that has been "
        "uploaded to the course. This creates embeddings and knowledge "
        "nodes from the document. Use when the teacher asks to index "
        "or re-index a specific document, or when content hasn't been "
        "indexed automatically."
    )
    parameters = {
        "type": "object",
        "properties": {
            "content_id": {
                "type": "integer",
                "description": "The content ID in the LMS to index.",
            },
            "course_id": {
                "type": "integer",
                "description": "The course this content belongs to.",
            },
        },
        "required": ["content_id", "course_id"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        content_id = kwargs["content_id"]
        course_id = kwargs.get("_course_id") or kwargs["course_id"]

        try:
            # Check if content is already indexed
            from app.core.database import get_ai_conn

            async with get_ai_conn() as conn:
                existing = await conn.fetchrow(
                    """SELECT status, error
                       FROM content_index_status
                       WHERE content_id = $1""",
                    content_id,
                )

            if existing and existing["status"] == "ready":
                # Content already indexed - offer re-index
                return ToolResult(
                    status="success",
                    data={
                        "content_id": content_id,
                        "already_indexed": True,
                        "current_status": "ready",
                    },
                    message=(
                        f"Nội dung {content_id} đã được index. "
                        f"Sử dụng reindex nếu muốn cập nhật."
                    ),
                )

            if existing and existing["status"] == "processing":
                return ToolResult(
                    status="success",
                    data={
                        "content_id": content_id,
                        "current_status": "processing",
                    },
                    message=f"Nội dung {content_id} đang được index.",
                )

            # Publish reindex command via existing service
            from app.services.reindex_service import reindex_service

            job_id = await reindex_service.start_reindex(
                content_id=content_id, course_id=course_id,
            )

            return ToolResult(
                status="success",
                data={
                    "content_id": content_id,
                    "course_id": course_id,
                    "job_id": job_id,
                    "status": "pending",
                },
                message=(
                    f"Đã bắt đầu index nội dung {content_id}. "
                    f"Quá trình có thể mất vài phút."
                ),
            )

        except Exception as e:
            logger.error("trigger_auto_index failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi khi trigger indexing: {e}",
            )
