"""
Teacher MCP Automation Tool: mcp_index_files

Headless tool to trigger automated indexing (embeddings, knowledge graph extraction)
for a list of LMS content IDs or uploaded material files.
"""
from __future__ import annotations

import logging
from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class McpIndexFilesTool(BaseTool):
    name = "mcp_index_files"
    description = (
        "Headless file indexing: Batch triggers AI indexing (embedding generation & knowledge graph "
        "extraction into Qdrant + Neo4j) for multiple content IDs or uploaded files in a course. "
        "Use when an external MCP client wants to index multiple files programmatically."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "integer",
                "description": "Course ID to index materials for.",
            },
            "content_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of content IDs in LMS to trigger indexing for.",
            },
        },
        "required": ["course_id", "content_ids"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        course_id = kwargs.get("_course_id") or kwargs.get("course_id")
        content_ids: list[int] = kwargs.get("content_ids") or []

        if not course_id:
            return ToolResult(
                status="error",
                data={"error": "missing_course_id"},
                message="course_id is required for batch indexing.",
            )
        if not content_ids:
            return ToolResult(
                status="error",
                data={"error": "missing_content_ids"},
                message="At least one content_id must be provided to index.",
            )
        if len(content_ids) > 20 or any(not isinstance(cid, int) or cid <= 0 for cid in content_ids):
            return ToolResult(
                status="error",
                data={"error": "invalid_content_ids"},
                message="Provide at most 20 positive content IDs.",
            )

        try:
            from app.services.reindex_service import reindex_service
            from app.core.database import get_ai_conn

            async with get_ai_conn() as conn:
                rows = await conn.fetch(
                    "SELECT content_id FROM content_index_status WHERE course_id = $1 AND content_id = ANY($2::bigint[])",
                    int(course_id), content_ids,
                )
            valid_ids = {int(row["content_id"]) for row in rows}
            if valid_ids != set(content_ids):
                return ToolResult(
                    status="error",
                    data={"error": "content_course_mismatch"},
                    message="Every content_id must already belong to the selected course.",
                )

            indexing_jobs = []
            for cid in content_ids:
                try:
                    job_id = await reindex_service.start_reindex(
                        content_id=cid,
                        course_id=int(course_id),
                    )
                    indexing_jobs.append({
                        "content_id": cid,
                        "job_id": job_id,
                        "status": "triggered",
                    })
                except Exception as c_exc:
                    logger.warning("Indexing trigger failed for content %s: %s", cid, c_exc)
                    indexing_jobs.append({
                        "content_id": cid,
                        "status": "failed",
                        "error": str(c_exc),
                    })

            return ToolResult(
                status="success",
                data={
                    "course_id": int(course_id),
                    "total_requested": len(content_ids),
                    "jobs": indexing_jobs,
                },
                message=(
                    f"Đã kích hoạt index tự động cho {len(indexing_jobs)} nội dung "
                    f"trong khóa học #{course_id}."
                ),
            )
        except Exception as exc:
            logger.exception("mcp_index_files failed: %s", exc)
            return ToolResult(
                status="error",
                data={"error": str(exc)},
                message=f"File indexing failed: {exc}",
            )
