"""
Mentor Tool: search_materials

GraphRAG-upgraded RAG search over course materials.

Changes from v1:
  - Calls graphrag_service.retrieve() instead of rag_service.search_hierarchical()
    directly, enabling graph-augmented retrieval (concept graph expansion,
    prerequisite-aware re-ranking, neighbor chunk enrichment).
  - Returns concept_relationships and prereq_path in result data for the
    agent to reference in its response.
  - Falls back to standard RAG when graphrag_service is unavailable.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SearchMaterialsTool(BaseTool):
    name = "search_course_materials"
    description = (
        "Search course materials using semantic search and knowledge graph context. "
        "Returns relevant document excerpts from indexed course content, enriched "
        "with concept relationships and prerequisite signals. Use when the student "
        "asks a knowledge question and you need to find the answer in the "
        "course materials, or when you want to reference specific content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - the concept or question to look up.",
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
        "required": ["query"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.core.config import get_settings
        settings = get_settings()

        query = kwargs["query"]
        course_id: int | None = kwargs.get("_course_id") or kwargs.get("course_id")
        content_id: int | None = kwargs.get("_content_id") or kwargs.get("content_id")
        node_id: int | None = kwargs.get("_node_id") or kwargs.get("node_id")
        user_id: int | None = kwargs.get("_user_id")
        top_k = kwargs.get("top_k", 3)

        execution_plan = kwargs.get("execution_plan")
        expansion_enabled = True
        max_expansion_level = "global"
        min_similarity = 0.25
        graph_expansion_needed = settings.graphrag_enabled
        user_weakness_relevant = False

        if execution_plan:
            strategy = execution_plan.retrieval_strategy
            expansion_enabled = strategy.expansion_enabled
            max_expansion_level = strategy.max_expansion_level
            min_similarity = strategy.min_similarity
            top_k = strategy.depth or top_k
            # GraphRAG signals from Planner v2
            graph_expansion_needed = getattr(execution_plan, "graph_expansion_needed", settings.graphrag_enabled)
            user_weakness_relevant = getattr(execution_plan, "user_weakness_relevant", False)

        try:
            # ── GraphRAG path (default) ─────────────────────────────────────
            if settings.graphrag_enabled and graph_expansion_needed:
                from app.services.graphrag_service import graphrag_service
                from app.agents.core.context_formatter import graphrag_context_formatter

                # Fetch weak nodes if mastery is relevant
                weak_node_ids: list[int] = []
                if user_weakness_relevant and user_id:
                    try:
                        from app.agents.memory.ltm import ltm
                        weak_node_ids = await ltm.get_weak_nodes(
                            user_id=user_id,
                            course_id=course_id,
                            threshold=0.5,
                        )
                    except Exception as exc:
                        logger.debug("get_weak_nodes failed (non-fatal): %s", exc)

                ctx = await graphrag_service.retrieve(
                    query=query,
                    course_id=course_id,
                    content_id=content_id,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    expansion_enabled=expansion_enabled,
                    max_expansion_level=max_expansion_level,
                    user_id=user_id,
                    weak_node_ids=weak_node_ids or None,
                )
                chunks = ctx.ranked_chunks
                graph_meta = graphrag_context_formatter.format_for_tool_result(ctx)

            else:
                # ── Standard RAG fallback ───────────────────────────────────
                from app.services.rag_service import rag_service
                chunks, resolved_scope = await rag_service.search_hierarchical(
                    query=query,
                    course_id=course_id,
                    content_id=content_id,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    expansion_enabled=expansion_enabled,
                    max_expansion_level=max_expansion_level,
                )
                graph_meta = {"graph_expanded": False}

            logger.info(
                "search_course_materials query='%s' chunks=%d graph_expanded=%s",
                query, len(chunks), graph_meta.get("graph_expanded"),
            )

            if not chunks:
                return ToolResult(
                    status="success",
                    data={
                        "chunks": [],
                        "query": query,
                        "graph": graph_meta,
                    },
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
                    "node_id": c.node_id,
                    "title": titles.get(c.content_id) or "Tài liệu học tập"
                }
                for c in chunks
            ]

            return ToolResult(
                status="success",
                data={
                    "chunks": results,
                    "query": query,
                    "count": len(results),
                    "graph": graph_meta,
                },
                message=(
                    f"Tìm thấy {len(results)} đoạn tài liệu liên quan."
                    + (
                        f" (Mở rộng từ {graph_meta.get('seed_node_count', 0)} khái niệm "
                        f"sang {graph_meta.get('expanded_node_count', 0)} khái niệm liên quan qua Knowledge Graph.)"
                        if graph_meta.get("graph_expanded") else ""
                    )
                ),
            )

        except Exception as e:
            logger.error("search_materials failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi tìm kiếm: {e}",
            )
