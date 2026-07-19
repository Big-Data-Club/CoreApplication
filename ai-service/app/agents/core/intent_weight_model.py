"""
ai-service/app/agents/core/intent_weight_model.py

Intent Weight Model - solves the "context-lock" problem.

Problem:
  A learner is currently on the "Travel vocabulary" lesson and asks "help me review vocabulary".
  -> The system locks onto the Travel topic, failing to recognize this as a general review request.

Solution:
  Instead of relying solely on the scope_resolver to determine the course, introduce an "intent weight" layer
  to calculate and compare:
    (A) Current context weight (page_context / MTM anchor)
    (B) User's explicit intent weight (explicit intent signal)
  to decide which one should win - and when (B) > (A), override the scope to "general" or the new topic.

Regex is not used. All signals are analyzed via a single LLM call with
structured output -> ensuring it is multilingual-safe.
"""
from __future__ import annotations

import logging
from typing import Optional
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import chat_complete_structured
from app.core.llm_gateway import TASK_AGENT_ROUTER

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Output schema
# ─────────────────────────────────────────────────────────────────────────────

class IntentWeightOutput(BaseModel):
    """
    Intent weight analysis result.
    All fields are populated by the LLM, with no hardcoded language patterns.
    """

    # The user's true intent - separated from the current topic
    explicit_intent: str = Field(
        description=(
            "The user's explicit learning action. One of: "
            "'review_current_lesson' (wants to study/do exercises ON the active lesson), "
            "'pivot_general' (wants general support not tied to active lesson), "
            "'pivot_new_topic' (names a different topic/course), "
            "'ask_concept' (asks a conceptual question about something in the lesson), "
            "'elicit_preference' (student shares learning style, topic interest, or pace preferences), "
            "'request_recommendation' (student explicitly asks for study recommendations or next steps), "
            "'provide_feedback' (student critiques, accepts, or rejects a recommended topic/lesson), "
            "'ask_explanation' (student asks why a certain lesson or topic was recommended to them), "
            "'chitchat' (general conversation). "
        )
    )

    # Pivot signal strength - key decision signal
    pivot_strength: float = Field(
        ge=0.0, le=1.0,
        description=(
            "How strongly the user is pivoting AWAY from the currently active lesson context. "
            "0.0 = staying fully in current lesson, "
            "1.0 = completely breaking out (e.g. 'help me with assignments in general', 'ôn tập tổng quát'). "
            "Score 0.6+ means the user wants to break out of the active lesson context."
        )
    )

    # New topic if mentioned by the user
    new_topic_hint: Optional[str] = Field(
        None,
        description=(
            "If the user is pivoting to a specific new topic or concept (not the active lesson), "
            "name it here. Null if staying in current lesson or pivot is general."
        )
    )

    # Detected language
    detected_language: str = Field(
        default="vi",
        description="ISO 639-1 language code detected from user message (e.g. 'vi', 'en')."
    )

    # Confidence score
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in this classification."
    )

    reasoning: str = Field(
        description="Brief explanation of why this classification was chosen."
    )


_SYSTEM_PROMPT = """\
You are an Intent Weight Analyzer for a multilingual Learning Management System.

Your job: Given what the student is currently reading (active lesson) and their new message, determine whether the student wants to:
  (A) Work on the CURRENT active lesson (review it, do exercises, ask about it),
  (B) PIVOT away - asking for general support, a different topic, or general review unrelated to the active lesson, or
  (C) CRS Interaction - express learning preferences, request recommendations, critique suggestions, or ask for explanations.

Key disambiguation rules:
1. If the student says something like "help me review vocabulary / làm bài tập / ôn thi" WITHOUT referencing the specific lesson content or title -> this is a PIVOT (pivot_strength 0.7-0.9).
2. If the student says "review THIS lesson / bài này / bài này / đoạn này" -> staying in current lesson (pivot_strength 0.0-0.2).
3. If the student explicitly asks about a concept IN the current lesson -> ask_concept (pivot_strength 0.1-0.3).
4. If the student mentions a completely different topic -> pivot_new_topic (pivot_strength 0.8-1.0).
5. If the student shares details about how they prefer to study (e.g. "tôi thích học thực hành", "tôi muốn học nhanh hơn") -> elicit_preference (pivot_strength 0.5-0.7).
6. If the student directly asks for suggestions or what to do next (e.g. "what should I study?", "nên học gì bây giờ?") -> request_recommendation (pivot_strength 0.7-0.9).
7. If the student gives feedback on recommended paths (e.g. "bài này khó quá", "cho tôi bài khác", "tôi không muốn học SQL") -> provide_feedback (pivot_strength 0.6-0.8).
8. If the student asks why something was recommended (e.g. "sao tôi phải học bài này?", "tại sao lại gợi ý bài này?") -> ask_explanation (pivot_strength 0.4-0.6).

Be language-agnostic: analyze the MEANING, not the language surface form. Support Vietnamese, English, and mixed-language messages equally.

Return valid JSON matching the schema exactly.
"""


async def analyze_intent_weight(
    user_message: str,
    active_lesson_title: Optional[str],
    active_lesson_topic: Optional[str],
    mtm_anchor_topic: Optional[str],
) -> IntentWeightOutput:
    """
    Analyze whether the user wants to stay in the current lesson or pivot away.

    Args:
        user_message: Raw user message (any language).
        active_lesson_title: Title of the lesson student is viewing (from page_context).
        active_lesson_topic: Topic/subject of the active lesson (e.g. "Travel vocabulary").
        mtm_anchor_topic: The topic the MTM anchor is currently set to.

    Returns:
        IntentWeightOutput with pivot_strength and explicit_intent.
    """
    # Build context description for LLM - không dùng regex, để LLM phân tích
    context_lines = []
    if active_lesson_title:
        context_lines.append(f"Active lesson the student has open: \"{active_lesson_title}\"")
    if active_lesson_topic:
        context_lines.append(f"Active lesson topic/subject: \"{active_lesson_topic}\"")
    if mtm_anchor_topic:
        context_lines.append(f"MTM session anchor (last focused topic): \"{mtm_anchor_topic}\"")
    if not context_lines:
        context_lines.append("No active lesson context - student has no lesson open.")

    context_str = "\n".join(context_lines)

    user_content = (
        f"Context:\n{context_str}\n\n"
        f"Student's new message:\n\"{user_message}\"\n\n"
        "Analyze whether the student is staying in the active lesson or pivoting away. "
        "Return JSON."
    )

    try:
        result = await chat_complete_structured(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_model=IntentWeightOutput,
            model=settings.quiz_model,
            temperature=0.0,
            max_tokens=300,
            task=TASK_AGENT_ROUTER,
        )
        logger.debug(
            "IntentWeight: explicit_intent=%s pivot_strength=%.2f confidence=%.2f | reason=%s",
            result.explicit_intent,
            result.pivot_strength,
            result.confidence,
            result.reasoning[:80],
        )
        return result

    except Exception as exc:
        logger.warning("IntentWeightModel failed, defaulting to no-pivot: %s", exc)
        # Safe fallback: keep the current context, do not pivot
        return IntentWeightOutput(
            explicit_intent="review_current_lesson",
            pivot_strength=0.0,
            new_topic_hint=None,
            detected_language="vi",
            confidence=0.3,
            reasoning=f"Fallback due to error: {exc}",
        )