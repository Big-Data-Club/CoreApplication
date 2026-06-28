from __future__ import annotations

import logging
from typing import Optional, List
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import chat_complete_structured
from app.core.llm_gateway import TASK_AGENT_ROUTER

logger = logging.getLogger(__name__)
settings = get_settings()


class RetrievalStrategy(BaseModel):
    scope: str = Field(
        description="One of: 'content', 'section', 'course', 'cross_course', 'global', 'none'"
    )
    depth: int = Field(
        default=3,
        description="Number of chunks to fetch (top_k)"
    )
    min_similarity: float = Field(
        default=0.25,
        description="Minimum similarity score threshold"
    )
    expansion_enabled: bool = Field(
        default=True,
        description="Whether to expand scope if initial retrieval is insufficient"
    )
    max_expansion_level: str = Field(
        default="global",
        description="Maximum level to expand: 'content', 'section', 'course', 'global'"
    )


class ExecutionPlan(BaseModel):
    user_intent: str = Field(
        description=(
            "Learner's learning goal. One of: "
            "'explanation' (explain concept/lesson), "
            "'clarification' (clarify ambiguous question), "
            "'recommendation' (what to study next/next steps), "
            "'comparison' (compare two concepts), "
            "'navigation' (course roadmap/structure), "
            "'quiz_help' (quiz attempts/wrong answers), "
            "'prerequisite' (foundational knowledge), "
            "'next_step' (next learning action), "
            "'chitchat' (greetings/chitchat), "
            "'other'"
        )
    )
    operational_intent: str = Field(
        description=(
            "The app context mapping. One of: "
            "'stay_in_context' (asking about the currently open lesson/content), "
            "'pivot_new_topic' (asking about a new topic/course not currently open), "
            "'global_search' (general query without open lesson context), "
            "'dashboard_recommendation' (on dashboard asking what to do next)"
        )
    )
    operation: str = Field(
        description=(
            "The engine operation to execute. One of: "
            "'content_qa' (QA over course materials), "
            "'recommendation_engine' (personalization recommendations), "
            "'navigation_helper' (course mapping/roadmap), "
            "'quiz_assist' (quiz help/wrong answer diagnostics), "
            "'general_chat' (greetings/chitchat)"
        )
    )
    retrieval_strategy: RetrievalStrategy
    selected_tools: List[str] = Field(
        description=(
            "List of tool names selected to execute this plan. "
            "Available tools: ['search_course_materials', 'explain_concept', "
            "'get_study_plan', 'diagnose_knowledge_gap', 'create_mini_challenge', "
            "'generate_flashcard', 'search_web', 'save_to_notebook']"
        )
    )
    personalization_enabled: bool = Field(
        description="True if student-specific history/mastery from the Lakehouse should be used to tailor the response."
    )
    lakehouse_required: bool = Field(
        description="True if DuckDB Lakehouse analytics/logs must be fetched (via personalize-service) to fulfill the request."
    )
    reasoning: str = Field(
        description="Chain-of-thought explanation for why this plan was selected."
    )


PLANNER_SYSTEM_PROMPT = """\
You are the Unified Agent Planner for the BDC Learning Management System.
Your job is to analyze the user's message, conversation context, and active UI context, and generate a cohesive ExecutionPlan.

Active courses for this user:
{course_list}

{current_context}

Available Tools:
- search_course_materials: Search course materials using semantic RAG
- explain_concept: Pedagogy-aware conceptual explanation
- get_study_plan: Generate personalized next steps / roadmap based on Lakehouse metrics
- diagnose_knowledge_gap: Check student weaknesses / wrong answers
- create_mini_challenge: Quick check concept exercises
- generate_flashcard: Flashcard creation
- search_web: Web search fallback
- save_to_notebook: Save content to student notebook

Rules:
1. **Understand Intent & Context**:
   - If the user asks "what should I study next?" or "help me review" on the Dashboard (pageType=dashboard or no open lesson), this is a recommendation engine operation, personalization/lakehouse are required, and retrieval strategy scope is 'none'.
   - If they are viewing a lesson (pageType=lesson) and ask "Explain this section" or "what does this mean?", they want to 'stay_in_context'. Operation is 'content_qa'. Retrieval scope is 'content'. Personalization is optional.
   - If they ask about a concept not in the current lesson, they are pivoting. Operational intent is 'pivot_new_topic'. Scope is 'course' or 'global'.
2. **Retrieval Scope & Expansion**:
   - Limit scope to 'content' initially if they are studying a specific lesson. Set expansion_enabled=True and max_expansion_level='global' so they can fallback to module/course/global if the lesson has insufficient detail.
   - For recommendation or general chitchat, set scope to 'none'.
3. **Personalization**:
   - Any progress/advice/next-step queries require personalization_enabled=True and lakehouse_required=True.

Return valid JSON matching the schema.
"""


