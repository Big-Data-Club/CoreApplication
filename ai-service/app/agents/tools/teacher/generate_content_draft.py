"""
Teacher Tool: generate_content_draft

Uses LLM to generate text-based content drafts (outlines, summaries,
slide structures) based on course materials. The output is a DRAFT
that the teacher reviews before publishing.
"""
from __future__ import annotations

import logging
import httpx
from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GenerateContentDraftTool(BaseTool):
    name = "generate_content_draft"
    description = (
        "Generate a TEXT-BASED content draft such as a lesson outline, "
        "summary, slide structure, lesson plan, or explanation for a "
        "topic, based on existing course materials (RAG). Outputs markdown "
        "for the teacher to review.\n"
        "DO NOT use this tool to create quizzes, questions, flashcards, or "
        "exercises - use `generate_quiz_draft` for quizzes. "
        "The `content_type` parameter MUST be one of: outline, summary, "
        "slide_structure, lesson_plan, explanation. No other value is "
        "accepted. "
        "If you don't know the course_id, call `list_my_courses` first."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "integer",
                "description": "Optional. The course ID. If not provided, AI will recommend one based on the topic.",
            },
            "topic": {
                "type": "string",
                "description": "The topic or concept to generate content about.",
            },
            "content_type": {
                "type": "string",
                "enum": ["outline", "summary", "slide_structure",
                         "lesson_plan", "explanation"],
                "description": "Type of content to generate.",
                "default": "outline",
            },
            "language": {
                "type": "string",
                "enum": ["vi", "en"],
                "default": "vi",
            },
        },
        "required": ["topic"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.core.llm import chat_complete_json
        from app.services.rag_service import rag_service

        user_id = kwargs.get("_user_id")
        course_id = kwargs.get("_course_id") or kwargs.get("course_id")
        topic = kwargs["topic"]
        content_type = kwargs.get("content_type", "outline")
        language = kwargs.get("language", "vi")

        try:
            # 1. Fetch all courses and sections for the user
            lms_base = settings.lms_service_url.rstrip("/")
            courses_info = []
            if user_id:
                async with httpx.AsyncClient(timeout=15) as client:
                    headers = {"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)}
                    resp = await client.get(f"{lms_base}/api/v1/courses/my", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        courses = data.get("data", []) if isinstance(data, dict) and "data" in data else data
                        if isinstance(courses, list):
                            for c in courses:
                                c_id = c.get("id")
                                sec_resp = await client.get(f"{lms_base}/api/v1/courses/{c_id}/sections", headers=headers)
                                sec_json = sec_resp.json() if sec_resp.status_code == 200 else None
                                sections = sec_json.get("data", []) if isinstance(sec_json, dict) else []
                                if not isinstance(sections, list):
                                    sections = []
                                courses_info.append({
                                    "id": c_id,
                                    "title": c.get("title"),
                                    "sections": [{"id": s.get("id"), "title": s.get("title")} for s in sections]
                                })

            # Validate provided course_id or reset to None if hallucinated
            valid_course_ids = [c["id"] for c in courses_info]
            if course_id and course_id not in valid_course_ids:
                course_id = None

            # 2. RAG retrieve relevant materials
            chunks = await rag_service.search_multilingual(
                query=topic, course_id=course_id, top_k=5,
            )
            context = "\n---\n".join(c.chunk_text for c in chunks) if chunks else ""

            # 3. Build prompt
            type_instructions = {
                "outline": "Create a detailed lesson outline with main topics, subtopics, and key points.",
                "summary": "Write a comprehensive summary of the topic.",
                "slide_structure": "Create a slide deck structure with slide titles, bullet points, and speaker notes.",
                "lesson_plan": "Create a lesson plan with objectives, activities, timing, and assessment methods.",
                "explanation": "Write a clear, detailed explanation suitable for students.",
            }
            instruction = type_instructions.get(content_type, type_instructions["outline"])

            lang_note = "Viết bằng tiếng Việt." if language == "vi" else "Write in English."

            courses_str = ""
            for c in courses_info:
                courses_str += f"- Course ID {c['id']}: {c['title']}\n"
                for s in c["sections"]:
                    courses_str += f"  + Section ID {s['id']}: {s['title']}\n"

            system_prompt = (
                f"You are an expert educational content creator. {lang_note}\n"
                f"Task: {instruction}\n"
                f"Topic: {topic}\n\n"
                f"Base your content on the following course materials if available.\n"
                f"COURSE MATERIALS:\n{context if context else '(No materials found)'}\n\n"
                f"The teacher has the following courses and sections:\n"
                f"{courses_str if courses_str else '(No courses found)'}\n\n"
                f"Return your response as a JSON object with keys: "
                f"'draft' (markdown string), 'suggested_course_id' (integer or null), and 'suggested_section_id' (integer or null). "
                f"Choose the most appropriate course and section for this topic from the teacher's list."
            )

            result = await chat_complete_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate a {content_type} about: {topic}"},
                ],
                temperature=0.5,
                max_tokens=2048,
            )

            draft_text = result.get("draft", "")
            suggested_cid = result.get("suggested_course_id")
            suggested_sid = result.get("suggested_section_id")
            
            final_course_id = course_id or suggested_cid

            return ToolResult(
                status="success",
                data={
                    "content_type": content_type,
                    "topic": topic,
                    "draft": draft_text,
                    "course_id": final_course_id,
                    "suggested_section_id": suggested_sid,
                },
                message=f"Đã tạo {content_type} cho chủ đề '{topic}'.",
                ui_instruction={
                    "component": "ContentDraftPreview",
                    "props": {
                        "content_type": content_type,
                        "topic": topic,
                        "draft": draft_text,
                        "course_id": final_course_id,
                        "suggested_section_id": suggested_sid,
                    },
                },
            )

        except Exception as e:
            logger.error("generate_content_draft failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi khi tạo nội dung: {e}",
            )
