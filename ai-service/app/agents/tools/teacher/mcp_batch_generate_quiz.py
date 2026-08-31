"""Validate quiz packages authored by an external MCP client model."""
from __future__ import annotations

import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

settings = get_settings()


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

        try:
            bank_items = await _save_to_question_bank(
                course_id=course_id,
                user_id=int(kwargs.get("_user_id") or 0),
                quizzes=normalized,
            )
        except ValueError as exc:
            return ToolResult(status="error", data={"error": "question_bank_save_failed"}, message=str(exc))
        except Exception:
            return ToolResult(
                status="error", data={"error": "question_bank_save_failed"},
                message="Questions were validated but could not be saved to the LMS Question Bank.",
            )

        return ToolResult(
            status="success",
            data={
                "course_id": course_id, "quizzes": normalized,
                "question_count": total, "bank_item_ids": [item.get("id") for item in bank_items if isinstance(item, dict)],
                "state": "SAVED_TO_QUESTION_BANK_DRAFT",
            },
            message=f"Saved {len(bank_items)} externally authored questions as drafts in the LMS Question Bank. Review and select them to assemble a quiz.",
        )


async def _save_to_question_bank(*, course_id: int, user_id: int, quizzes: list[dict]) -> list[dict]:
    items: list[dict] = []
    for quiz in quizzes:
        for question in quiz["questions"]:
            items.append({
                "node_id": quiz["node_id"],
                "question_type": "SINGLE_CHOICE",
                "question_text": question["question"],
                "explanation": question["explanation"],
                "points": 10,
                "difficulty": "MEDIUM",
                "answer_options": [
                    {"option_text": option, "is_correct": index == question["correct_index"], "order_index": index}
                    for index, option in enumerate(question["options"])
                ],
                "correct_answers": [],
                "settings": {},
                "tags": ["mcp", "external-ai"],
                "source": "AI_GENERATED",
                "status": "DRAFT",
            })
    headers = {"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)}
    url = f"{settings.lms_service_url.rstrip('/')}/api/v1/courses/{course_id}/question-bank"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json={"items": items}, headers=headers)
    if response.status_code not in (200, 201):
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or response.text
        except ValueError:
            message = response.text
        raise ValueError(f"LMS Question Bank rejected the draft (HTTP {response.status_code}): {message[:500]}")
    body = response.json()
    data = body.get("data", body) if isinstance(body, dict) else body
    return data if isinstance(data, list) else []
