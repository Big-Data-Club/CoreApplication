"""
Mentor Tool: explain_concept

GraphRAG-upgraded concept explanation tool.

Changes from v1:
  - Fetches prerequisite chain from Neo4j for the query concept.
  - Injects concept map (prerequisites, related concepts, mastery signals)
    into the LLM system prompt before generating the explanation.
  - LLM now knows: "student needs to understand A and B before C",
    and adapts explanation depth + structure accordingly.
  - Falls back gracefully to standard RAG when Neo4j is unavailable.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ExplainConceptTool(BaseTool):
    name = "explain_concept"
    description = (
        "Explain a concept to the student using course materials and knowledge graph context. "
        "The explanation adapts to the student's mastery level AND the concept's prerequisite "
        "structure - explaining foundational concepts first if the student has gaps. "
        "Use when the student asks to explain something, or when you need to teach a concept."
    )
    parameters = {
        "type": "object",
        "properties": {
            "concept": {
                "type": "string",
                "description": "The concept to explain.",
            },
            "course_id": {
                "type": "integer",
                "description": "The course ID for context.",
            },
            "depth": {
                "type": "string",
                "enum": ["beginner", "intermediate", "advanced"],
                "description": (
                    "Explanation depth. Auto-detected from student "
                    "mastery if not specified."
                ),
            },
            "language": {
                "type": "string",
                "enum": ["vi", "en"],
                "default": "vi",
            },
        },
        "required": ["concept", "course_id"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.core.config import get_settings
        from app.core.llm import chat_complete
        from app.core.llm_gateway import TASK_CHAT

        settings = get_settings()
        concept = kwargs["concept"]
        course_id = kwargs.get("_course_id") or kwargs.get("course_id")
        content_id = kwargs.get("_content_id") or kwargs.get("content_id")
        section_id = kwargs.get("_section_id") or kwargs.get("section_id")
        depth = kwargs.get("depth")
        language = kwargs.get("language", "vi")
        student_id = kwargs.get("_user_id", 0)

        execution_plan = kwargs.get("execution_plan")
        expansion_enabled = True
        max_expansion_level = "global"
        min_similarity = 0.25
        graph_expansion_needed = settings.graphrag_enabled

        if execution_plan:
            strategy = execution_plan.retrieval_strategy
            expansion_enabled = strategy.expansion_enabled
            max_expansion_level = strategy.max_expansion_level
            min_similarity = strategy.min_similarity
            graph_expansion_needed = getattr(execution_plan, "graph_expansion_needed", settings.graphrag_enabled)

        try:
            # ── 1. Auto-detect depth from mastery ──────────────────────────
            if not depth:
                try:
                    from app.services.mastery_service import mastery_service
                    weaknesses = await mastery_service.get_user_struggles(
                        user_id=student_id, course_id=course_id,
                    )
                    if weaknesses and any(w["mastery_level"] < 0.3 for w in weaknesses):
                        depth = "beginner"
                    elif weaknesses and any(w["mastery_level"] < 0.6 for w in weaknesses):
                        depth = "intermediate"
                    else:
                        depth = "intermediate"
                except Exception:
                    depth = "intermediate"

            # ── 2. Retrieve concept materials (GraphRAG or standard) ────────
            depth_top_k = {"beginner": 3, "intermediate": 5, "advanced": 8}
            top_k = depth_top_k.get(depth, 5)

            concept_map_text = ""
            prereq_chain_names: list[str] = []
            weak_prereqs: list[str] = []

            if settings.graphrag_enabled and graph_expansion_needed:
                from app.services.graphrag_service import graphrag_service
                from app.agents.core.context_formatter import graphrag_context_formatter

                # Fetch weak nodes for personalization
                weak_node_ids: list[int] = []
                if student_id:
                    try:
                        from app.agents.memory.ltm import ltm
                        weak_node_ids = await ltm.get_weak_nodes(
                            user_id=student_id,
                            course_id=course_id,
                            threshold=0.5,
                        )
                    except Exception:
                        pass

                ctx = await graphrag_service.retrieve(
                    query=concept,
                    course_id=course_id,
                    content_id=content_id,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    expansion_enabled=expansion_enabled,
                    max_expansion_level=max_expansion_level,
                    user_id=student_id,
                    weak_node_ids=weak_node_ids or None,
                )
                chunks = ctx.ranked_chunks

                # Build concept map text for LLM context
                concept_map_text = graphrag_context_formatter.format(ctx)

                # Extract prereq chain names for depth adjustment
                prereq_chain_names = [
                    (cn.name_vi or cn.name) for cn in ctx.prereq_chain
                ]
                # Extract weak prereqs
                if ctx.weak_nodes:
                    node_map = {cn.id: cn for cn in ctx.concept_nodes}
                    weak_in_prereq_ids = set(ctx.weak_nodes.keys()) & set(ctx.prereq_node_ids)
                    weak_prereqs = [
                        (node_map[nid].name_vi or node_map[nid].name)
                        for nid in weak_in_prereq_ids
                        if nid in node_map
                    ]

                # Auto-adjust depth: if student has weak prerequisites, start simpler
                if weak_prereqs and depth in ("intermediate", "advanced"):
                    depth = "beginner"
                    logger.debug(
                        "explain_concept: depth downgraded to beginner due to weak prereqs: %s",
                        weak_prereqs,
                    )

            else:
                # Standard RAG fallback
                from app.services.rag_service import rag_service
                chunks, _ = await rag_service.search_hierarchical(
                    query=concept,
                    course_id=course_id,
                    section_id=section_id,
                    content_id=content_id,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    expansion_enabled=expansion_enabled,
                    max_expansion_level=max_expansion_level,
                )

            context = "\n---\n".join(c.chunk_text for c in chunks) if chunks else ""

            # ── 3. Build LLM prompt ────────────────────────────────────────
            depth_instructions = {
                "beginner": (
                    "Explain like the student is seeing this for the first time. "
                    "Use simple language, analogies, and concrete examples. "
                    "Avoid jargon. Break complex ideas into small steps."
                ),
                "intermediate": (
                    "Explain with moderate detail. The student has basic knowledge. "
                    "Include key principles, common patterns, and 1-2 examples."
                ),
                "advanced": (
                    "Provide a deep, nuanced explanation. Include edge cases, "
                    "comparisons with related concepts, and real-world applications."
                ),
            }

            lang_note = "Trả lời bằng tiếng Việt." if language == "vi" else "Answer in English."

            # Build prerequisite guidance section
            prereq_guidance = ""
            if prereq_chain_names and len(prereq_chain_names) > 1:
                prereq_guidance = (
                    f"\n\n## Prerequisite Path\n"
                    f"To fully understand '{concept}', the student should know this chain:\n"
                    + " → ".join(prereq_chain_names)
                    + "\nBriefly confirm or reinforce earlier concepts in this chain before the main explanation."
                )
            if weak_prereqs:
                prereq_guidance += (
                    f"\n\n## Student Weakness Alert\n"
                    f"The student is WEAK at these prerequisite concepts: {', '.join(weak_prereqs)}. "
                    f"Start by briefly re-explaining these before the main concept."
                )

            system_prompt = (
                f"You are an expert tutor. {lang_note}\n"
                f"{depth_instructions.get(depth, depth_instructions['intermediate'])}\n"
                f"{prereq_guidance}\n\n"
                f"## Course Materials\n"
                f"{context if context else '(No specific materials found, use general knowledge)'}\n\n"
                f"{concept_map_text}\n\n"
                f"Format: Use markdown with headers, bullet points, and code blocks "
                f"where appropriate. Keep it focused and educational. "
                f"End with 1-2 thought-provoking questions to deepen understanding."
            )

            explanation = await chat_complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Explain: {concept}"},
                ],
                temperature=0.4,
                max_tokens=1800,
                task=TASK_CHAT,
            )

            return ToolResult(
                status="success",
                data={
                    "explanation": explanation,
                    "concept": concept,
                    "depth": depth,
                    "source_count": len(chunks),
                    "prereq_chain": prereq_chain_names,
                    "weak_prereqs": weak_prereqs,
                    "graph_expanded": bool(concept_map_text),
                },
                message=(
                    f"Giải thích '{concept}' ở mức {depth}."
                    + (f" (Dựa trên chuỗi tiên quyết: {' → '.join(prereq_chain_names[-3:])})" if prereq_chain_names else "")
                ),
            )

        except Exception as e:
            logger.error("explain_concept failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi: {e}",
            )
