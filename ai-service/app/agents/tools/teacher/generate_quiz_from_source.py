"""Generate quiz questions from lesson text already available to the teacher agent."""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class GenerateQuizFromSourceTool(BaseTool):
    name = "generate_quiz_from_source"
    description = (
        "Generate NEW quiz questions directly from lesson text, pasted notes, or "
        "question examples already present in the conversation/page, then show an "
        "approval preview for an existing quiz. Use this when the teacher asks for "
        "more/additional questions based on supplied content. This path does NOT "
        "require an indexed knowledge node. Do not use it to import an already-written "
        "question verbatim; use parse_quiz_questions for that."
    )
    parameters = {
        "type": "object",
        "properties": {
            "quiz_id": {
                "type": "integer",
                "description": "Target quiz ID, normally from the current page context.",
            },
            "source_text": {
                "type": "string",
                "description": (
                    "Authoritative lesson text, notes, or representative questions from "
                    "the current page/conversation. Include enough facts to ground answers."
                ),
            },
            "num_questions": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 3,
            },
            "language": {
                "type": "string",
                "description": "Output language code requested by the teacher, such as en or vi.",
                "default": "en",
            },
            "question_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "SINGLE_CHOICE", "MULTIPLE_CHOICE", "FILL_BLANK_TEXT",
                        "FILL_BLANK_DROPDOWN", "SHORT_ANSWER", "ESSAY",
                    ],
                },
                "description": "Allowed formats. Default: a useful mix of choice questions.",
            },
            "difficulty": {
                "type": "string",
                "enum": ["easy", "medium", "hard", "mixed"],
                "default": "mixed",
            },
            "instructions": {
                "type": "string",
                "description": (
                    "Teacher constraints such as learning outcomes, style, dropdown blanks, "
                    "or desired cognitive level."
                ),
            },
            "existing_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Existing stems to avoid duplicating.",
            },
            "points_per_question": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 10,
            },
        },
        "required": ["quiz_id", "source_text"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.services.quiz_parse_service import quiz_parse_service

        quiz_id = kwargs.get("quiz_id")
        source_text = str(kwargs.get("source_text") or "").strip()
        course_id = kwargs.get("_course_id")
        language = str(kwargs.get("language") or "en")

        if not quiz_id:
            return ToolResult(
                status="error",
                data={"error": "missing_quiz_id"},
                message="Please open or specify the target quiz before generating questions.",
            )
        if not source_text:
            return ToolResult(
                status="error",
                data={"error": "missing_source_text"},
                message="Please provide lesson content or notes to ground the new questions.",
            )

        try:
            questions = await quiz_parse_service.generate_from_source(
                source_text=source_text,
                num_questions=kwargs.get("num_questions", 3),
                language=language,
                question_types=kwargs.get("question_types"),
                difficulty=kwargs.get("difficulty", "mixed"),
                instructions=str(kwargs.get("instructions") or ""),
                existing_questions=kwargs.get("existing_questions"),
                points_per_question=kwargs.get("points_per_question", 10),
            )
        except Exception as exc:
            logger.error("generate_quiz_from_source failed: %s", exc)
            return ToolResult(
                status="error",
                data={"error": str(exc)},
                message="I couldn't generate grounded quiz questions from that source.",
            )

        if not questions:
            return ToolResult(
                status="error",
                data={"error": "no_valid_questions"},
                message="No valid questions were generated. Please provide more source detail.",
            )

        for i, question in enumerate(questions):
            question["preview_id"] = i + 1

        if language.lower().startswith("vi"):
            message = (
                f"Đã tạo {len(questions)} câu hỏi mới dựa trên nội dung được cung cấp. "
                f"Vui lòng xem lại trước khi thêm vào Quiz #{quiz_id}."
            )
        else:
            message = (
                f"Created {len(questions)} new questions grounded in the supplied content. "
                f"Please review them before adding them to Quiz #{quiz_id}."
            )

        return ToolResult(
            status="pending_human_approval",
            data={"questions": questions, "quiz_id": quiz_id, "count": len(questions)},
            message=message,
            ui_instruction={
                "component": "QuizImportPreview",
                "props": {
                    "questions": questions,
                    "quiz_id": quiz_id,
                    "course_id": course_id,
                },
            },
        )
