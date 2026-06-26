"""
ai-service/app/agents/core/scope_resolver.py

Course Scope Resolver - answers "which course is the user talking about?" and resolves "context-lock" issues.

The agent is a teacher manages many courses, and a student is enrolled
in many. Most user messages do NOT name a course explicitly, so we must
infer scope from a combination of:

    1. The list of active courses for this user (single source of truth).
    2. The MTM session anchor (current_course_id from a prior turn).
    3. The course_id explicitly attached to this turn (e.g., the frontend
       opened a course-scoped chat panel).
    4. Substring matches between the user's message and course titles.
    5. Intent signals from the IntentWeightModel (multilingual-safe, replacing 
       legacy regex for global, deictic, or outside keywords).
    6. (Last resort) a fast LLM extraction call.

Key Features & Updates:
    - IntentWeightModel Integration: Evaluates pivot signals during `resolve_course_scope`. 
      If `pivot_strength >= 0.6`, it overrides the scope to "all" or "none" instead of 
      locking into the MTM anchor.
    - Context Scope Resolution: Introduces `resolve_context_scope()` to determine if 
      `page_context` should be utilized. It returns a `ContextScopeDecision` for the 
      react_loop to inject appropriately into `build_system_prompt`.
    - Backward Compatibility: Maintains the original `CourseScope` dataclass and 
      `apply_scope_to_course_id()` without introducing breaking changes to `react_loop.py`.

Output is a `CourseScope` object that the ReAct loop uses to:
    - Bias retrieval (context_builder) toward one or many courses.
    - Inject the focused course_id into tool calls.
    - Trigger a SCOPE clarification when the answer is genuinely ambiguous.

Design Principles: 
Cheap path first (zero LLM), utilizing LLM only as a fallback or for intent weighting. 
The resolver MUST be deterministic and never raise exceptions - falling back to 
"ambiguous" on any error.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from app.agents.memory.active_courses import (
    find_course_by_title,
    list_course_titles,
)
from app.core.config import get_settings
from app.agents.core.intent_weight_model import analyze_intent_weight, IntentWeightOutput

logger = logging.getLogger(__name__)
settings = get_settings()


ScopeMode = Literal["single", "multi", "all", "none", "ambiguous"]

# Pivot threshold - if pivot_strength >= this value, override context-lock
_PIVOT_THRESHOLD = 0.6


# ─────────────────────────────────────────────────────────────────────────────
# CourseScope
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# ContextScopeDecision
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ContextScopeDecision:
    """
    The scope resolver's decision on whether to inject page_context
    into the system prompt, and which version to inject.

    react_loop uses this object instead of passing raw page_context to
    build_system_prompt to avoid context-lock.
    """

    # Whether to inject page_context into the system prompt
    use_page_context: bool

    # Whether to inject system_context (micro-lesson)
    use_system_context: bool

    # Sanitized page_context (None if not used)
    effective_page_context: Optional[dict]

    # Sanitized system_context (None if not used)
    effective_system_context: Optional[dict]

    # Reason for the decision (for logging/debugging)
    reason: str

    # Pivot info from IntentWeightModel
    intent_weight: Optional[IntentWeightOutput] = None

    # Suggested topic to search for (when pivoting to a new topic)
    suggested_search_topic: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# resolve_context_scope()
# ─────────────────────────────────────────────────────────────────────────────

async def resolve_context_scope(
    user_message: str,
    page_context: Optional[dict],
    system_context: Optional[dict],
    mtm_ctx: Optional[dict],
) -> ContextScopeDecision:
    """
    Determine whether page_context / system_context should be injected into
    the system prompt, based on the IntentWeightModel.

    Logic:
        1. If there is no page_context and no system_context -> there is nothing to decide.
            Return use_page_context=False, use_system_context=False.

        2. If there is a page_context or system_context -> call IntentWeightModel to determine
            if the user is pivoting or staying.

        3. If pivot_strength >= _PIVOT_THRESHOLD:
            - Remove page_context from the system prompt (use effective_page_context=None)
            - If the user pivots to a specific topic, record the suggested_search_topic
              so the ReAct loop can search for that exact topic instead of the currently open lesson's topic

        4. If pivot_strength < _PIVOT_THRESHOLD:
            - Inject page_context normally (the user wants to study the currently open lesson)

    Args:
        user_message: Raw user message.
        page_context: Dict from the frontend (currently viewed lesson). None if unavailable.
        system_context: Dict from the Quick Action Panel. None if unavailable.
        mtm_ctx: Raw MTM context dict from mtm.get_context().

    Returns:
        ContextScopeDecision
    """
    # No context available -> no analysis needed
    has_page_ctx = bool(
        page_context and (
            page_context.get("contentBody")
            or page_context.get("content_body")
            or page_context.get("body")
            or page_context.get("contentTitle")
            or page_context.get("title")
        )
    )
    has_sys_ctx = bool(
        system_context and (
            system_context.get("lesson_text")
            or system_context.get("lesson_title")
        )
    )

    if not has_page_ctx and not has_sys_ctx:
        return ContextScopeDecision(
            use_page_context=False,
            use_system_context=False,
            effective_page_context=None,
            effective_system_context=None,
            reason="no_active_lesson_context",
        )

    # Extract lesson title / topic for IntentWeightModel
    lesson_title: Optional[str] = None
    lesson_topic: Optional[str] = None

    if page_context:
        lesson_title = (
            page_context.get("contentTitle")
            or page_context.get("title")
            or page_context.get("name")
        )

    if system_context:
        lesson_title = lesson_title or system_context.get("lesson_title")
        # Try to infer topic from lesson title (just pass the title as topic too)
        lesson_topic = system_context.get("topic") or lesson_title

    # Extract MTM anchor topic
    mtm_anchor_topic: Optional[str] = None
    if mtm_ctx and isinstance(mtm_ctx, dict):
        facts = mtm_ctx.get("key_facts") or {}
        if isinstance(facts, dict):
            mtm_anchor_topic = facts.get("current_topic") or facts.get("current_lesson_title")

    # Call IntentWeightModel - LLM analyzes semantics, no regex used
    weight = await analyze_intent_weight(
        user_message=user_message,
        active_lesson_title=lesson_title,
        active_lesson_topic=lesson_topic,
        mtm_anchor_topic=mtm_anchor_topic,
    )

    logger.info(
        "ContextScope: pivot_strength=%.2f intent=%s | lesson='%s' | msg='%s'",
        weight.pivot_strength,
        weight.explicit_intent,
        lesson_title or "?",
        user_message[:60],
    )

    # Make a decision based on pivot_strength
    if weight.pivot_strength >= _PIVOT_THRESHOLD:
        # The user is pivoting away from the currently viewed lesson
        reason = (
            f"pivot_detected: strength={weight.pivot_strength:.2f} "
            f"intent={weight.explicit_intent} - suppressing page_context to avoid context-lock"
        )
        logger.info("ContextScope: %s", reason)

        return ContextScopeDecision(
            use_page_context=False,
            use_system_context=False,
            effective_page_context=None,
            effective_system_context=None,
            reason=reason,
            intent_weight=weight,
            suggested_search_topic=weight.new_topic_hint,
        )

    # The user wants to stay in the currently viewed lesson
    reason = (
        f"no_pivot: strength={weight.pivot_strength:.2f} "
        f"intent={weight.explicit_intent} - using page_context"
    )
    return ContextScopeDecision(
        use_page_context=has_page_ctx,
        use_system_context=has_sys_ctx,
        effective_page_context=page_context if has_page_ctx else None,
        effective_system_context=system_context if has_sys_ctx else None,
        reason=reason,
        intent_weight=weight,
        suggested_search_topic=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Existing resolve_course_scope() - enhanced with IntentWeightModel fallback
# ─────────────────────────────────────────────────────────────────────────────

async def resolve_course_scope(
    user_message: str,
    active_courses: dict,
    mtm_ctx: Optional[dict] = None,
    explicit_course_id: Optional[int] = None,
    router_matched_course_id: Optional[int] = None,
    intent_weight: Optional[IntentWeightOutput] = None,
) -> CourseScope:
    """
    Decide which course(s) the current message applies to.

    Decision hierarchy (cheap -> expensive):
        0. No active courses -> mode="none".
        1. Only one active course -> mode="single" auto-resolve.
        2. pivot_strength >= threshold -> mode="all" (cross-course support).
        3. Explicit "across all courses" -> mode="all".
        4. Explicit course_id from FE -> "single".
        5. Deictic reference + MTM anchor (via intent_weight, without using regex).
        6. Exactly one course title match -> "single".
        7. Router-extracted course_id -> "single".
        8. Otherwise -> "ambiguous".

    Does not use _DEICTIC_RE / _GLOBAL_RE / _OUTSIDE_RE regex.
    Replaced by intent_weight.explicit_intent and pivot_strength.
    """
    courses = (active_courses or {}).get("courses") or []
    msg = (user_message or "").strip()

    # Step 0
    if not courses:
        return CourseScope(
            mode="none",
            confidence=1.0,
            reason="user has no active courses",
        )

    # Step 1
    if len(courses) == 1:
        c = courses[0]
        return CourseScope(
            mode="single",
            focus_course_id=c.get("id"),
            confidence=1.0,
            reason="user has exactly one active course",
        )

    # Step 2 - pivot detected -> cross-course support
    if intent_weight and intent_weight.pivot_strength >= _PIVOT_THRESHOLD:
        if intent_weight.explicit_intent == "pivot_new_topic" and intent_weight.new_topic_hint:
            # Try to match new topic hint against course titles
            matched = find_course_by_title(
                active_courses, intent_weight.new_topic_hint, min_len=3
            )
            if matched is not None:
                return CourseScope(
                    mode="single",
                    focus_course_id=matched.get("id"),
                    confidence=0.8,
                    reason=f"pivot to new topic matched course: {matched.get('title')!r}",
                )

        # General pivot -> all courses (let the LLM decide in context)
        ids = [c.get("id") for c in courses if c.get("id") is not None]
        return CourseScope(
            mode="all",
            candidate_course_ids=ids,
            confidence=0.85,
            reason=f"user pivoted away from active lesson (pivot_strength={intent_weight.pivot_strength:.2f})",
        )

    # Step 3 - explicit course_id from FE
    if explicit_course_id is not None:
        if any(c.get("id") == explicit_course_id for c in courses):
            return CourseScope(
                mode="single",
                focus_course_id=explicit_course_id,
                confidence=0.95,
                reason="explicit course_id from frontend",
            )

    # Step 4 - deictic via intent_weight (no regex)
    # IntentWeightModel has determined explicit_intent="review_current_lesson" or "ask_concept"
    # -> the user is referring to the current lesson -> reuse MTM anchor
    anchor_id = _read_anchor_course_id(mtm_ctx)
    if (
        intent_weight
        and intent_weight.explicit_intent in ("review_current_lesson", "ask_concept")
        and intent_weight.pivot_strength < 0.3
        and anchor_id is not None
        and any(c.get("id") == anchor_id for c in courses)
    ):
        return CourseScope(
            mode="single",
            focus_course_id=anchor_id,
            confidence=0.85,
            reason="deictic reference resolved via IntentWeightModel + MTM anchor",
        )

    # Step 5 - title substring match
    matched = find_course_by_title(active_courses, msg, min_len=3)
    if matched is not None:
        return CourseScope(
            mode="single",
            focus_course_id=matched.get("id"),
            confidence=0.85,
            reason=f"course title substring match: {matched.get('title')!r}",
        )

    # Step 6 - router-extracted
    if router_matched_course_id is not None:
        if any(c.get("id") == router_matched_course_id for c in courses):
            return CourseScope(
                mode="single",
                focus_course_id=router_matched_course_id,
                confidence=0.85,
                reason="resolved via router LLM extraction",
            )

    # Step 7 - ambiguous
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
    """Unchanged from original."""
    if scope.mode == "single" and scope.focus_course_id is not None:
        return scope.focus_course_id
    return fallback_course_id


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────

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