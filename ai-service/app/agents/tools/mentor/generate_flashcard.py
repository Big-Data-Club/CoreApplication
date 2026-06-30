"""
Mentor Tool: generate_flashcard

Generates flashcards for the student's weak areas.
Wraps the existing flashcard_service which handles RAG + LLM + DB persistence.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class GenerateFlashcardTool(BaseTool):
    name = "generate_flashcard"
    description = (
        "Generate flashcards for a specific topic to help the student "
        "memorize key concepts. Flashcards are saved to the database "
        "and automatically added to the spaced repetition schedule. "
        "Use when the student needs to review a topic, or when you "
        "identify a knowledge gap that can be addressed with flashcards."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "integer",
                "description": "The course ID.",
            },
            "node_id": {
                "type": "integer",
                "description": "The knowledge node (topic) to create flashcards for.",
            },
            "count": {
                "type": "integer",
                "description": "Number of flashcards to generate. Default: 3.",
                "default": 3,
                "minimum": 1,
                "maximum": 10,
            },
            "language": {
                "type": "string",
                "enum": ["vi", "en"],
                "default": "vi",
            },
        },
        "required": ["course_id", "node_id"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.services.flashcard_service import flashcard_srv

        course_id = kwargs.get("_course_id") or kwargs["course_id"]
        node_id = kwargs["node_id"]
        count = kwargs.get("count", 3)
        language = kwargs.get("language", "vi")
        student_id = kwargs.get("_user_id", 0)

        try:
            flashcards = await flashcard_srv.generate_flashcards_with_llm(
                student_id=student_id,
                node_id=node_id,
                course_id=course_id,
                count=count,
                language=language,
            )

            preview = [
                {
                    "id": fc.get("id"),
                    "front": fc.get("front_text", ""),
                    "back": fc.get("back_text", ""),
                }
                for fc in flashcards
            ]

            return ToolResult(
                status="success",
                data={
                    "flashcards": preview,
                    "count": len(preview),
                    "node_id": node_id,
                },
                message=f"Đã tạo {len(preview)} flashcard. Bắt đầu ôn tập!",
                ui_instruction={
                    "component": "FlashcardDeck",
                    "props": {
                        "cards": preview,
                        "flashcards": preview,
                        "course_id": course_id,
                        "node_id": node_id,
                    },
                },

            )

        except ValueError as e:
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=str(e),
            )
        except Exception as e:
            logger.error("generate_flashcard failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi tạo flashcard: {e}",
            )
