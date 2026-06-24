"""
Mentor Tool: search_materials

RAG search over course materials. Returns relevant document chunks
that the mentor can use to answer knowledge questions accurately.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SearchMaterialsTool(BaseTool):
    name = "search_course_materials"
    description = (
        "Search course materials using semantic search. Returns relevant "
        "document excerpts from indexed course content. Use when the student "
        "asks a knowledge question and you need to find the answer in the "
        "course materials, or when you want to reference specific content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query — the concept or question to look up.",
            },
            "course_id": {
                "type": "integer",
                "description": "Optional: filter search to a specific course ID. Omit to search across all courses.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return. Default: 3.",
                "default": 3,
            },
        },
        "required": ["query"],  # course_id is OPTIONAL — Mentor agent is cross-course
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.services.rag_service import rag_service

        query = kwargs["query"]
        # course_id is optional — use injected context or LLM-provided value
        course_id: int | None = kwargs.get("_course_id") or kwargs.get("course_id")
        # content_id and node_id are injected from active page/lesson context
        content_id: int | None = kwargs.get("_content_id") or kwargs.get("content_id")
        node_id: int | None = kwargs.get("_node_id") or kwargs.get("node_id")
        top_k = kwargs.get("top_k", 3)

        try:
            chunks = await rag_service.search_multilingual(
                query=query,
                course_id=course_id,
                content_id=content_id,
                node_id=node_id,
                top_k=top_k,
            )

            if not chunks:
                return ToolResult(
                    status="success",
                    data={"chunks": [], "query": query},
                    message=(
                        f"Không tìm thấy tài liệu liên quan đến '{query}'. "
                        f"Nội dung khóa học có thể chưa được index."
                    ),
                )

            # Resolve document titles
            content_ids = list({c.content_id for c in chunks if c.content_id})
            titles = {}
            if content_ids:
                from app.core.database import get_ai_conn
                try:
                    async with get_ai_conn() as conn:
                        rows = await conn.fetch(
                            "SELECT content_id, title FROM content_index_status WHERE content_id = ANY($1)",
                            content_ids
                        )
                        titles = {r["content_id"]: r["title"] for r in rows}
                except Exception as db_err:
                    logger.warning("Failed to fetch content titles: %s", db_err)

            results = [
                {
                    "text": c.chunk_text,
                    "similarity": round(c.similarity, 3),
                    "source_type": c.source_type,
                    "page_number": c.page_number,
                    "content_id": c.content_id,
                    "title": titles.get(c.content_id) or "Tài liệu học tập"
                }
                for c in chunks
            ]

            return ToolResult(
                status="success",
                data={"chunks": results, "query": query, "count": len(results)},
                message=f"Tìm thấy {len(results)} đoạn tài liệu liên quan.",
            )

        except Exception as e:
            logger.error("search_materials failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi tìm kiếm: {e}",
            )