async def generate_plan(
    user_message: str,
    active_courses: dict | None = None,
    agent_type: str = "mentor",
    current_course_id: int | None = None,
    page_context: dict | None = None,
    system_context: dict | None = None,
    history: list[dict] | None = None,
) -> ExecutionPlan:
    """
    Unified planning step to produce a structured ExecutionPlan for the agent turn.
    """
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
    
    # Page Context
    if page_context:
        page_type = page_context.get("pageType") or page_context.get("type") or page_context.get("page_type")
        if page_type:
            current_context_lines.append(f"  - Page Type: {page_type}")
        content_title = page_context.get("contentTitle") or page_context.get("title") or page_context.get("name")
        if content_title:
            current_context_lines.append(f"  - Current Content Title: \"{content_title}\"")
        content_id = page_context.get("contentId") or page_context.get("content_id")
        if content_id:
            current_context_lines.append(f"  - Current Content ID: {content_id}")
        section_id = page_context.get("sectionId") or page_context.get("section_id")
        if section_id:
            current_context_lines.append(f"  - Current Section ID: {section_id}")

    # System Context
    if system_context:
        lesson_title = system_context.get("lesson_title")
        if lesson_title:
            current_context_lines.append(f"  - Active Micro Lesson Title: \"{lesson_title}\"")
        lesson_id = system_context.get("lesson_id") or system_context.get("content_id")
        if lesson_id:
            current_context_lines.append(f"  - Active Micro Lesson ID: {lesson_id}")

    current_context = ""
    if current_context_lines:
        current_context = "Current UI & Learning Context:\n" + "\n".join(current_context_lines)

    # Format history
    hist_str = ""
    if history:
        hist_str = "\nRecent Conversation History:\n"
        for m in history[-5:]:
            hist_str += f"- {m.get('role')}: {m.get('content')}\n"

    user_prompt = f"User Message: \"{user_message}\"\n{hist_str}\nGenerate ExecutionPlan."

    try:
        plan = await chat_complete_structured(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT.format(course_list=course_list, current_context=current_context)},
                {"role": "user", "content": user_prompt},
            ],
            response_model=ExecutionPlan,
            model=settings.quiz_model,  # use accurate model for planning
            temperature=0.0,
            max_tokens=512,
            task=TASK_AGENT_ROUTER,
        )
        logger.info(
            "AgentPlan: user_intent=%s, operational_intent=%s, operation=%s, retrieval_scope=%s, selected_tools=%s, personalization=%s",
            plan.user_intent, plan.operational_intent, plan.operation,
            plan.retrieval_strategy.scope, plan.selected_tools, plan.personalization_enabled
        )
        return plan
    except Exception as exc:
        logger.error("Agent unified planning failed: %s. Generating fallback plan.", exc)
        # Fallback plan
        return ExecutionPlan(
            user_intent="other",
            operational_intent="global_search",
            operation="content_qa",
            retrieval_strategy=RetrievalStrategy(
                scope="course" if current_course_id else "global",
                depth=3,
                min_similarity=0.25,
                expansion_enabled=True,
                max_expansion_level="global",
            ),
            selected_tools=["search_course_materials", "explain_concept"],
            personalization_enabled=False,
            lakehouse_required=False,
            reasoning=f"Fallback due to planning error: {exc}",
        )
