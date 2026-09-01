"""Create a private LMS course draft from a caller-authored curriculum."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_PLAN_BYTES = 800 * 1024
MAX_CHAPTERS = 50
MAX_LESSONS = 300
MAX_LESSON_MARKDOWN_BYTES = 180 * 1024
_LESSON_CONCURRENCY = 8


class McpCreateCourseFromFilesTool(BaseTool):
    """Create a real private course; the historic tool name is retained for clients."""

    name = "mcp_create_course_from_files"
    description = (
        "Create a real private LMS course in DRAFT status from an externally authored curriculum. "
        "It creates sections and draft TEXT lessons immediately; it never publishes. "
        "For large curricula, submit up to 50 chapters / 300 lessons (up to 800 KB total JSON). "
        "Local source files stay local: only the supplied derived lesson text is stored in BDC."
    )
    parameters = {
        "type": "object",
        "properties": {
            "plan": {
                "type": "object",
                "description": "Course metadata and chapters. Each chapter may contain lessons; each lesson accepts title, description and optional markdown.",
                "properties": {
                    "title": {"type": "string", "minLength": 3, "maxLength": 255},
                    "description": {"type": "string", "maxLength": 5000},
                    "category": {"type": "string", "maxLength": 100},
                    "level": {"type": "string", "enum": ["BEGINNER", "INTERMEDIATE", "ADVANCED", "ALL_LEVELS"]},
                    "organization_id": {"type": "integer", "minimum": 1, "description": "Optional; LMS selects the teacher's default organization when omitted."},
                    "chapters": {
                        "type": "array", "minItems": 1, "maxItems": MAX_CHAPTERS,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "minLength": 3, "maxLength": 255},
                                "description": {"type": "string", "maxLength": 2000},
                                "lessons": {
                                    "type": "array", "maxItems": MAX_LESSONS,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string", "minLength": 3, "maxLength": 255},
                                            "description": {"type": "string", "maxLength": 2000},
                                            "markdown": {"type": "string", "description": "Optional Markdown body for this draft TEXT lesson."},
                                        },
                                        "required": ["title"],
                                    },
                                },
                            },
                            "required": ["title"],
                        },
                    },
                },
                "required": ["title", "chapters"],
            },
            "source_names": {
                "type": "array", "maxItems": 50,
                "items": {"type": "string", "maxLength": 255},
                "description": "Optional display-only provenance. Never send local paths, URLs, file bytes or credentials.",
            },
        },
        "required": ["plan"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = int(kwargs.get("_user_id") or 0)
        plan = kwargs.get("plan")
        if not user_id or not isinstance(plan, dict):
            return _error("invalid_course_plan", "A valid course plan is required.")
        try:
            course, chapters = _normalise_plan(plan)
        except ValueError as exc:
            return _error("invalid_course_plan", str(exc))
        if len(json.dumps({"course": course, "chapters": chapters}, ensure_ascii=False).encode("utf-8")) > MAX_PLAN_BYTES:
            return _error("course_plan_too_large", "Course plan exceeds 800 KB. Create the draft first, then add detailed lessons in smaller batches.")

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                response = await client.post(f"{settings.lms_service_url.rstrip('/')}/api/v1/courses", json=course, headers=_lms_headers(user_id))
                if response.status_code not in (200, 201):
                    return _error("course_create_failed", _response_error(response))
                created_course = _body_data(response)
                course_id = int(created_course.get("id") or 0)
                if not course_id:
                    return _error("course_create_failed", "LMS did not return a course ID.")

                created_sections: list[dict[str, Any]] = []
                for index, chapter in enumerate(chapters):
                    section_response = await client.post(
                        f"{settings.lms_service_url.rstrip('/')}/api/v1/courses/{course_id}/sections",
                        json={"title": chapter["title"], "description": chapter["description"], "order_index": index}, headers=_lms_headers(user_id),
                    )
                    if section_response.status_code not in (200, 201):
                        return ToolResult(status="partial", data={"course": created_course, "state": "DRAFT", "created_sections": created_sections, "failed_chapter": chapter["title"], "error": _response_error(section_response)}, message="Course draft was created, but a later section failed. It remains private and can be completed safely in LMS.")
                    section = _body_data(section_response)
                    created_sections.append(section)
                    failures = await _create_lessons(client, int(section["id"]), chapter["lessons"], user_id)
                    if failures:
                        return ToolResult(status="partial", data={"course": created_course, "state": "DRAFT", "created_sections": created_sections, "failed_lessons": failures}, message="Course draft was created, but some lessons could not be saved. No content was published; retry only the listed lessons.")
        except httpx.HTTPError as exc:
            logger.warning("MCP course draft request failed: %s", exc)
            return _error("lms_unavailable", "LMS could not be reached. No publication was attempted.")
        except Exception:
            logger.exception("MCP course draft creation failed")
            return _error("course_create_failed", "LMS could not create the draft course.")

        lesson_count = sum(len(chapter["lessons"]) for chapter in chapters)
        return ToolResult(status="success", data={"course": created_course, "course_id": course_id, "state": "DRAFT", "section_count": len(chapters), "lesson_count": lesson_count}, message=f"Created private DRAFT course '{course['title']}' with {len(chapters)} sections and {lesson_count} draft lessons.")


def _normalise_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    title = _text(plan.get("title"), 255)
    if len(title) < 3:
        raise ValueError("Course title must contain 3–255 characters.")
    raw_chapters = plan.get("chapters")
    if not isinstance(raw_chapters, list) or not 1 <= len(raw_chapters) <= MAX_CHAPTERS:
        raise ValueError(f"Provide 1–{MAX_CHAPTERS} chapters.")
    level = str(plan.get("level") or "ALL_LEVELS").upper()
    if level not in {"BEGINNER", "INTERMEDIATE", "ADVANCED", "ALL_LEVELS"}:
        raise ValueError("level must be BEGINNER, INTERMEDIATE, ADVANCED or ALL_LEVELS.")
    course: dict[str, Any] = {"title": title, "description": _text(plan.get("description"), 5000), "category": _text(plan.get("category"), 100), "level": level, "visibility": "ORG_ONLY"}
    if isinstance(plan.get("organization_id"), int) and plan["organization_id"] > 0:
        course["org_id"] = plan["organization_id"]

    chapters: list[dict[str, Any]] = []
    lesson_count = 0
    for chapter_index, raw_chapter in enumerate(raw_chapters, 1):
        if not isinstance(raw_chapter, dict):
            raise ValueError(f"Chapter {chapter_index} must be an object.")
        chapter_title = _text(raw_chapter.get("title"), 255)
        if len(chapter_title) < 3:
            raise ValueError(f"Chapter {chapter_index} title must contain 3–255 characters.")
        raw_lessons = raw_chapter.get("lessons", [])
        if not isinstance(raw_lessons, list):
            raise ValueError(f"Lessons for chapter '{chapter_title}' must be an array.")
        lessons: list[dict[str, str]] = []
        for lesson_index, raw_lesson in enumerate(raw_lessons, 1):
            if isinstance(raw_lesson, str):
                raw_lesson = {"title": raw_lesson}
            if not isinstance(raw_lesson, dict):
                raise ValueError(f"Lesson {lesson_index} in '{chapter_title}' must be an object.")
            lesson_title = _text(raw_lesson.get("title"), 255)
            if len(lesson_title) < 3:
                raise ValueError(f"Lesson {lesson_index} in '{chapter_title}' needs a 3–255 character title.")
            markdown = raw_lesson.get("markdown", raw_lesson.get("content", ""))
            if not isinstance(markdown, str):
                raise ValueError(f"Lesson '{lesson_title}' Markdown must be text.")
            if len(markdown.encode("utf-8")) > MAX_LESSON_MARKDOWN_BYTES:
                raise ValueError(f"Lesson '{lesson_title}' exceeds the 180 KB Markdown limit.")
            lessons.append({"title": lesson_title, "description": _text(raw_lesson.get("description"), 2000), "markdown": markdown})
            lesson_count += 1
        chapters.append({"title": chapter_title, "description": _text(raw_chapter.get("description"), 2000), "lessons": lessons})
    if lesson_count > MAX_LESSONS:
        raise ValueError(f"A course draft supports at most {MAX_LESSONS} lessons per MCP call.")
    return course, chapters


async def _create_lessons(client: httpx.AsyncClient, section_id: int, lessons: list[dict[str, str]], user_id: int) -> list[dict[str, str]]:
    semaphore = asyncio.Semaphore(_LESSON_CONCURRENCY)

    async def create(index: int, lesson: dict[str, str]) -> dict[str, str] | None:
        async with semaphore:
            response = await client.post(
                f"{settings.lms_service_url.rstrip('/')}/api/v1/sections/{section_id}/content",
                json={"type": "TEXT", "title": lesson["title"], "description": lesson["description"], "order_index": index, "is_mandatory": False, "metadata": {"content": lesson["markdown"]}}, headers=_lms_headers(user_id),
            )
        return None if response.status_code in (200, 201) else {"title": lesson["title"], "error": _response_error(response)}

    results = await asyncio.gather(*(create(index, lesson) for index, lesson in enumerate(lessons)))
    return [item for item in results if item is not None]


def _lms_headers(user_id: int) -> dict[str, str]:
    return {"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)}


def _body_data(response: httpx.Response) -> dict[str, Any]:
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else {}


def _response_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            return str(body.get("message") or body.get("error") or body.get("detail") or f"LMS HTTP {response.status_code}")
    except Exception:
        pass
    return f"LMS HTTP {response.status_code}"


def _text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _error(code: str, message: str) -> ToolResult:
    return ToolResult(status="error", data={"error": code}, message=message)
