"""Fast, deterministic context contract for every agent turn.

The browser tells us what it is displaying, but that input is only a hint.
This module normalises the hint, verifies course IDs against the user's active
courses, and makes the cheap course-scope decision before any LLM call.  It is
deliberately side-effect free so it can be tested and reused by new agents.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.agents.core.course_matching import find_course_by_title


ResolutionStatus = Literal[
    "current_page", "single_course", "named_course", "global",
    "needs_course_choice", "needs_course_navigation",
]


@dataclass(slots=True)
class ContextSnapshot:
    page_type: str = "other"
    route: str | None = None
    role: str | None = None
    course_id: int | None = None
    course_name: str | None = None
    section_id: int | None = None
    section_name: str | None = None
    content_id: int | None = None
    content_title: str | None = None
    quiz_id: int | None = None
    has_content_body: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ContextResolution:
    status: ResolutionStatus
    snapshot: ContextSnapshot
    course_id: int | None = None
    confidence: float = 1.0
    reason: str = ""
    clarification_question: str | None = None
    clarification_options: list[dict[str, str]] = field(default_factory=list)
    navigation: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["snapshot"] = self.snapshot.as_dict()
        return data


def _as_positive_int(value: Any) -> int | None:
    try:
        number = int(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _get(ctx: dict[str, Any], camel: str, snake: str | None = None) -> Any:
    return ctx.get(camel, ctx.get(snake or camel))


def normalize_page_context(
    page_context: dict[str, Any] | None,
    user_context: dict[str, Any] | None = None,
) -> ContextSnapshot:
    """Return a compact, bounded snapshot; never retain arbitrary page data."""
    raw = page_context or {}
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    return ContextSnapshot(
        page_type=str(_get(raw, "pageType", "page_type") or "other")[:48],
        route=str(raw.get("route") or raw.get("pathname") or "")[:300] or None,
        role=str((user_context or {}).get("role") or raw.get("role") or "")[:80] or None,
        course_id=_as_positive_int(_get(raw, "courseId", "course_id")),
        course_name=str(_get(raw, "courseName", "course_name") or "")[:200] or None,
        section_id=_as_positive_int(_get(raw, "sectionId", "section_id")),
        section_name=str(_get(raw, "sectionName", "section_name") or "")[:200] or None,
        content_id=_as_positive_int(_get(raw, "contentId", "content_id")),
        content_title=str(_get(raw, "contentTitle", "content_title") or "")[:200] or None,
        quiz_id=_as_positive_int(_get(raw, "quizId", "quiz_id") or extra.get("quizId") or extra.get("quiz_id")),
        has_content_body=bool(_get(raw, "contentBody", "content_body")),
    )


def _courses(active_courses: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [c for c in (active_courses or {}).get("courses", []) if _as_positive_int(c.get("id"))]


def _course_options(courses: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"label": str(course.get("title") or f"Khóa học {course['id']}")[:200], "value": str(course["id"])}
        for course in courses
    ]


def _course_bound_request(message: str) -> bool:
    """Conservative signal: only block when an action truly needs a course."""
    text = message.casefold()
    signals = (
        "tạo", "thêm", "sửa", "xóa", "xuất bản", "publish", "create",
        "quiz", "câu hỏi", "flashcard", "bài học", "nội dung", "lớp học",
        "khóa học", "khoá học", "course", "tiến độ lớp", "học viên",
        "tài liệu", "tai lieu", "file", "upload", "index", "phân loại", "phan loai",
    )
    return any(signal in text for signal in signals)


def _find_named_course(message: str, courses: list[dict[str, Any]]) -> dict[str, Any] | None:
    return find_course_by_title({"courses": courses}, message, min_len=3)


def _course_index_path(agent_type: str) -> str:
    return "/lms/teacher/courses" if agent_type == "teacher" else "/lms/student/courses"


def resume_request_after_course_choice(
    *,
    message: str,
    resolution: ContextResolution,
    history: list[dict[str, Any]] | None,
) -> str:
    """Join a verified course-selection answer back to its pending request.

    Scope clarification is a protocol state, not a new user task. New records
    carry explicit metadata; the structural fallback supports conversations
    created before that metadata was introduced.
    """
    if resolution.status != "named_course" or resolution.course_id is None:
        return message
    messages = history or []
    if not messages or messages[-1].get("role") != "clarification":
        return message

    clarification = messages[-1]
    metadata = clarification.get("metadata")
    pending_request = None
    if isinstance(metadata, dict) and metadata.get("kind") == "scope":
        pending_request = metadata.get("pending_user_request")
    else:
        # Backward compatibility: an early scope stop always wrote the original
        # user turn immediately before the clarification turn.
        for item in reversed(messages[:-1]):
            if item.get("role") == "user":
                candidate = str(item.get("content") or "").strip()
                if _course_bound_request(candidate):
                    pending_request = candidate
                break

    if not pending_request:
        return message
    return (
        f"{pending_request}\n\n"
        f"[Verified follow-up course selection: course_id={resolution.course_id}; "
        f"user reference={message.strip()!r}]"
    )


def resolve_turn_context(
    *,
    message: str,
    page_context: dict[str, Any] | None,
    user_context: dict[str, Any] | None,
    active_courses: dict[str, Any] | None,
    agent_type: str,
    explicit_course_id: int | None = None,
) -> ContextResolution:
    """Resolve the safest course context without calling a model.

    A course named by the user wins after verification. Browser and panel
    hints are accepted only when they exist in the user's active course list.
    For actions outside a course, stop and ask instead of guessing.
    """
    snapshot = normalize_page_context(page_context, user_context)
    courses = _courses(active_courses)
    by_id = {int(c["id"]): c for c in courses}

    # An explicit reference in the user's message is verified against the
    # catalogue and should beat incidental browser/panel context.
    named = _find_named_course(message, courses)
    if named:
        return ContextResolution(
            status="named_course", snapshot=snapshot, course_id=int(named["id"]),
            confidence=0.93, reason="unique active-course reference named by user",
        )

    trusted_explicit_id = _as_positive_int(explicit_course_id)
    if trusted_explicit_id and trusted_explicit_id in by_id:
        return ContextResolution(
            status="current_page", snapshot=snapshot, course_id=trusted_explicit_id,
            confidence=0.97, reason="verified explicit course scope",
        )

    if snapshot.course_id and snapshot.course_id in by_id:
        return ContextResolution(
            status="current_page", snapshot=snapshot, course_id=snapshot.course_id,
            confidence=0.99, reason="verified course from active page",
        )

    needs_course = _course_bound_request(message)
    if len(courses) == 1:
        return ContextResolution(
            status="single_course", snapshot=snapshot, course_id=int(courses[0]["id"]),
            confidence=0.9, reason="user has exactly one active course",
        )

    if needs_course and len(courses) > 1:
        return ContextResolution(
            status="needs_course_choice", snapshot=snapshot, confidence=0.4,
            reason="course-bound request with multiple active courses",
            clarification_question="Bạn muốn tôi làm việc với khóa học nào?",
            clarification_options=_course_options(courses),
        )

    if needs_course and not courses:
        path = _course_index_path(agent_type)
        return ContextResolution(
            status="needs_course_navigation", snapshot=snapshot, confidence=1.0,
            reason="course-bound request but user has no active courses",
            clarification_question="Bạn chưa ở trong khóa học nào. Bạn có muốn mở danh sách khóa học để chọn một khóa học không?",
            navigation={"label": "Mở danh sách khóa học", "href": path},
        )

    return ContextResolution(
        status="global", snapshot=snapshot, confidence=0.8,
        reason="request can be answered without a course scope",
    )
