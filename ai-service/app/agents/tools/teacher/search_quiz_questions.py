"""Read-only teacher retrieval; quiz authority is rechecked by LMS per call."""

from types import SimpleNamespace

from app.agents.tools.base_tool import BaseTool, ToolResult, sanitize_query
from app.services import quiz_index_service


class SearchQuizQuestionsTool(BaseTool):
    name = "search_quiz_questions"
    description = (
        "Search an indexed quiz managed by the current teacher. Requires a verified quiz ID; "
        "never guess it. Returns assessment questions, not answer keys or verified learning facts. "
        "Use for finding assessment coverage or questions about a concept. "
        "The quiz corpus is separate from course materials and is unavailable to student agents."
    )
    parameters = {
        "type": "object",
        "properties": {
            "quiz_id": {"type": "integer", "minimum": 1},
            "query": {"type": "string", "maxLength": 240},
        },
        "required": ["quiz_id", "query"],
        "additionalProperties": False,
    }

    async def execute(self, **kwargs) -> ToolResult:
        user_id, course_id = kwargs.get("_user_id"), kwargs.get("_course_id")
        quiz_id, query = kwargs.get("quiz_id"), sanitize_query(kwargs.get("query"))
        if (
            not user_id
            or not course_id
            or not isinstance(quiz_id, int)
            or quiz_id <= 0
            or not query
        ):
            return ToolResult(
                status="error",
                data={"error": "verified_scope_required"},
                message="Cần xác định quiz và khóa học trước khi tìm.",
            )
        try:
            head = await quiz_index_service.source(quiz_id, user_id, head=True)
            if head["course_id"] != course_id:
                raise ValueError("course_scope_mismatch")
            result = await quiz_index_service.search(
                SimpleNamespace(
                    quiz_id=quiz_id,
                    course_id=course_id,
                    revision=head["data"]["revision"],
                    query=query,
                )
            )
            return ToolResult(
                status="success",
                data={
                    "quiz_id": quiz_id,
                    "course_id": course_id,
                    "source_type": "assessment_question",
                    "questions": [
                        {
                            **item,
                            "content": item["content"][:1200],
                            "excerpted": len(item["content"]) > 1200,
                        }
                        for item in result["items"][:5]
                    ],
                    "total_matches": len(result["items"]),
                },
                message=f"Tìm thấy {len(result['items'])} câu hỏi trong quiz.",
            )
        except Exception:
            return ToolResult(
                status="error",
                data={"error": "quiz_unavailable_or_stale"},
                message="Không truy cập được quiz hoặc index cần cập nhật. Không có dữ liệu câu hỏi được trả về.",
            )
