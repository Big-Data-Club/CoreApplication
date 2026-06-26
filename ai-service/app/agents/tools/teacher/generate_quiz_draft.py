"""
Teacher Tool: generate_quiz_draft

Wraps quiz_service.generate_for_node() to create quiz questions
as DRAFTs. The teacher must approve them via the HITL widget
before they are published to the LMS.
"""
from __future__ import annotations

import logging
import httpx
from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GenerateQuizDraftTool(BaseTool):
    name = "generate_quiz_draft"
    description = (
        "Generate a QUIZ draft (multiple-choice questions, title, time "
        "limit, suggested section). Use this tool for ANY request that "
        "involves creating quizzes, tests, questions, or assessments - "
        "e.g. 'tạo quiz', 'tạo thêm quiz', 'tạo bài kiểm tra', "
        "'ra đề trắc nghiệm', 'làm câu hỏi cho chương này'.\n"
        "Requires a valid course_id AND node_id. If you don't have them, "
        "call `list_my_courses` and `list_knowledge_nodes` FIRST - never "
        "fabricate these IDs. The teacher reviews and publishes the draft "
        "via the HITL widget."
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
                "description": (
                    "The knowledge node ID (topic) to generate questions about. "
                    "MUST be a valid ID obtained from list_knowledge_nodes. "
                    "Do NOT guess this value."
                ),
            },
            "bloom_levels": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["remember", "understand", "apply",
                             "analyze", "evaluate", "create"],
                },
                "description": "Bloom taxonomy levels for question difficulty.",
            },
            "num_questions_per_level": {
                "type": "integer",
                "description": "Number of questions per level. Default: 2.",
                "default": 2,
            },
            "language": {
                "type": "string",
                "enum": ["vi", "en"],
                "default": "vi",
            },
            "preferred_title": {
                "type": "string",
                "description": "Optional specific title the user wants for the quiz.",
            }
        },
        "required": ["course_id", "node_id"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.services.quiz_service import quiz_gen_service
        from app.core.llm import chat_complete_json
        from app.core.llm_gateway import TASK_CHAT

        course_id = kwargs.get("_course_id") or kwargs["course_id"]
        node_id = kwargs["node_id"]
        bloom_levels = kwargs.get("bloom_levels")
        num_per_level = kwargs.get("num_questions_per_level", 2)
        language = kwargs.get("language", "vi")
        created_by = kwargs.get("_user_id", 0)
        preferred_title = kwargs.get("preferred_title")

        try:
            # 0. Pre-validate node_id exists - catch hallucinated IDs early
            from app.core.database import get_ai_conn

            async with get_ai_conn() as conn:
                node = await conn.fetchrow(
                    "SELECT id, name FROM knowledge_nodes "
                    "WHERE id = $1 AND course_id = $2",
                    node_id, course_id,
                )
            if not node:
                return ToolResult(
                    status="error",
                    data={"error": "invalid_node_id", "node_id": node_id},
                    message=(
                        f"node_id={node_id} không tồn tại trong khóa học {course_id}. "
                        "Hãy gọi `list_knowledge_nodes` trước để lấy danh sách node_id hợp lệ. "
                        "Nếu không có node nào, giáo viên cần index tài liệu khóa học trước."
                    ),
                )

            # 1. Generate the questions via service
            gen_ids = await quiz_gen_service.generate_for_node(
                node_id=node_id,
                course_id=course_id,
                created_by=created_by,
                bloom_levels=bloom_levels,
                language=language,
                questions_per_level=num_per_level,
            )

            # Fetch the generated drafts
            drafts = await quiz_gen_service.list_drafts(
                course_id=course_id, node_id=node_id,
            )
            new_drafts = [d for d in drafts if d.get("id") in gen_ids]

            # 2. Fetch existing sections for suggestion
            sections = []
            lms_base = settings.lms_service_url.rstrip("/")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{lms_base}/api/v1/courses/{course_id}/sections",
                    headers={"X-API-Secret": settings.ai_service_secret},
                )
                if resp.status_code == 200:
                    sections = resp.json().get("data") or []

            # 3. Use LLM to suggest Title, Time, and Section
            topic_name = new_drafts[0].get("node_name", "Chủ đề hiện tại") if new_drafts else "Quiz mới"
            section_list_str = "\n".join([f"- ID {s['id']}: {s['title']}" for s in sections])
            
            lang_note = "Trả về bằng tiếng Việt." if language == "vi" else "Respond in English."
            
            prompt = (
                f"Dựa trên các câu hỏi vừa tạo cho chủ đề '{topic_name}', hãy đề xuất cấu hình cho Quiz Activity này.\n"
                f"{lang_note}\n\n"
                f"Input:\n"
                f"- Số lượng câu hỏi: {len(new_drafts)}\n"
                f"- Độ khó: {', '.join(bloom_levels) if bloom_levels else 'Đa dạng'}\n"
                f"- Các chương hiện có:\n{section_list_str if sections else '(Trống)'}\n\n"
                f"Hãy trả về JSON với các key:\n"
                f"- 'quiz_title': Tiêu đề phù hợp (Gợi ý: {preferred_title if preferred_title else topic_name})\n"
                f"- 'time_limit_minutes': Thời gian làm bài hợp lý (10-60 phút)\n"
                f"- 'suggested_section_id': ID của chương phù hợp nhất để đặt quiz này (hoặc null)\n"
                f"- 'description': Một mô tả ngắn gọn (1-2 câu)"
            )

            suggestion = await chat_complete_json(
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                task=TASK_CHAT,
            )

            preview_data = []
            for d in new_drafts:
                preview_data.append({
                    "gen_id": d["id"],
                    "bloom_level": d.get("bloom_level", ""),
                    "question_text": d.get("question_text", ""),
                    "question_type": d.get("question_type", "SINGLE_CHOICE"),
                    "answer_options": d.get("answer_options", []),
                    "explanation": d.get("explanation", ""),
                    "node_name": d.get("node_name", ""),
                })

            return ToolResult(
                status="pending_human_approval",
                data={
                    **suggestion,
                    "drafts": preview_data,
                },
                message=f"Đã tạo {len(gen_ids)} câu hỏi nháp về '{topic_name}'. Vui lòng cấu hình và xuất bản quiz.",
                ui_instruction={
                    "component": "QuizCreationWizard",
                    "props": {
                        "drafts": preview_data,
                        "course_id": course_id,
                        "node_id": node_id,
                        "initial_config": suggestion
                    },
                },
            )

        except Exception as e:
            logger.error("generate_quiz_draft failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi khi tạo quiz: {e}",
            )

