"""
Mentor Tool: explain_concept

Uses RAG + LLM to explain a concept, adapting the explanation depth
based on the student's mastery level. Does NOT just return raw chunks —
it synthesizes an explanation tailored to the student.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ExplainConceptTool(BaseTool):
    name = "explain_concept"
    description = (
        "Explain a concept to the student using course materials as context. "
        "The explanation adapts to the student's mastery level — simpler for "
        "beginners, deeper for advanced students. Use when the student asks "
        "to explain something, or when you need to teach a concept."
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
        from app.core.llm import chat_complete
        from app.core.llm_gateway import TASK_CHAT
        from app.services.rag_service import rag_service

        concept = kwargs["concept"]
        course_id = kwargs.get("_course_id") or kwargs["course_id"]
        depth = kwargs.get("depth")
        language = kwargs.get("language", "vi")
        student_id = kwargs.get("_user_id", 0)

        try:
            # 1. Auto-detect depth from mastery if not provided
            if not depth:
                from app.services.mastery_service import mastery_service
                weaknesses = await mastery_service.get_user_struggles(
                    user_id=student_id, course_id=course_id,
                )
                if weaknesses and any(w["mastery_level"] < 0.3 for w in weaknesses):
                    depth = "beginner"
                elif weaknesses and any(w["mastery_level"] < 0.6 for w in weaknesses):
                    depth = "intermediate"
                else:
                    depth = "intermediate"  # default

            # 2. RAG context — depth-adaptive retrieval
            depth_top_k = {"beginner": 3, "intermediate": 5, "advanced": 8}
            top_k = depth_top_k.get(depth, 5)
            chunks = await rag_service.search_multilingual(
                query=concept, course_id=course_id, top_k=top_k,
            )
            context = "\n---\n".join(c.chunk_text for c in chunks) if chunks else ""

            # 3. Depth-specific instructions
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

            system_prompt = (
                f"You are an expert tutor. {lang_note}\n"
                f"{depth_instructions.get(depth, depth_instructions['intermediate'])}\n\n"
                f"Use the following course materials as primary source:\n"
                f"{context if context else '(No specific materials found, use general knowledge)'}\n\n"
                f"Format: Use markdown with headers, bullet points, and code blocks "
                f"where appropriate. Keep it focused and educational."
            )

            explanation = await chat_complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Explain: {concept}"},
                ],
                temperature=0.4,
                max_tokens=1500,
                task=TASK_CHAT,
            )

            return ToolResult(
                status="success",
                data={
                    "explanation": explanation,
                    "concept": concept,
                    "depth": depth,
                    "source_count": len(chunks),
                },
                message=f"Giải thích '{concept}' ở mức {depth}.",
            )

        except Exception as e:
            logger.error("explain_concept failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi: {e}",
            )
