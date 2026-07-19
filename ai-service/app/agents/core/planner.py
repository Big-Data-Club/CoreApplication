"""
ai-service/app/agents/core/planner.py

Unified Agent Planner v2 - Merged Router + Planner in one LLM call.

Changes from v1:
  - RouterOutput fields (intent, is_ambiguous, matched_course_id, requires_tool)
    are now part of ExecutionPlan, eliminating the separate router LLM call.
  - Added graph_expansion_needed: bool - whether GraphRAG graph context should
    be fetched for this query.
  - Added user_weakness_relevant: bool - whether LTM mastery data should be
    pulled to re-rank retrieved chunks.
  - Added primary_node_id: int | None - if the query maps to a specific
    knowledge node, used to fetch the precise prereq chain.

Backward compatibility:
  - classify_intent() in router.py now delegates to generate_plan() and
    extracts RouterOutput fields from the returned ExecutionPlan.
  - All existing callers of generate_plan() work unchanged.
"""
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
    # ── Learning intent (v1 fields) ────────────────────────────────────────
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
            "'elicitation' (preference elicitation / user stating learning preferences), "
            "'feedback' (feedback / critique of recommended topics/items), "
            "'explanation_request' (asking why a recommendation was made), "
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

    # ── Router fields (v2 - merged from RouterOutput) ─────────────────────
    intent: str = Field(
        default="knowledge_question",
        description=(
            "Router intent classification. One of: "
            "knowledge_question, progress_advice, content_creation, "
            "interactive_exercise, general_chat"
        )
    )
    is_ambiguous: bool = Field(
        default=False,
        description="True if the request is vague or needs clarification."
    )
    ambiguity_reason: str | None = Field(
        default=None,
        description="Short reason code for ambiguity if is_ambiguous is True."
    )
    missing_context: str | None = Field(
        default=None,
        description="Clarifying question or description of what is missing."
    )
    matched_course_id: int | None = Field(
        default=None,
        description="The course ID if the user explicitly implies a specific course."
    )
    requires_tool: bool = Field(
        default=False,
        description="True if the request explicitly requires a system action (quiz gen, flashcard create, etc.)."
    )

    # ── GraphRAG v2 signals ────────────────────────────────────────────────
    graph_expansion_needed: bool = Field(
        default=True,
        description=(
            "True if graph context should be fetched from Neo4j to augment retrieval. "
            "Set False for general_chat, chitchat, dashboard_recommendation, or when "
            "retrieval_strategy.scope is 'none'."
        )
    )
    user_weakness_relevant: bool = Field(
        default=False,
        description=(
            "True if the user's mastery/weakness data should be fetched from LTM "
            "to re-rank retrieved chunks. Always True for knowledge_question and "
            "interactive_exercise intents."
        )
    )
    primary_node_name: str | None = Field(
        default=None,
        description=(
            "The primary concept node name from the query (if identifiable). "
            "Used to fetch the precise prerequisite chain from Neo4j. "
            "Example: 'Hàng đợi (Queue)', 'Binary Search Tree'. Null if unknown."
        )
    )


