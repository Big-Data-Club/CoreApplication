"""
ai-service/app/agents/core/router.py

Intent Router - Backward-Compatible Wrapper.

As of Planner v2, the router and planner share a single LLM call via
generate_plan() in planner.py.  This module is kept for backward
compatibility with any code that calls classify_intent() directly.

When MERGED_PLANNER_ENABLED=true (default):
  classify_intent() calls generate_plan() and wraps the result as RouterOutput.

When MERGED_PLANNER_ENABLED=false:
  classify_intent() makes its own separate LLM call (legacy behavior).
"""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import chat_complete_structured
from app.core.llm_gateway import TASK_AGENT_ROUTER

logger = logging.getLogger(__name__)
settings = get_settings()

VALID_INTENTS = {
    "knowledge_question",
    "progress_advice",
    "content_creation",
    "interactive_exercise",
    "general_chat",
}


class RouterOutput(BaseModel):
    intent: str = Field(
        description="Exactly one of: knowledge_question, progress_advice, content_creation, interactive_exercise, general_chat"
    )
    is_ambiguous: bool = Field(
        description="True if the request is vague, lacks critical parameters, or refers to multiple possible courses and needs clarification."
    )
    ambiguity_reason: str | None = Field(
        None,
        description="Short code/reason for ambiguity if is_ambiguous is True, e.g., 'unspecified_course', 'vague_request', 'missing_parameters'"
    )
    missing_context: str | None = Field(
        None,
        description="Clarifying question or description of what is missing to resolve the request."
    )
    matched_course_id: int | None = Field(
        None,
        description="The course ID if the user explicitly names or implies a specific course from the active courses list, otherwise null."
    )
    requires_tool: bool = Field(
        default=False,
        description="True if the user is explicitly requesting a system action or database modification that requires a tool."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Legacy standalone router prompt (used only when MERGED_PLANNER_ENABLED=false)
# ─────────────────────────────────────────────────────────────────────────────

ROUTER_PROMPT = """\
You are the Intent Router and Scope Resolver for the BDC Learning Management System.
Your job is to analyze the user's message, classify their intent, and determine if the request is ambiguous or maps to a specific course.

Active courses for this user:
{course_list}

{current_context}

Intent types:
- knowledge_question: Asking about a concept (what, how, why, explain)
- progress_advice: Asking about scores, progress, study advice, grades
- content_creation: Asking to create/generate quizzes, content, slides, assessments
- interactive_exercise: Asking for practice, exercises, flashcards, mini-tests, review challenges
- general_chat: Greetings, thank you, chitchat, or generic conversational input

Ambiguity Rules:
1. Set is_ambiguous = true if the request is not general_chat, but is too vague to act on, OR if it requires a course context but the user has multiple courses and hasn't specified which one (and you cannot clearly match the course, and no current course context is provided).
2. If the user is currently viewing/interacting inside a specific course context (as shown in the Current context block), treat that course as specified and do NOT flag course-selection ambiguity. Set matched_course_id to that current course ID.
3. If the user explicitly mentions a course title or keywords that map uniquely to one of the active courses, set matched_course_id to that course's ID.
4. If the request is a general greeting, thank you, or chitchat, set intent to general_chat and is_ambiguous = false.

Tool Rules:
1. Set requires_tool = true if the user's message explicitly requests a system action or database modification that requires a tool (e.g. generating a quiz draft, saving/creating new flashcards in the database, starting an interactive challenge, triggering document index).
2. Set requires_tool = false if they are only asking for explanations, definitions, summaries, advice, or general conversation.
"""


async def classify_intent(
    user_message: str,
    active_courses: dict | None = None,
    agent_type: str = "mentor",
    current_course_id: int | None = None,
    page_context: dict | None = None,
) -> RouterOutput:
    """
    Classify the user's message into an intent type with structured details.

    When MERGED_PLANNER_ENABLED=true: delegates to generate_plan() to reuse
    the single planning LLM call instead of making a separate router call.

    When MERGED_PLANNER_ENABLED=false: makes a standalone LLM call (legacy).

    Returns a RouterOutput object. Falls back to a default RouterOutput on error.
    """
    # Short-circuit for trivial inputs (saves LLM call regardless of mode)
    try:
        stripped = user_message.strip().lower()
        if len(stripped) < 5 or stripped in (
            "hi", "hello", "hey", "xin chào", "chào",
            "thanks", "cảm ơn", "ok", "bye",
        ):
            return RouterOutput(
                intent="general_chat",
                is_ambiguous=False,
                ambiguity_reason=None,
                missing_context=None,
                matched_course_id=None,
                requires_tool=False,
            )
    except Exception:
        pass

    # ── Merged Planner path (default) ──────────────────────────────────────
    if settings.merged_planner_enabled:
        try:
            from app.agents.core.planner import generate_plan
            plan = await generate_plan(
                user_message=user_message,
                active_courses=active_courses,
                agent_type=agent_type,
                current_course_id=current_course_id,
                page_context=page_context,
            )
            intent = plan.intent if plan.intent in VALID_INTENTS else "general_chat"
            return RouterOutput(
                intent=intent,
                is_ambiguous=plan.is_ambiguous,
                ambiguity_reason=plan.ambiguity_reason,
                missing_context=plan.missing_context,
                matched_course_id=plan.matched_course_id,
                requires_tool=plan.requires_tool,
            )
        except Exception as exc:
            logger.warning(
                "classify_intent (merged planner path) failed, falling back: %s", exc
            )

    # ── Legacy standalone router path ─────────────────────────────────────
    try:
        courses = (active_courses or {}).get("courses") or []
        course_lines = []
        for c in courses:
            cid = c.get("id")
            title = c.get("title", "")
            course_lines.append(f"  - id={cid}: \"{title}\"")
        course_list = "\n".join(course_lines) if course_lines else "  (No active courses)"

        current_context_lines = []
        if current_course_id:
            course_title = ""
            for c in courses:
                if c.get("id") == current_course_id:
                    course_title = c.get("title", "")
                    break
            current_context_lines.append(f"  - Course Context: id={current_course_id} (\"{course_title}\")")
        if page_context:
            page_type = page_context.get("pageType") or page_context.get("type") or page_context.get("page_type")
            if page_type:
                current_context_lines.append(f"  - Page Type: {page_type}")
            content_title = page_context.get("contentTitle") or page_context.get("title") or page_context.get("name")
            if content_title:
                current_context_lines.append(f"  - Page Title/Topic: \"{content_title}\"")

        current_context = ""
        if current_context_lines:
            current_context = "Current context where the user is viewing/asking this:\n" + "\n".join(current_context_lines)

        prompt = ROUTER_PROMPT.format(course_list=course_list, current_context=current_context)

        output = await chat_complete_structured(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message[:500]},
            ],
            response_model=RouterOutput,
            model=settings.chat_model,
            temperature=0.0,
            max_tokens=256,
            task=TASK_AGENT_ROUTER,
        )

        if output.intent not in VALID_INTENTS:
            output.intent = "general_chat"

        logger.debug(
            "Intent classified (legacy): intent=%s, is_ambiguous=%s, matched_course_id=%s, requires_tool=%s",
            output.intent, output.is_ambiguous, output.matched_course_id, output.requires_tool
        )
        return output

    except Exception as exc:
        logger.error("Intent classification failed: %s", exc)
        return RouterOutput(
            intent="general_chat",
            is_ambiguous=False,
            ambiguity_reason="error",
            missing_context=None,
            matched_course_id=None,
            requires_tool=False,
        )
