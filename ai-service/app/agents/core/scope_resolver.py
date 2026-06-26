"""
ai-service/app/agents/core/scope_resolver.py

Course Scope Resolver — answers "which course is the user talking about?"

The agent is GLOBAL: a teacher manages many courses, a student is enrolled
in many. Most user messages do NOT name a course explicitly, so we must
infer scope from a combination of:

    1. The list of active courses for this user (single source of truth).
    2. The MTM session anchor (current_course_id from a prior turn).
    3. The course_id explicitly attached to this turn (e.g. the frontend
       opened a course-scoped chat panel).
    4. Substring matches between the user's message and course titles.
    5. Deictic / global keywords ("cái này", "this course", "tất cả khoá").
    6. (Last resort) a fast LLM extraction call.

Output is a `CourseScope` object the ReAct loop uses to:
    - bias retrieval (context_builder) toward one or many courses
    - inject the focused course_id into tool calls
    - trigger a SCOPE clarification when the answer is genuinely ambiguous

Cheap path first (zero LLM), LLM only as a fallback. Resolver MUST be
deterministic and never raise — fall back to "ambiguous" on any error.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from app.agents.memory.active_courses import (
    find_course_by_title,
    list_course_titles,
)
from app.core.config import get_settings
from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_AGENT_ROUTER

logger = logging.getLogger(__name__)
settings = get_settings()


ScopeMode = Literal["single", "multi", "all", "none", "ambiguous"]


@dataclass(slots=True)
class CourseScope:
    """Resolved view of which course(s) the current turn applies to."""

    mode: ScopeMode
    focus_course_id: Optional[int] = None
    candidate_course_ids: list[int] = field(default_factory=list)
    confidence: float = 1.0
    reason: str = ""
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    clarification_options: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "focus_course_id": self.focus_course_id,
            "candidate_course_ids": self.candidate_course_ids,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "needs_clarification": self.needs_clarification,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Lightweight cue lexicons (kept small + obvious; the LLM handles edge cases)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Words that imply the user is referring to a previously-anchored course.
_DEICTIC_PATTERNS = (
    r"\bcái này\b", r"\bvấn đề này\b", r"\bchủ đề này\b",
    r"\bbài này\b", r"\bchương này\b", r"\bkhoá này\b", r"\bkhóa này\b",
    r"\bmôn này\b", r"\bthis (course|topic|lesson|chapter|quiz|one)\b",
    r"\bthat (course|topic|lesson|chapter|quiz|one)\b",
    r"\bở đây\b",
)
_DEICTIC_RE = re.compile("|".join(_DEICTIC_PATTERNS), re.IGNORECASE)

# Words that signal the user wants action ACROSS all their courses.
_GLOBAL_PATTERNS = (
    r"\btất cả (các )?khoá học\b", r"\btất cả (các )?khóa học\b",
    r"\bmọi (khoá|khóa) học\b",
    r"\bcross[- ]course\b", r"\ball (my )?courses\b", r"\bevery course\b",
    r"\boverall\b", r"\btoàn bộ\b",
)
_GLOBAL_RE = re.compile("|".join(_GLOBAL_PATTERNS), re.IGNORECASE)

# Words that signal the user is asking about a general topic or denying selecting a course.
_OUTSIDE_PATTERNS = (
    r"\bchưa có môn\b", r"\bkhông có môn\b", r"\bkhông thuộc môn\b",
    r"\bhỏi chung\b", r"\bngoài lề\b", r"\bngoài giáo trình\b",
    r"\bkhông nằm trong\b", r"\bno course\b", r"\bgeneral topic\b",
    r"\bnot in course\b", r"\bchưa học môn này\b", r"\bchưa có môn học này\b",
    r"\bkhông có môn học nào\b", r"\bchưa có môn này\b"
)
_OUTSIDE_RE = re.compile("|".join(_OUTSIDE_PATTERNS), re.IGNORECASE)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Public API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def resolve_course_scope(
    user_message: str,
    active_courses: dict,
    mtm_ctx: Optional[dict] = None,
    explicit_course_id: Optional[int] = None,
    router_matched_course_id: Optional[int] = None,
) -> CourseScope:
    """
    Decide which course(s) the current message applies to.

    Order of decisions (most cheap -> least cheap):
        0. No active courses -> mode="none".
        1. Only one active course -> mode="single" auto-resolve.
        2. Explicit "across all courses" cue -> mode="all".
        3. Explicit course_id from the FE that matches an active course -> "single".
        4. Deictic reference + MTM anchor present -> "single" (reuse anchor).
        5. Exactly one course title substring-matches the message -> "single".
        6. Router-extracted course_id from LLM classification -> "single".
        7. Otherwise -> "ambiguous" with a grounded clarification question.

    The resolver NEVER raises — failures degrade to "ambiguous".
    """
    courses = (active_courses or {}).get("courses") or []
    msg = (user_message or "").strip()

    # Step 0 — user has no active courses.
    if not courses:
        return CourseScope(
            mode="none",
            confidence=1.0,
            reason="user has no active courses",
        )

    # Step 1 — only one course -> easy.
    if len(courses) == 1:
        c = courses[0]
        return CourseScope(
            mode="single",
            focus_course_id=c.get("id"),
            confidence=1.0,
            reason="user has exactly one active course",
        )

    msg_lower = msg.lower()

    # Step 1.5 — user explicitly says the topic is general or not in their courses.
    if _OUTSIDE_RE.search(msg_lower):
        return CourseScope(
            mode="none",
            confidence=1.0,
            reason="user explicitly indicated the topic is general or outside existing courses",
        )

    # Step 2 — global keyword wins.
    if _GLOBAL_RE.search(msg_lower):
        ids = [c.get("id") for c in courses if c.get("id") is not None]
        return CourseScope(
            mode="all",
            candidate_course_ids=ids,
            confidence=0.9,
            reason="message references all/multiple courses explicitly",
        )

    # Step 3 — FE-provided course_id is the strongest anchor IF it matches.
    if explicit_course_id is not None:
        if any(c.get("id") == explicit_course_id for c in courses):
            return CourseScope(
                mode="single",
                focus_course_id=explicit_course_id,
                confidence=0.95,
                reason="explicit course_id from frontend",
            )

    # Step 4 — deictic reference + MTM anchor -> reuse last-focused course.
    anchor_id = _read_anchor_course_id(mtm_ctx)
    if _DEICTIC_RE.search(msg) and anchor_id is not None:
        if any(c.get("id") == anchor_id for c in courses):
            return CourseScope(
                mode="single",
                focus_course_id=anchor_id,
                confidence=0.85,
                reason="deictic reference resolved against MTM anchor",
            )

    # Step 5 — exact substring match against course titles.
    matched = find_course_by_title(active_courses, msg, min_len=3)
    if matched is not None:
        return CourseScope(
            mode="single",
            focus_course_id=matched.get("id"),
            confidence=0.85,
            reason=f"course title substring match: {matched.get('title')!r}",
        )

    # Step 6 — router-extracted course_id
    if router_matched_course_id is not None:
        if any(c.get("id") == router_matched_course_id for c in courses):
            return CourseScope(
                mode="single",
                focus_course_id=router_matched_course_id,
                confidence=0.85,
                reason="resolved via router LLM extraction",
            )

    # Step 7 — genuinely ambiguous -> ask the user, with grounded options.
    titles = list_course_titles(active_courses)
    options = [
        {"label": titles[i], "value": str(c.get("id"))}
        for i, c in enumerate(courses)
        if c.get("id") is not None
    ]
    return CourseScope(
        mode="ambiguous",
        candidate_course_ids=[c.get("id") for c in courses if c.get("id")],
        confidence=0.4,
        reason="multi-course user, message did not name a specific course",
        needs_clarification=True,
        clarification_question=_default_scope_question(active_courses),
        clarification_options=options,
    )


def apply_scope_to_course_id(
    scope: CourseScope,
    fallback_course_id: Optional[int] = None,
) -> Optional[int]:
    """
    Translate a `CourseScope` into the concrete `course_id` we pass into
    tools and into the system_memory retrieval slot.

    "single" -> the focused course.
    "all" / "multi" / "none" / "ambiguous" -> None (cross-course / unscoped).
    Falls back to the caller's hint only if the scope didn't pin anything.
    """
    if scope.mode == "single" and scope.focus_course_id is not None:
        return scope.focus_course_id
    return fallback_course_id


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internals
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _read_anchor_course_id(mtm_ctx: Optional[dict]) -> Optional[int]:
    if not mtm_ctx:
        return None
    facts = mtm_ctx.get("key_facts") if isinstance(mtm_ctx, dict) else None
    if not isinstance(facts, dict):
        return None
    val = facts.get("current_course_id")
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _default_scope_question(active_courses: dict) -> str:
    n = len(active_courses.get("courses") or [])
    if (active_courses.get("agent_type") or "") == "teacher":
        return (
            f"Bạn muốn tôi làm việc với khoá học nào trong {n} khoá bạn "
            "đang dạy?"
        )
    return (
        f"Bạn muốn tôi tập trung vào khoá học nào trong {n} khoá bạn đang "
        "học?"
    )
