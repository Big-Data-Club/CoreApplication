"""
Teacher Tool: parse_quiz_questions

Parses raw, unformatted text (copy-pasted by the teacher) into structured
quiz questions and presents them in a HITL widget for review before saving
to a specific quiz.

The teacher can paste text from:
- Exam papers, textbooks, websites
- Fill-in-the-blank sentences with "..." or "___"
- Multiple choice questions in any format

The LLM auto-detects question types (SINGLE_CHOICE, FILL_BLANK_TEXT, etc.)
without requiring any specific input format.
"""
from __future__ import annotations

import logging
from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ParseQuizQuestionsTool(BaseTool):
    name = "parse_quiz_questions"
    description = (
        "Parse raw text (pasted by the teacher) into structured quiz questions "
        "and add them to an existing quiz. Use this tool when a teacher pastes "
        "question text and wants it imported into a quiz - e.g., "
        "'thêm câu hỏi này vào quiz', 'parse câu hỏi sau vào bài kiểm tra', "
        "'nhập câu hỏi sau đây', 'import these questions'. "
        "The tool auto-detects question types (trắc nghiệm, điền từ, tự luận, ...). "
        "Requires quiz_id and the raw question text. If quiz_id is not provided, "
        "ask the teacher which quiz they want to add questions to."
    )
    parameters = {
        "type": "object",
        "properties": {
            "raw_text": {
                "type": "string",
                "description": (
                    "The raw unformatted text containing one or more quiz questions. "
                    "Can include multiple-choice options, fill-in-the-blank blanks, etc."
                ),
            },
            "quiz_id": {
                "type": "integer",
                "description": (
                    "The ID of the quiz to add questions to. "
                    "REQUIRED. Ask the teacher if unknown."
                ),
            },
            "points_per_question": {
                "type": "integer",
                "description": "Default points assigned to each parsed question. Default: 10.",
                "default": 10,
            },
        },
        "required": ["raw_text", "quiz_id"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.services.quiz_parse_service import quiz_parse_service

        raw_text: str = kwargs.get("raw_text", "").strip()
        quiz_id: int | None = kwargs.get("quiz_id")
        points_per_question: int = int(kwargs.get("points_per_question", 10))
        # Injected context
        course_id: int | None = kwargs.get("_course_id")
        user_id: int = kwargs.get("_user_id", 0)

        if not raw_text:
            return ToolResult(
                status="error",
                data={"error": "empty_text"},
                message="Vui lòng cung cấp nội dung câu hỏi cần parse.",
            )

        if not quiz_id:
            return ToolResult(
                status="error",
                data={"error": "missing_quiz_id"},
                message=(
                    "Cần cung cấp quiz_id. "
                    "Bạn muốn thêm câu hỏi vào quiz nào? (cung cấp ID của quiz)"
                ),
            )

        try:
            questions = await quiz_parse_service.parse(
                raw_text=raw_text,
                points_per_question=points_per_question,
            )
        except Exception as e:
            logger.error("parse_quiz_questions tool: LLM parse failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi khi phân tích câu hỏi: {e}",
            )

        if not questions:
            return ToolResult(
                status="error",
                data={"error": "no_questions_found"},
                message=(
                    "Không tìm thấy câu hỏi nào trong văn bản. "
                    "Hãy đảm bảo văn bản chứa câu hỏi rõ ràng."
                ),
            )

        # Assign preview IDs for frontend widget tracking
        for i, q in enumerate(questions):
            q["preview_id"] = i + 1

        return ToolResult(
            status="pending_human_approval",
            data={
                "questions": questions,
                "quiz_id": quiz_id,
                "count": len(questions),
            },
            message=(
                f"Đã phân tích được {len(questions)} câu hỏi từ văn bản. "
                f"Vui lòng xem lại và xác nhận để thêm vào Quiz #{quiz_id}."
            ),
            ui_instruction={
                "component": "QuizImportPreview",
                "props": {
                    "questions": questions,
                    "quiz_id": quiz_id,
                    "course_id": course_id,
                },
            },
        )
