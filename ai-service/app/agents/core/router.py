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


ROUTER_PROMPT = """\
You are the Intent Router and Scope Resolver for the BDC Learning Management System.
Your job is to analyze the user's message, classify their intent, and determine if the request is ambiguous or maps to a specific course.

Active courses for this user:
{course_list}

Intent types:
- knowledge_question: Asking about a concept (what, how, why, explain)
- progress_advice: Asking about scores, progress, study advice, grades
- content_creation: Asking to create/generate quizzes, content, slides, assessments
- interactive_exercise: Asking for practice, exercises, flashcards, mini-tests, review challenges
- general_chat: Greetings, thank you, chitchat, or generic conversational input

Ambiguity Rules:
1. Set is_ambiguous = true if the request is not general_chat, but is too vague to act on, OR if it requires a course context but the user has multiple courses and hasn't specified which one (and you cannot clearly match the course).
2. If the user explicitly mentions a course title or keywords that map uniquely to one of the active courses, set matched_course_id to that course's ID.
3. If the request is a general greeting, thank you, or chitchat, set intent to general_chat and is_ambiguous = false.
"""


async def classify_intent(
    user_message: str,
    active_courses: dict | None = None,
    agent_type: str = "mentor",
) -> RouterOutput:
    """
    Classify the user's message into an intent type with structured details.

    Returns a RouterOutput object.
    Falls back to a default RouterOutput on error.
    """
    try:
        # Short messages and greetings → skip LLM call
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
            )

        courses = (active_courses or {}).get("courses") or []
        course_lines = []
        for c in courses:
            cid = c.get("id")
            title = c.get("title", "")
            course_lines.append(f"  - id={cid}: \"{title}\"")
        course_list = "\n".join(course_lines) if course_lines else "  (No active courses)"

        prompt = ROUTER_PROMPT.format(course_list=course_list)

        output = await chat_complete_structured(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message[:500]},
            ],
            response_model=RouterOutput,
            model=settings.chat_model,  # fast model
            temperature=0.0,
            max_tokens=256,
            task=TASK_AGENT_ROUTER,
        )

        if output.intent not in VALID_INTENTS:
            output.intent = "general_chat"

        logger.debug(
            "Intent classified: intent=%s, is_ambiguous=%s, matched_course_id=%s",
            output.intent, output.is_ambiguous, output.matched_course_id
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
        )

