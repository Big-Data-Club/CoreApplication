"""Validate quiz packages authored by an external MCP client model."""
from __future__ import annotations

from app.agents.tools.base_tool import BaseTool, ToolResult


class McpBatchGenerateQuizTool(BaseTool):
    name = "mcp_batch_generate_quiz"
    description = (
        "Validate quiz questions authored by your external AI model against knowledge nodes "
        "in one owned course. No BDC LLM is called. Use list_knowledge_nodes first."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "integer"},
            "quizzes": {
                "type": "array", "minItems": 1, "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "integer"},
                        "title": {"type": "string", "maxLength": 200},
                        "questions": {
                            "type": "array", "minItems": 1, "maxItems": 20,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string", "maxLength": 1000},
                                    "options": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string", "maxLength": 500}},
                                    "correct_index": {"type": "integer", "minimum": 0, "maximum": 5},
                                    "explanation": {"type": "string", "maxLength": 1500},
                                },
                                "required": ["question", "options", "correct_index"],
                            },
                        },
                    },
                    "required": ["node_id", "title", "questions"],
                },
            },
        },
        "required": ["course_id", "quizzes"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        course_id = int(kwargs.get("course_id") or 0)
        quizzes = kwargs.get("quizzes") or []
        if not course_id or not isinstance(quizzes, list) or not 1 <= len(quizzes) <= 20:
            return ToolResult(status="error", data={"error": "invalid_quiz_batch"}, message="Provide 1–20 quiz packages.")

        node_ids = [int(q.get("node_id") or 0) for q in quizzes if isinstance(q, dict)]
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                "SELECT id FROM knowledge_nodes WHERE course_id = $1 AND id = ANY($2::bigint[])",
                course_id, node_ids,
            )
        valid_nodes = {int(row["id"]) for row in rows}
        if set(node_ids) != valid_nodes:
            return ToolResult(status="error", data={"error": "invalid_node_ids"}, message="Every node_id must belong to the selected course.")

        normalized = []
        total = 0
        for quiz in quizzes:
            questions = quiz.get("questions") or []
            if not 1 <= len(questions) <= 20:
                return ToolResult(status="error", data={"error": "invalid_questions"}, message="Each quiz needs 1–20 questions.")
            clean_questions = []
            for question in questions:
                stem = str(question.get("question") or "").strip()[:1000]
                options = [str(v).strip()[:500] for v in (question.get("options") or [])]
                correct = question.get("correct_index")
                if not stem or not 2 <= len(options) <= 6 or not isinstance(correct, int) or not 0 <= correct < len(options) or any(not v for v in options):
                    return ToolResult(status="error", data={"error": "invalid_question"}, message="A question has an invalid stem, options, or correct_index.")
                clean_questions.append({"question": stem, "options": options, "correct_index": correct, "explanation": str(question.get("explanation") or "")[:1500]})
            total += len(clean_questions)
            normalized.append({"node_id": int(quiz["node_id"]), "title": str(quiz.get("title") or "Quiz")[:200], "questions": clean_questions})

        return ToolResult(
            status="success",
            data={"course_id": course_id, "quizzes": normalized, "question_count": total, "state": "VALIDATED_DRAFT"},
            message=f"Validated {total} externally authored questions. Review them before publishing in LMS.",
        )