PLANNER_SYSTEM_PROMPT = """\
You are the Unified Agent Planner v2 for the BDC Learning Management System.
Your job is to analyze the user's message, conversation context, and active UI context,
then generate a cohesive ExecutionPlan that covers BOTH routing AND planning in one pass.

Active courses for this user:
{course_list}

{current_context}

Available Tools:
- search_course_materials: Search course materials using semantic RAG
- explain_concept: Pedagogy-aware conceptual explanation with prereq awareness
- get_study_plan: Generate personalized next steps / roadmap based on Lakehouse metrics
- diagnose_knowledge_gap: Check student weaknesses / wrong answers
- create_mini_challenge: Quick check concept exercises
- generate_flashcard: Flashcard creation
- search_web: Web search fallback
- save_to_notebook: Save content to student notebook

Planning Rules:
1. **Understand Intent & Context**:
   - Dashboard (pageType=dashboard or no open lesson) + "what to study next?" -> recommendation_engine, personalization+lakehouse required, scope='none', graph_expansion_needed=false.
   - Lesson view (pageType=lesson) + "explain this" -> stay_in_context, content_qa, scope='content', graph_expansion_needed=true.
   - Asking about topic not in current lesson -> pivot_new_topic, scope='course' or 'global', graph_expansion_needed=true.
   - Greetings/chitchat -> general_chat, scope='none', graph_expansion_needed=false.
   - Request recommendation/next steps ("nên học gì tiếp theo?", "gợi ý bài tiếp theo") -> recommendation_engine, user_intent='recommendation', personalization+lakehouse required, scope='none', selected_tools=['get_study_plan'].
   - Share study preferences ("tôi thích thực hành", "tôi muốn học nâng cao") -> recommendation_engine, user_intent='elicitation', personalization+lakehouse required, scope='none'.
   - Reject/critique suggestions ("bài này khó quá", "tôi không muốn học SQL") -> recommendation_engine, user_intent='feedback', personalization+lakehouse required, scope='none', selected_tools=['get_study_plan'].
   - Ask why something was recommended ("sao tôi phải học bài này?", "tại sao gợi ý bài này?") -> recommendation_engine, user_intent='explanation_request', personalization+lakehouse required.

2. **GraphRAG Signals**:
   - Set graph_expansion_needed=true whenever the user asks a knowledge question (explanation, clarification, comparison, prerequisite) and course materials are indexed.
   - Set user_weakness_relevant=true for knowledge_question and interactive_exercise intents, where mastery-based re-ranking can help.
   - Extract primary_node_name if the user names a specific concept (e.g. "Queue", "Binary Search", "TCP/IP"). Set to null for general or multi-topic queries.

3. **Router fields** (merged):
   - intent: classify into one of the 5 router intents (use 'progress_advice' for recommendation requests, elicitation, feedback, and explanation requests).
   - is_ambiguous: true if the request is too vague and cannot be acted on without clarification.
   - matched_course_id: set if user explicitly names or implies a specific course from the active courses list.
   - requires_tool: true only if the user explicitly asks for a system action (generate quiz, create flashcard, etc.).

4. **Retrieval Scope & Expansion**:
   - Start narrow (content if in a lesson, course if viewing course), enable expansion to global as fallback.
   - For recommendation or general chitchat, set scope='none'.

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
    Unified planning step - produces a single ExecutionPlan covering both
    routing intent and retrieval/tool planning.

    When MERGED_PLANNER_ENABLED=true (default), this is the only LLM call
    for the planning phase.  When false, the result is identical but the
    legacy router.py still makes a separate call for backward compatibility.
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
        node_id = page_context.get("nodeId") or page_context.get("node_id")
        if node_id:
            current_context_lines.append(f"  - Current Node ID: {node_id}")
        quiz_id = page_context.get("quizId") or page_context.get("quiz_id") or (page_context.get("extra") or {}).get("quizId") or (page_context.get("extra") or {}).get("quiz_id")
        if quiz_id:
            current_context_lines.append(f"  - Current Quiz ID: {quiz_id}")

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
            hist_str += f"- {m.get('role')}: {m.get('content', '')[:200]}\n"

    user_prompt = f"User Message: \"{user_message}\"\n{hist_str}\nGenerate ExecutionPlan."

    try:
        plan = await chat_complete_structured(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT.format(
                    course_list=course_list,
                    current_context=current_context,
                )},
                {"role": "user", "content": user_prompt},
            ],
            response_model=ExecutionPlan,
            model=settings.quiz_model,  # use accurate model for planning
            temperature=0.0,
            max_tokens=600,
            task=TASK_AGENT_ROUTER,
        )
        logger.info(
            "AgentPlan v2: intent=%s op_intent=%s operation=%s scope=%s "
            "tools=%s graph=%s weakness=%s node='%s' ambiguous=%s",
            plan.user_intent, plan.operational_intent, plan.operation,
            plan.retrieval_strategy.scope, plan.selected_tools,
            plan.graph_expansion_needed, plan.user_weakness_relevant,
            plan.primary_node_name, plan.is_ambiguous,
        )
        return plan
    except Exception as exc:
        logger.error("Agent unified planning v2 failed: %s. Using fallback plan.", exc)
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
            # Router defaults
            intent="knowledge_question",
            is_ambiguous=False,
            requires_tool=False,
            # GraphRAG defaults - conservative fallback
            graph_expansion_needed=bool(current_course_id),
            user_weakness_relevant=False,
            primary_node_name=None,
        )
