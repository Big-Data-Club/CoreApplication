from __future__ import annotations

import json
import logging
import time
import uuid
from typing import AsyncIterator

from app.agents.events import AgentEvent, AgentEventType
from app.agents.memory.stm import stm
from app.agents.memory.mtm import mtm
from app.agents.memory.message_store import message_store
from app.agents.memory.context_builder import context_builder
from app.agents.memory.active_courses import (
    format_active_courses_for_prompt,
    invalidate_active_courses,
    load_active_courses,
)
from app.agents.memory.lesson_dossier import (
    format_lesson_dossier,
    load_lesson_dossier,
)
from app.agents.core.prompts import build_system_prompt
from app.agents.core.scope_resolver import (
    apply_scope_to_course_id,
)
from app.agents.core.context_foundation import (
    _as_positive_int,
    resolve_turn_context,
    resume_request_after_course_choice,
)
from app.agents.core.clarification import (
    build_scope_clarification,
    should_clarify,
)
from app.agents.tools.registry import (
    get_tool_schemas, get_tool_by_name, execute_tool,
)
from app.core.config import get_settings
from app.core.llm_gateway import get_gateway, ChatRequest, TASK_AGENT_REACT
from app.agents.tools.base_tool import ToolResult

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_ITERATIONS = 5
MAX_CLARIFICATIONS_PER_SESSION = 2


def _val(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _is_teacher_authoring_request(message: str) -> bool:
    """Fail-safe route for actions that must reach the HITL tool workflow.

    Router confidence is intentionally probabilistic; publishing-oriented
    teacher requests cannot be.  If the router misses a short Vietnamese or
    English authoring request, sending it to prose-only multi-agent mode loses
    the editable draft and can overload its retrieval context.
    """
    text = (message or "").lower()
    action_markers = (
        "tạo", "soạn", "thêm", "xuất bản", "generate", "create", "draft", "publish",
    )
    artifact_markers = (
        "bài học", "lesson", "nội dung", "content", "quiz", "câu hỏi", "question",
        "bài kiểm tra", "assessment", "slide", "tài liệu", "material",
    )
    if not (
        any(marker in text for marker in action_markers)
        and any(marker in text for marker in artifact_markers)
    ):
        return False
    # Guard against false positives: conceptual/explanatory questions that
    # merely CONTAIN an action word must stay on the prose/tool path.
    question_markers = (
        "là gì", "thế nào", "như thế nào", "giải thích", "khái niệm",
        "ý nghĩa", "explain", "what is", "what are", "how does", "meaning of",
    )
    return not any(marker in text for marker in question_markers)


def _format_compact_teacher_courses(active_courses: dict) -> str:
    """Keep authoritative course IDs without injecting every graph node."""
    courses = active_courses.get("courses") or []
    if not courses:
        return ""
    lines = [
        "ACTIVE COURSES FOR THIS USER",
        "(Use only these course_ids. Knowledge nodes are fetched on demand.)",
    ]
    for course in courses:
        if course.get("id") is not None:
            lines.append(f'- course_id={course["id"]} "{course.get("title", "")}" (owner)')
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# [PATCH 1] Dynamic max_tokens
# -----------------------------------------------------------------------------

def _resolve_max_tokens(intent_type: str, has_page_context: bool) -> int:
    """
    Allocate the token budget for the LLM based on the expected complexity of the response.

    Instead of a hardcoded 2048 for all cases, the budget is adjusted according to the intent:
    - content_creation / interactive_exercise: tools perform the heavy generation -> 2048
    - knowledge_question + page_context (currently studying a lesson): requires deep explanation -> 3500
    - standard knowledge_question: -> 3000
    - progress_advice: -> 2500
    - general_chat / fallback: -> 2048
    """
    if intent_type in ("content_creation", "interactive_exercise"):
        return 2048
    if intent_type == "knowledge_question":
        return 3500 if has_page_context else 3000
    if intent_type == "progress_advice":
        return 2500
    return 2048


# -----------------------------------------------------------------------------
# [PATCH 2] Smart tool result truncation
# -----------------------------------------------------------------------------

def _smart_truncate_tool_result(
    tool_name: str,
    result_content: str,
    limit: int = 4000,
) -> str:
    """
    Truncate tool results semantically instead of using a hard character limit.

    - search_course_materials: keep chunks intact, cut at boundaries
    - diagnose_knowledge_gap: keep weaknesses + prerequisite_chains
    - explain_concept: trim each text chunk
    - fallback: cut at the newline closest to the limit
    """
    if len(result_content) <= limit:
        return result_content

    try:
        data = json.loads(result_content)

        if tool_name in ("search_course_materials", "explain_concept"):
            chunks = data.get("data", {}).get("chunks", [])
            kept, char_count = [], 0
            for chunk in chunks:
                chunk_json = json.dumps(chunk, ensure_ascii=False)
                if char_count + len(chunk_json) > int(limit * 0.85):
                    break
                kept.append(chunk)
                char_count += len(chunk_json)
            data.setdefault("data", {})["chunks"] = kept
            data["data"]["_truncated"] = f"showing {len(kept)}/{len(chunks)} chunks"
            return json.dumps(data, ensure_ascii=False)

        if tool_name == "diagnose_knowledge_gap":
            inner = data.get("data", {})
            inner.pop("recent_errors", None)
            data["data"] = inner
            result = json.dumps(data, ensure_ascii=False)
            if len(result) <= limit:
                return result

        if tool_name == "explain_concept":
            inner = data.get("data", {})
            for m in inner.get("course_materials", []):
                if len(m.get("text", "")) > 500:
                    m["text"] = m["text"][:500] + "…"
            data["data"] = inner
            return json.dumps(data, ensure_ascii=False)

    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Generic fallback: cắt tại newline
    truncated = result_content[:limit]
    last_nl = truncated.rfind("\n")
    if last_nl > int(limit * 0.8):
        truncated = truncated[:last_nl]
    return truncated + "\n[result truncated for context budget]"


# -----------------------------------------------------------------------------
# Reference ledger: assigns stable [n] citation numbers per turn
# -----------------------------------------------------------------------------

from app.agents.core.references import ReferenceLedger


# -----------------------------------------------------------------------------
# ThoughtStreamParser
# -----------------------------------------------------------------------------

class ThoughtStreamParser:
    """
    Parses streamed tokens on the fly to separate thoughts wrapped inside
    <thought>...</thought> tags from the final content response.
    """
    def __init__(self):
        self.buffer = ""
        self.in_thought = False
        self.thought_buffer = ""
        self.content_buffer = ""
        self.tag_checked = False

    def feed(self, delta: str) -> list[tuple[str, str]]:
        """
        Feeds a chunk of text delta and returns a list of tuples (event_type, text_chunk).
        event_type can be 'thought' or 'content'.
        """
        self.buffer += delta
        events = []

        if not self.tag_checked:
            prefix = "<thought>"
            if len(self.buffer) >= len(prefix):
                if self.buffer.startswith(prefix):
                    self.in_thought = True
                    self.buffer = self.buffer[len(prefix):]
                self.tag_checked = True
            elif not prefix.startswith(self.buffer):
                self.tag_checked = True

        if self.in_thought:
            end_tag = "</thought>"
            idx = self.buffer.find(end_tag)
            if idx != -1:
                thought_part = self.buffer[:idx]
                if thought_part:
                    self.thought_buffer += thought_part
                    events.append(("thought", thought_part))
                
                self.in_thought = False
                self.buffer = self.buffer[idx + len(end_tag):]
                
                if self.buffer:
                    self.content_buffer += self.buffer
                    events.append(("content", self.buffer))
                    self.buffer = ""
            else:
                # Only buffer what could potentially form the start of </thought>
                # Check suffixes of self.buffer to see if they match prefixes of end_tag
                overlap = 0
                for i in range(1, min(len(self.buffer), len(end_tag)) + 1):
                    if end_tag.startswith(self.buffer[-i:]):
                        overlap = i
                
                if overlap > 0:
                    emit_part = self.buffer[:-overlap]
                    if emit_part:
                        self.thought_buffer += emit_part
                        events.append(("thought", emit_part))
                    self.buffer = self.buffer[-overlap:]
                else:
                    self.thought_buffer += self.buffer
                    events.append(("thought", self.buffer))
                    self.buffer = ""
        else:
            if self.tag_checked and self.buffer:
                self.content_buffer += self.buffer
                events.append(("content", self.buffer))
                self.buffer = ""

        return events

    def flush(self) -> list[tuple[str, str]]:
        events = []
        if self.buffer:
            if self.in_thought:
                events.append(("thought", self.buffer))
                self.thought_buffer += self.buffer
            else:
                events.append(("content", self.buffer))
                self.content_buffer += self.buffer
            self.buffer = ""
        return events

    # [PATCH 3] Trả về full thought để structured log
    def get_full_thought(self) -> str:
        return self.thought_buffer


# -----------------------------------------------------------------------------
# Main ReAct loop
# -----------------------------------------------------------------------------

async def run_react_loop(
    session_id: str,
    user_id: int,
    agent_type: str,
    user_message: str,
    course_id: int | None = None,
    user_context: dict | None = None,
    page_context: dict | None = None,
    system_context: dict | None = None,
) -> AsyncIterator[AgentEvent]:
    """
    Execute the full ReAct loop for a single user turn.

    This is an async generator that yields AgentEvents as they happen.
    The caller (SSE endpoint) iterates over these events and streams
    them to the frontend.

    Args:
        session_id: MTM session UUID.
        user_id: Authenticated user ID.
        agent_type: "teacher" or "mentor".
        user_message: The user's raw message text.
        course_id: Optional course context.

    Yields:
        AgentEvent objects in chronological order.
    """
    turn_id = uuid.uuid4().hex[:8]
    start_time = time.monotonic()

    logger.info(
        "ReAct start: session=%s user=%d agent=%s msg='%s'",
        session_id[:8], user_id, agent_type, user_message[:80],
    )

    # -- Step 1.5: Load active courses ----------------------------------------
    active_courses = await load_active_courses(
        user_id=user_id,
        agent_type=agent_type,
    )

    # -- Step 1a: Verify the UI context before spending an LLM call ---------
    # Page context is a browser hint, never authority.  This fast resolver
    # checks the hinted course against the user's active-course list and stops
    # course-bound actions when there is no safe target.
    context_resolution = resolve_turn_context(
        message=user_message,
        page_context=page_context,
        user_context=user_context,
        active_courses=active_courses,
        agent_type=agent_type,
        explicit_course_id=course_id,
    )

    # The browser/panel pointed at a specific course that failed verification.
    # That is often just a stale anchor cache (fresh enrolment, role switch,
    # LMS hiccup). Re-fetch the authoritative list once before asking the
    # user to pick a course they may demonstrably be viewing.
    hinted_course_id = _as_positive_int(course_id) or context_resolution.snapshot.course_id
    if context_resolution.status == "needs_course_choice" and hinted_course_id:
        logger.info(
            "Course hint %s failed verification; refreshing active courses",
            hinted_course_id,
        )
        active_courses = await load_active_courses(
            user_id=user_id,
            agent_type=agent_type,
            refresh=True,
        )
        context_resolution = resolve_turn_context(
            message=user_message,
            page_context=page_context,
            user_context=user_context,
            active_courses=active_courses,
            agent_type=agent_type,
            explicit_course_id=course_id,
        )

    yield AgentEvent(
        type=AgentEventType.CONTEXT,
        data=context_resolution.as_dict(),
        session_id=session_id,
        turn_id=turn_id,
    )

    if context_resolution.status == "needs_course_navigation":
        # Navigation changes the user's workspace, so make it an explicit
        # human-approved action even though it is reversible.
        yield AgentEvent(
            type=AgentEventType.HITL_REQUEST,
            data={
                "tool": "navigate_to_course_list",
                "message": context_resolution.clarification_question,
                "data": {"action": "navigate", **(context_resolution.navigation or {})},
            },
            session_id=session_id,
            turn_id=turn_id,
        )
        await stm.append(session_id, "user", user_message)
        await stm.append(session_id, "clarification", context_resolution.clarification_question or "")
        await message_store.save_message(session_id, "user", user_message)
        await message_store.save_message(
            session_id,
            "assistant",
            context_resolution.clarification_question or "",
            {
                "hitlRequest": {
                    "tool": "navigate_to_course_list",
                    "message": context_resolution.clarification_question or "",
                    "data": {"action": "navigate", **(context_resolution.navigation or {})},
                },
                "context": context_resolution.as_dict(),
            },
        )
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={"reason": "course_navigation_requested"},
            session_id=session_id,
            turn_id=turn_id,
        )
        return

    if context_resolution.status == "needs_course_choice":
        question = context_resolution.clarification_question or "Bạn muốn làm việc với khóa học nào?"
        await stm.append(session_id, "user", user_message)
        await stm.append(
            session_id,
            "clarification",
            question,
            metadata={"kind": "scope", "pending_user_request": user_message},
        )
        await message_store.save_message(session_id, "user", user_message)
        await message_store.save_message(
            session_id,
            "assistant",
            question,
            {"context": context_resolution.as_dict()},
        )
        yield AgentEvent(
            type=AgentEventType.CLARIFICATION,
            data={
                "kind": "scope",
                "question": question,
                "options": context_resolution.clarification_options,
                "missing": ["course_id"],
            },
            session_id=session_id,
            turn_id=turn_id,
        )
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={"reason": "course_selection_requested"},
            session_id=session_id,
            turn_id=turn_id,
        )
        return

    # -- Step 1: Unified Planning Layer ----------------------------------------
    from app.agents.core.planner import generate_plan
    from app.agents.core.scope_resolver import CourseScope, ContextScopeDecision
    from app.agents.core.router import classify_intent

    # Retrieve history for context
    history_turns = []
    try:
        history_turns = await stm.get_window(session_id, n_turns=5)
    except Exception:
        pass

    effective_user_request = resume_request_after_course_choice(
        message=user_message,
        resolution=context_resolution,
        history=history_turns,
    )

    execution_plan = await generate_plan(
        user_message=effective_user_request,
        active_courses=active_courses,
        agent_type=agent_type,
        current_course_id=context_resolution.course_id or course_id,
        page_context=page_context,
        system_context=system_context,
        history=history_turns,
    )

    # Planner v2 covers routing - use execution_plan fields directly
    # The legacy classify_intent() wrapper would just call generate_plan() again;
    # we short-circuit it by building a lightweight RouterOutput from the plan.
    from app.agents.core.router import RouterOutput
    router_output = RouterOutput(
        intent=execution_plan.intent,
        is_ambiguous=execution_plan.is_ambiguous,
        ambiguity_reason=execution_plan.ambiguity_reason,
        missing_context=execution_plan.missing_context,
        matched_course_id=execution_plan.matched_course_id,
        requires_tool=execution_plan.requires_tool,
    )

    # Downstream token budgets, memory, and orchestration expect the router's
    # operational categories (content_creation, knowledge_question, ...), not
    # the pedagogical user_intent labels (explanation, quiz_help, ...).
    intent_type = execution_plan.intent

    yield AgentEvent(
        type=AgentEventType.THINKING,
        data={
            "step": "unified_plan",
            "user_intent": execution_plan.user_intent,
            "operational_intent": execution_plan.operational_intent,
            "operation": execution_plan.operation,
            "retrieval_scope": execution_plan.retrieval_strategy.scope,
            "retrieval_depth": execution_plan.retrieval_strategy.depth,
            "expansion_enabled": execution_plan.retrieval_strategy.expansion_enabled,
            "selected_tools": execution_plan.selected_tools,
            "personalization_enabled": execution_plan.personalization_enabled,
            "lakehouse_required": execution_plan.lakehouse_required,
            "reasoning": execution_plan.reasoning,
            # GraphRAG v2 signals
            "graph_expansion_needed": getattr(execution_plan, "graph_expansion_needed", False),
            "user_weakness_relevant": getattr(execution_plan, "user_weakness_relevant", False),
            "primary_node_name": getattr(execution_plan, "primary_node_name", None),
        },
        session_id=session_id,
        turn_id=turn_id,
    )

    logger.info(
        "═══ Unified Execution Plan [session=%s] ═══\n"
        "User Intent: %s\n"
        "Operational Intent: %s\n"
        "Operation: %s\n"
        "Retrieval Scope: %s (Depth: %d, Expansion: %s)\n"
        "Selected Tools: %s\n"
        "Personalization: %s (Lakehouse: %s)\n"
        "Reasoning: %s\n"
        "═══ END Plan ═══",
        session_id[:8],
        execution_plan.user_intent,
        execution_plan.operational_intent,
        execution_plan.operation,
        execution_plan.retrieval_strategy.scope,
        execution_plan.retrieval_strategy.depth,
        execution_plan.retrieval_strategy.expansion_enabled,
        execution_plan.selected_tools,
        execution_plan.personalization_enabled,
        execution_plan.lakehouse_required,
        execution_plan.reasoning,
    )

    # Build ContextScopeDecision and CourseScope adapters for backwards compatibility
    is_pivot = execution_plan.operational_intent in ("pivot_new_topic", "global_search")
    use_page = bool(page_context and not is_pivot)
    use_sys = bool(system_context and not is_pivot)

    ctx_decision = ContextScopeDecision(
        use_page_context=use_page,
        use_system_context=use_sys,
        effective_page_context=page_context if use_page else None,
        effective_system_context=system_context if use_sys else None,
        reason=f"Unified plan operational_intent: {execution_plan.operational_intent}",
        intent_weight=None,
        suggested_search_topic=user_message if is_pivot else None,
    )

    # The deterministic resolution is the trusted default. The planner may
    # refine it only when it returned an ID from the active course list.
    focus_course_id = context_resolution.course_id or course_id
    active_course_ids = {
        c.get("id") for c in (active_courses.get("courses") or [])
        if c.get("id") is not None
    }
    if not focus_course_id and execution_plan.matched_course_id in active_course_ids:
        focus_course_id = execution_plan.matched_course_id
    if not focus_course_id and page_context:
        page_course_id = page_context.get("courseId") or page_context.get("course_id")
        if page_course_id in active_course_ids:
            focus_course_id = page_course_id
    if not focus_course_id and system_context:
        system_course_id = system_context.get("course_id") or system_context.get("courseId")
        if system_course_id in active_course_ids:
            focus_course_id = system_course_id

    mode = "single" if focus_course_id else "global"
    if execution_plan.retrieval_strategy.scope == "global":
        mode = "all"

    scope = CourseScope(
        mode=mode,
        focus_course_id=focus_course_id,
        candidate_course_ids=[focus_course_id] if focus_course_id else [],
        confidence=1.0,
        reason=f"Unified plan scope: {execution_plan.retrieval_strategy.scope}",
        needs_clarification=False,
    )
    effective_course_id = apply_scope_to_course_id(scope, fallback_course_id=None)

    yield AgentEvent(
        type=AgentEventType.SCOPE,
        data=scope.as_dict(),
        session_id=session_id,
        turn_id=turn_id,
    )

    logger.debug(
        "Scope resolved: mode=%s focus=%s reason=%s",
        scope.mode, scope.focus_course_id, scope.reason,
    )

    # If the scope resolver locked onto a single course, pin it into MTM
    # so the next turn benefits from the anchor too. We update the recent
    # courses MRU list as well - useful when the user bounces between
    # courses without re-naming them.
    if scope.mode == "single" and scope.focus_course_id is not None:
        focus_title = next(
            (
                c.get("title")
                for c in (active_courses.get("courses") or [])
                if c.get("id") == scope.focus_course_id
            ),
            None,
        )
        try:
            await mtm.push_recent_course(
                session_id=session_id,
                course_id=scope.focus_course_id,
                course_title=focus_title,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("push_recent_course failed: %s", exc)

    # -- Step 2: Assemble memory context --------------------------------------
    memory_ctx = await context_builder.build(
        user_id=user_id,
        session_id=session_id,
        agent_type=agent_type,
        query=effective_user_request,
        course_id=effective_course_id,
        intent_type=intent_type,
        scope_course_ids=scope.candidate_course_ids or None,
    )

    yield AgentEvent(
        type=AgentEventType.THINKING,
        data={
            "step": "memory",
            "token_estimate": memory_ctx["token_estimate"],
            "stm_messages": len(memory_ctx["stm_messages"]),
        },
        session_id=session_id,
        turn_id=turn_id,
    )

    logger.debug(
        "Context assembled: tokens~%d, stm=%d msgs (%.0fms)",
        memory_ctx["token_estimate"],
        len(memory_ctx["stm_messages"]),
        (time.monotonic() - start_time) * 1000,
    )

    # -- Step 3: Clarification gate --------------------------------------------
    stm_history = memory_ctx["stm_messages"]
    clarify_count = sum(
        1 for m in stm_history if m.get("role") == "clarification"
    )

    if clarify_count < MAX_CLARIFICATIONS_PER_SESSION:
        # (a) Scope clarification - runs first, no LLM call.
        scope_clarify = build_scope_clarification(scope)

        # (b) Router clarification - runs if router flagged ambiguity (e.g., vague request, missing params)
        router_clarify: dict | None = None
        if scope_clarify is None and router_output.is_ambiguous:
            router_clarify = {
                "needs_clarification": True,
                "kind": "parameter",
                "confidence": 0.5,
                "clarification_question": router_output.missing_context or "Bạn có thể nói rõ hơn không?",
                "clarification_options": [],
                "missing_fields": [router_output.ambiguity_reason] if router_output.ambiguity_reason else [],
            }

        # (c) Parameter clarification - fallback if both scope and router are clean.
        param_clarify: dict | None = None
        if scope_clarify is None and router_clarify is None and scope.mode != "ambiguous":
            tool_schemas = get_tool_schemas(agent_type)
            mtm_ctx = memory_ctx["raw"].get("mtm", {})
            try:
                result = await should_clarify(
                    user_message=effective_user_request,
                    tool_schemas=tool_schemas,
                    session_context=mtm_ctx,
                )
                if (result.get("needs_clarification")
                        and result.get("confidence", 1.0) < 0.6):
                    param_clarify = result
            except Exception as exc:  # noqa: BLE001
                logger.warning("parameter clarification failed: %s", exc)

        clarify_result = scope_clarify or router_clarify or param_clarify
        if clarify_result:
            question = clarify_result.get(
                "clarification_question",
                "Bạn có thể nói rõ hơn không?",
            )
            options = clarify_result.get("clarification_options", [])

            logger.info(
                "Clarification triggered (kind=%s): '%s'",
                clarify_result.get("kind", "parameter"), question[:60],
            )

            await stm.append(session_id, "user", user_message)
            await stm.append(session_id, "clarification", question)

            yield AgentEvent(
                type=AgentEventType.CLARIFICATION,
                data={
                    "kind": clarify_result.get("kind", "parameter"),
                    "question": question,
                    "options": options,
                    "missing": clarify_result.get("missing_fields", []),
                },
                session_id=session_id,
                turn_id=turn_id,
            )
            yield AgentEvent(
                type=AgentEventType.DONE,
                data={"reason": "clarification_requested"},
                session_id=session_id,
                turn_id=turn_id,
            )
            return

    # Save user message to STM and persistent store before processing
    await stm.append(session_id, "user", user_message)
    await message_store.save_message(session_id, "user", user_message)

    # -- Step 3.5: Multi-Agent Spawning ----------------------------------------
    from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator

    parent_context_length = memory_ctx.get("token_estimate", 0) + len(user_message) // 4
    orchestrator = MultiAgentOrchestrator(session_id, turn_id)

    # Truyền thêm page/sys context và stm_turn_count vào spawning score
    score, breakdown = orchestrator.calculate_spawning_score(
        user_message=effective_user_request,
        intent_type=intent_type,
        parent_context_length=parent_context_length,
        page_context=ctx_decision.effective_page_context,
        system_context=ctx_decision.effective_system_context,
        stm_turn_count=len(stm_history),
    )

    yield AgentEvent(
        type=AgentEventType.THINKING,
        data={
            "step": "multi_agent_decision",
            "score": score,
            "breakdown": breakdown,
        },
        session_id=session_id,
        turn_id=turn_id,
    )

    # The multi-agent pipeline produces prose only and cannot execute tools or
    # emit HITL widgets. Keep teacher action requests in the tool-capable ReAct
    # loop so "create/add" actually results in an editable draft.
    teacher_action_request = agent_type == "teacher" and (
        router_output.requires_tool
        or intent_type in ("content_creation", "interactive_exercise")
        or _is_teacher_authoring_request(effective_user_request)
    )

    if score >= 0.45 and not teacher_action_request:
        logger.info(
            "Spawning multi-agent: score=%.3f reasons=%s",
            score, breakdown.get("triggered_by", []),
        )
        try:
            final_answer = ""
            async for ev in orchestrator.run_multi_agent_flow(
                query=user_message,
                course_id=effective_course_id,
                intent_type=intent_type,
                score_breakdown=breakdown,
                page_context=ctx_decision.effective_page_context,
                system_context=ctx_decision.effective_system_context,
            ):
                if isinstance(ev, AgentEvent):
                    yield ev
                else:
                    final_answer = ev

            await stm.append(session_id, "assistant", final_answer)
            multi_agent_refs = getattr(orchestrator, "collected_references", None) or []
            metadata = {
                "thinking": "Multi-agent orchestration executed successfully.",
                "toolActivities": [],
                "context": context_resolution.as_dict(),
                "references": multi_agent_refs,
                "model": getattr(orchestrator, "answered_model", None),
                "multiAgentLogs": orchestrator.multi_agent_logs,
                "critiqueReport": orchestrator.critique_report,
                "consolidation": orchestrator.consolidation,
                "spawningScore": orchestrator.spawning_score,
                "spawningBreakdown": orchestrator.spawning_breakdown,
                "orchestrationPlan": orchestrator.orchestration_plan,
            }
            saved_message_id = await message_store.save_message(
                session_id, "assistant", final_answer, metadata
            )

            try:
                from app.services.agent_telemetry_service import agent_telemetry_service
                await agent_telemetry_service.log_trace(
                    session_id=session_id,
                    turn_id=turn_id,
                    user_query=user_message,
                    spawning_score=orchestrator.spawning_score,
                    spawning_breakdown=orchestrator.spawning_breakdown,
                    consolidation=orchestrator.consolidation,
                    multi_agent_logs=orchestrator.multi_agent_logs,
                    critique_report=orchestrator.critique_report,
                    final_answer=final_answer,
                )
            except Exception as tel_err:
                logger.warning("Telemetry log failed (non-fatal): %s", tel_err)

            async for evt in _maybe_emit_title_update(
                session_id=session_id,
                user_message=user_message,
                turn_id=turn_id,
            ):
                yield evt

            # Draft text was already streamed token-by-token during the
            # pipeline; only fall back to a bulk emission if none of it
            # reached the user (e.g. drafting stream failed internally).
            if final_answer.strip() and not getattr(orchestrator, "streamed_to_user", False):
                yield AgentEvent(
                    type=AgentEventType.TEXT_DELTA,
                    data={"delta": final_answer},
                    session_id=session_id,
                    turn_id=turn_id,
                )
            yield AgentEvent(
                type=AgentEventType.DONE,
                data={
                    "text": final_answer,
                    "iterations": 1,
                    "intent": intent_type,
                    "model": getattr(orchestrator, "answered_model", None),
                    "references": multi_agent_refs or None,
                    "message_id": saved_message_id,
                },
                session_id=session_id,
                turn_id=turn_id,
            )
            await _trigger_post_turn_consolidation(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
                course_id=effective_course_id,
                intent_type=intent_type,
            )
            return

        except Exception as exc:
            logger.warning(
                "Multi-agent flow failed. Falling back to parent ReAct: %s", exc
            )
            # If part of the draft already reached the user, clear the bubble
            # so the fallback answer does not append to a half-written draft.
            if getattr(orchestrator, "streamed_to_user", False):
                yield AgentEvent(
                    type=AgentEventType.TEXT_RESET,
                    data={"reason": "multi_agent_fallback"},
                    session_id=session_id,
                    turn_id=turn_id,
                )
            yield AgentEvent(
                type=AgentEventType.THINKING,
                data={
                    "step": "multi_agent_fallback",
                    "detail": f"Sub-agent error: {str(exc)[:120]}. Falling back to standard generation.",
                },
                session_id=session_id,
                turn_id=turn_id,
            )

    if teacher_action_request:
        logger.info("Skipping prose-only multi-agent flow for teacher action request")

    # -- Step 3.7: GraphRAG pre-fetch (when graph expansion is signaled) --------
    # Fetch concept graph context BEFORE building the system prompt so the
    # LLM receives prerequisite and relationship signals from the first token.
    graph_context_text = ""
    _graph_expansion_needed = getattr(execution_plan, "graph_expansion_needed", False)
    _user_weakness_relevant = getattr(execution_plan, "user_weakness_relevant", False)

    if agent_type == "mentor" and _graph_expansion_needed:
        try:
            from app.core.config import get_settings as _get_settings
            _cfg = _get_settings()
            if _cfg.graphrag_enabled and _cfg.neo4j_enabled:
                from app.services.graphrag_service import graphrag_service
                from app.agents.core.context_formatter import graphrag_context_formatter

                _weak_node_ids: list[int] = []
                if _user_weakness_relevant:
                    try:
                        from app.agents.memory.ltm import ltm as _ltm
                        _weak_node_ids = await _ltm.get_weak_nodes(
                            user_id=user_id,
                            course_id=effective_course_id,
                            threshold=0.5,
                        )
                    except Exception:
                        pass

                _graph_ctx = await graphrag_service.retrieve(
                    query=user_message,
                    course_id=effective_course_id,
                    top_k=3,  # lightweight pre-fetch (tools will do deeper retrieval)
                    min_similarity=0.30,
                    expansion_enabled=True,
                    max_expansion_level="course",  # cap to avoid over-expansion at prompt level
                    user_id=user_id,
                    weak_node_ids=_weak_node_ids or None,
                )
                graph_context_text = graphrag_context_formatter.format(_graph_ctx)

                yield AgentEvent(
                    type=AgentEventType.THINKING,
                    data={
                        "step": "graphrag_prefetch",
                        "seed_nodes": _graph_ctx.seed_node_ids,
                        "expanded_nodes": len(_graph_ctx.expanded_node_ids),
                        "prereq_chain_len": len(_graph_ctx.prereq_chain),
                        "graph_expanded": _graph_ctx.graph_expanded,
                    },
                    session_id=session_id,
                    turn_id=turn_id,
                )
        except Exception as _exc:
            logger.warning("GraphRAG pre-fetch failed (non-fatal): %s", _exc)

    # -- Step 4: Build messages ------------------------------------------------
    # Authoring requests need a compact, tool-routing prompt. Full node lists
    # are only useful after the model has selected a quiz workflow and can be
    # fetched on demand; sending them on every turn causes TPM preflight errors.
    active_courses_section = (
        _format_compact_teacher_courses(active_courses)
        if teacher_action_request
        else format_active_courses_for_prompt(active_courses)
    )

    # Use ctx_decision.effective_* instead of raw page_context/system_context
    # When the user pivots, effective_page_context = None -> prevents context-lock

    # -- Lesson dossier: verified structure (course hierarchy, knowledge
    # nodes, prerequisites, chunk coverage) for the lesson on screen. This
    # is what lets the agent "know where it is" even for FILE/VIDEO lessons
    # that have no page text.
    lesson_context_text = ""
    _dossier_course_id = effective_course_id or context_resolution.course_id
    _dossier_content_id = None
    if ctx_decision.use_page_context and ctx_decision.effective_page_context:
        _pc = ctx_decision.effective_page_context
        _dossier_content_id = _as_positive_int(_pc.get("contentId") or _pc.get("content_id"))
    if _dossier_course_id and _dossier_content_id:
        try:
            _dossier = await load_lesson_dossier(
                course_id=int(_dossier_course_id),
                content_id=int(_dossier_content_id),
            )
            lesson_context_text = format_lesson_dossier(_dossier)
            if lesson_context_text:
                yield AgentEvent(
                    type=AgentEventType.THINKING,
                    data={"step": "lesson_dossier", "detail": f"course={_dossier_course_id} content={_dossier_content_id}"},
                    session_id=session_id,
                    turn_id=turn_id,
                )
        except Exception as _exc:  # noqa: BLE001 - dossier is best-effort
            logger.warning("Lesson dossier failed (non-fatal): %s", _exc)

    system_prompt = build_system_prompt(
        agent_type=agent_type,
        memory_context=memory_ctx["prompt_section"],
        user_context=user_context,
        active_courses_section=active_courses_section,
        page_context=ctx_decision.effective_page_context,
        system_context=ctx_decision.effective_system_context,
        graph_context=graph_context_text,
        lesson_context=lesson_context_text,
    )

    # Start with system prompt
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add STM history (filtered - only user/assistant/tool/clarification roles)
    for m in stm_history:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "clarification" and content:
            messages.append({"role": "assistant", "content": content})
        elif role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
        elif role == "tool" and content:
            messages.append({
                "role": "tool",
                "content": content,
                "tool_call_id": m.get("tool_call_id", "unknown"),
            })

    # If the user pivots and has a suggested_search_topic, add a hint to the message
    effective_message = effective_user_request
    if (
        ctx_decision.suggested_search_topic
        and not ctx_decision.use_page_context
    ):
        effective_message = (
            f"{effective_user_request}\n\n"
            f"[System hint: user appears to be asking about '{ctx_decision.suggested_search_topic}' "
            f"- search this topic cross-course if needed]"
        )
        logger.debug("Injected search topic hint: %s", ctx_decision.suggested_search_topic)

    messages.append({"role": "user", "content": effective_message})

    tool_schemas = get_tool_schemas(agent_type)
    assistant_text = ""
    assistant_thinking = ""
    answered_model: str | None = None
    ref_ledger = ReferenceLedger()
    assistant_metadata: dict = {
        "toolActivities": [],
        "references": [],
        # Persist the verified decision so reopened conversations explain the
        # scope they were grounded in, without retaining raw lesson content.
        "context": context_resolution.as_dict(),
    }

    # Dynamic max_tokens
    has_page_context = ctx_decision.use_page_context or ctx_decision.use_system_context
    max_tokens = _resolve_max_tokens(intent_type, has_page_context)
    logger.debug("Token budget: intent=%s has_page_ctx=%s max_tokens=%d",
                 intent_type, has_page_context, max_tokens)

    # -- Step 5: ReAct Iterations ----------------------------------------------
    final_text = ""

    for iteration in range(MAX_ITERATIONS):
        iter_start = time.monotonic()
        iter_id = f"{turn_id}-{iteration}"

        logger.debug("ReAct iteration %d/%d", iteration + 1, MAX_ITERATIONS)

        gateway = get_gateway()
        req = ChatRequest(
            task=TASK_AGENT_REACT,
            messages=messages,
            temperature=0.3,
            max_tokens=max_tokens,          # dynamic
            json_mode=False,
            extra={"tools": tool_schemas, "tool_choice": "auto"} if tool_schemas else {},
        )

        collected_text = ""
        collected_tool_calls: list[dict] = []
        parser = ThoughtStreamParser()      # instance per iteration

        try:
            async for delta_text, usage, chunk in gateway.stream(req):
                if answered_model is None:
                    chunk_model = (
                        chunk.get("model")
                        if isinstance(chunk, dict)
                        else getattr(chunk, "model", None)
                    )
                    if chunk_model:
                        answered_model = str(chunk_model)
                choices = _val(chunk, "choices")
                choice_0 = choices[0] if (choices and isinstance(choices, (list, tuple)) and len(choices) > 0) else None
                container = _val(choice_0, "delta") or _val(choice_0, "message") if choice_0 else None

                raw_text = delta_text or (_val(container, "content") if container and isinstance(_val(container, "content"), str) else "")
                if raw_text:
                    parsed_events = parser.feed(raw_text)
                    for ev_type, text_chunk in parsed_events:
                        if ev_type == "thought":
                            assistant_thinking += text_chunk
                            yield AgentEvent(
                                type=AgentEventType.THINKING,
                                data={"delta": text_chunk},
                                session_id=session_id,
                                turn_id=iter_id,
                            )
                        elif ev_type == "content":
                            collected_text += text_chunk
                            assistant_text += text_chunk
                            yield AgentEvent(
                                type=AgentEventType.TEXT_DELTA,
                                data={"delta": text_chunk},
                                session_id=session_id,
                                turn_id=iter_id,
                            )

                tool_calls = _val(container, "tool_calls") if container else None
                if tool_calls and isinstance(tool_calls, (list, tuple)):
                    for tc in tool_calls:
                        tc_idx = _val(tc, "index", 0)
                        while tc_idx >= len(collected_tool_calls):
                            collected_tool_calls.append({"id": "", "name": "", "arguments": ""})
                        entry = collected_tool_calls[tc_idx]
                        tc_id = _val(tc, "id")
                        if tc_id:
                            entry["id"] = tc_id
                        func = _val(tc, "function")
                        fn_name = _val(func, "name") if func else None
                        fn_args = _val(func, "arguments") if func else None
                        if fn_name:
                            entry["name"] = fn_name
                        if fn_args:
                            entry["arguments"] += fn_args

        except Exception as exc:
            err_str = str(exc)
            is_tool_validation = (
                "tool call validation failed" in err_str
                or "did not match schema" in err_str
            )
            if is_tool_validation and iteration < MAX_ITERATIONS - 1:
                logger.warning(
                    "Tool-call validation failed on iter %d; retrying. err=%s",
                    iteration + 1, err_str[:200],
                )
                yield AgentEvent(
                    type=AgentEventType.THINKING,
                    data={"step": "tool_retry", "detail": "adjusting tool arguments"},
                    session_id=session_id,
                    turn_id=turn_id,
                )
                messages.append({
                    "role": "system",
                    "content": (
                        "Your previous tool call was REJECTED by schema validation:\n"
                        f"  {err_str}\n"
                        "Fix your tool call or reply in natural language if no tool fits."
                    ),
                })
                continue
            else:
                logger.error("LLM stream failed: %s", err_str)
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": err_str, "iteration": iteration},
                    session_id=session_id,
                    turn_id=turn_id,
                )
                return

        for ev_type, text_chunk in parser.flush():
            if ev_type == "thought":
                assistant_thinking += text_chunk
                yield AgentEvent(
                    type=AgentEventType.THINKING,
                    data={"delta": text_chunk},
                    session_id=session_id,
                    turn_id=iter_id,
                )
            elif ev_type == "content":
                collected_text += text_chunk
                assistant_text += text_chunk
                yield AgentEvent(
                    type=AgentEventType.TEXT_DELTA,
                    data={"delta": text_chunk},
                    session_id=session_id,
                    turn_id=iter_id,
                )

        # Structured CoT log sau mỗi iteration
        full_thought = parser.get_full_thought()
        if full_thought:
            logger.info(
                "═══ CoT [session=%s iter=%d/%d len=%d] ═══\n%s\n═══ END CoT ═══",
                session_id[:8],
                iteration + 1,
                MAX_ITERATIONS,
                len(full_thought),
                full_thought,
            )
            yield AgentEvent(
                type=AgentEventType.THINKING,
                data={
                    "step": "cot_complete",
                    "iteration": iteration + 1,
                    "thought_length": len(full_thought),
                    "thought_preview": full_thought[:300],
                },
                session_id=session_id,
                turn_id=iter_id,
            )

        iter_ms = (time.monotonic() - iter_start) * 1000
        logger.debug(
            "Iteration %d: text=%d chars, tool_calls=%d (%.0fms)",
            iteration + 1, len(collected_text), len(collected_tool_calls), iter_ms,
        )

        # -- No tool calls -> done ----------------------------------------------
        if not collected_tool_calls:
            final_text = collected_text
            await stm.append(session_id, "assistant", collected_text)
            if assistant_thinking:
                assistant_metadata["thinking"] = assistant_thinking
            if ref_ledger:
                assistant_metadata["references"] = ref_ledger.references
            if answered_model:
                assistant_metadata["model"] = answered_model
            saved_message_id = await message_store.save_message(
                session_id, "assistant", assistant_text, assistant_metadata
            )
            async for evt in _maybe_emit_title_update(
                session_id=session_id,
                user_message=user_message,
                turn_id=turn_id,
            ):
                yield evt
            yield AgentEvent(
                type=AgentEventType.DONE,
                data={
                    "text": collected_text,
                    "iterations": iteration + 1,
                    "intent": intent_type,
                    "model": answered_model,
                    "references": ref_ledger.references if ref_ledger else None,
                    "message_id": saved_message_id,
                },
                session_id=session_id,
                turn_id=turn_id,
            )
            await _trigger_post_turn_consolidation(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
                course_id=effective_course_id,
                intent_type=intent_type,
            )
            return

        # -- Tool calls -> execute ----------------------------------------------
        assistant_msg: dict = {
            "role": "assistant",
            "content": collected_text or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in collected_tool_calls
                if tc["id"] and tc["name"]
            ],
        }
        messages.append(assistant_msg)

        for tc in collected_tool_calls:
            tool_name = tc["name"]
            if not tool_name:
                continue

            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                if args is None:
                    args = {}
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse tool args: name=%s, raw='%s'",
                    tool_name, tc["arguments"][:200],
                )
                args = None
            if args is not None and not isinstance(args, dict):
                args = None

            if args is None:
                # Malformed arguments must be fed back to the model as the
                # tool response - otherwise this tool_call_id dangles (strict
                # providers reject that) and the model never learns why.
                error_message = (
                    "Tool arguments were not valid JSON. Re-issue the same "
                    "tool call with a valid JSON object."
                )
                assistant_metadata["toolActivities"].append({
                    "tool": tool_name,
                    "status": "error",
                    "args": {},
                    "message": error_message,
                })
                yield AgentEvent(
                    type=AgentEventType.TOOL_RESULT,
                    data={
                        "tool": tool_name,
                        "status": "error",
                        "message": error_message,
                    },
                    session_id=session_id,
                    turn_id=iter_id,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"] or f"invalid-{tool_name}",
                    "content": json.dumps(
                        {"status": "error", "message": error_message},
                        ensure_ascii=False,
                    ),
                })
                continue

            assistant_metadata["toolActivities"].append({
                "tool": tool_name,
                "status": "running",
                "args": args,
            })
            yield AgentEvent(
                type=AgentEventType.TOOL_START,
                data={"tool": tool_name, "args": args},
                session_id=session_id,
                turn_id=iter_id,
            )

            logger.info("Executing tool: %s(%s)", tool_name, list(args.keys()))

            effective_content_id = None
            if ctx_decision.effective_page_context:
                effective_content_id = (
                    ctx_decision.effective_page_context.get("contentId")
                    or ctx_decision.effective_page_context.get("content_id")
                )

            effective_node_id = None
            if ctx_decision.effective_system_context:
                effective_node_id = (
                    ctx_decision.effective_system_context.get("nodeId")
                    or ctx_decision.effective_system_context.get("node_id")
                )

            tool_result = await execute_tool(
                name=tool_name,
                arguments=args,
                user_id=user_id,
                course_id=effective_course_id,
                session_id=session_id,
                content_id=effective_content_id,
                node_id=effective_node_id,
                execution_plan=execution_plan,
            )

            if tool_result.status == "success" and tool_result.data:
                # Harvest citations into a per-turn ledger with stable [n]
                # indices, then stamp those indices back onto the chunk dicts
                # BEFORE serialisation so the model can cite them precisely.
                harvested_chunks: list[dict] | None = None
                if tool_name in ("search_course_materials", "explain_concept"):
                    harvested_chunks = tool_result.data.get("chunks") or []
                elif tool_name == "search_web":
                    harvested_chunks = tool_result.data.get("results") or []

                if harvested_chunks:
                    is_web = tool_name == "search_web"
                    for ch in harvested_chunks:
                        if not isinstance(ch, dict):
                            continue
                        if is_web:
                            ref = {
                                "title": ch.get("title") or "Kết quả Web",
                                "content": (ch.get("snippet") or "")[:600],
                                "relevance_score": float(
                                    ch.get("relevance_score") or 1.0
                                ),
                                "source_type": "web",
                                "url": ch.get("url"),
                            }
                        else:
                            ref = {
                                "title": ch.get("title") or "Tài liệu khóa học",
                                "content": (ch.get("text") or "")[:600],
                                "relevance_score": float(
                                    ch.get("similarity") or 0.0
                                ),
                                "source_type": "material",
                                "page_number": ch.get("page_number"),
                                "content_id": ch.get("content_id"),
                                "node_id": ch.get("node_id"),
                            }
                        ch["ref"] = ref_ledger.add(ref)

            if tool_result.ui_instruction:
                # HITL owns rendering of its actionable widget. Emitting it a
                # second time would duplicate that one component in the client.
                if tool_result.status != "pending_human_approval":
                    assistant_metadata.setdefault("uiComponents", []).append(tool_result.ui_instruction)
                    yield AgentEvent(
                        type=AgentEventType.UI_COMPONENT,
                        data=tool_result.ui_instruction,
                        session_id=session_id,
                        turn_id=iter_id,
                    )

            if tool_result.status == "pending_human_approval":
                assistant_metadata["hitlRequest"] = {
                    "tool": tool_name,
                    "message": tool_result.message,
                    "data": tool_result.data,
                    "ui_instruction": tool_result.ui_instruction,
                }
                yield AgentEvent(
                    type=AgentEventType.HITL_REQUEST,
                    data={
                        "tool": tool_name,
                        "message": tool_result.message,
                        "data": tool_result.data,
                        "ui_instruction": tool_result.ui_instruction,
                    },
                    session_id=session_id,
                    turn_id=iter_id,
                )

            for t in assistant_metadata["toolActivities"]:
                if t["tool"] == tool_name and t["status"] == "running":
                    t["status"] = "done" if tool_result.status != "error" else "error"
                    t["message"] = tool_result.message

            yield AgentEvent(
                type=AgentEventType.TOOL_RESULT,
                data={
                    "tool": tool_name,
                    "status": tool_result.status,
                    "message": tool_result.message,
                },
                session_id=session_id,
                turn_id=iter_id,
            )

            await _update_anchor_from_tool(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
                tool_name=tool_name,
                args=args,
                tool_result=tool_result,
            )

            if tool_result.status == "pending_human_approval":
                logger.info("HITL break: tool=%s", tool_name)
                await stm.append(session_id, "assistant", tool_result.message)
                if assistant_thinking:
                    assistant_metadata["thinking"] = assistant_thinking
                if ref_ledger:
                    assistant_metadata["references"] = ref_ledger.references
                if answered_model:
                    assistant_metadata["model"] = answered_model
                saved_message_id = await message_store.save_message(
                    session_id, "assistant", assistant_text, assistant_metadata
                )
                async for evt in _maybe_emit_title_update(
                    session_id=session_id,
                    user_message=user_message,
                    turn_id=turn_id,
                ):
                    yield evt
                yield AgentEvent(
                    type=AgentEventType.DONE,
                    data={
                        "text": tool_result.message,
                        "iterations": iteration + 1,
                        "reason": "hitl_pending",
                        "model": answered_model,
                        "references": ref_ledger.references if ref_ledger else None,
                        "message_id": saved_message_id,
                    },
                    session_id=session_id,
                    turn_id=turn_id,
                )
                await _trigger_post_turn_consolidation(
                    session_id=session_id,
                    user_id=user_id,
                    agent_type=agent_type,
                    course_id=effective_course_id,
                    intent_type=intent_type,
                )
                return

            # Smart truncation instead of a hard 3000-character limit
            result_summary = {
                "status": tool_result.status,
                "message": tool_result.message,
                "data": tool_result.data,
            }
            result_content = json.dumps(
                result_summary, ensure_ascii=False, default=str,
            )
            result_content = _smart_truncate_tool_result(
                tool_name, result_content, limit=4000
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_content,
            })

            logger.info(
                "Tool result: %s -> %s (%d chars)",
                tool_name, tool_result.status, len(result_content),
            )

    # -- Max iterations reached ------------------------------------------------
    logger.warning("ReAct max iterations reached: session=%s", session_id[:8])

    if ref_ledger:
        assistant_metadata["references"] = ref_ledger.references
    if answered_model:
        assistant_metadata["model"] = answered_model
    assistant_metadata["incomplete"] = True

    yield AgentEvent(
        type=AgentEventType.THINKING,
        data={
            "step": "turn_incomplete",
            "detail": (
                "Turn hit the processing limit before full completion."
                if assistant_text.strip()
                else "No final answer was produced within the iteration budget."
            ),
        },
        session_id=session_id,
        turn_id=turn_id,
    )

    if assistant_text.strip():
        # Keep the partial answer the user already saw intact - never append
        # a canned apology to streamed content. Flag it via metadata instead.
        await stm.append(session_id, "assistant", assistant_text)
        saved_message_id = await message_store.save_message(
            session_id, "assistant", assistant_text, assistant_metadata
        )
        fallback = assistant_text
    else:
        fallback = (
            "Tôi đã thực hiện nhiều bước nhưng chưa hoàn tất. "
            "Bạn có thể thử lại với yêu cầu cụ thể hơn không?"
        )
        await stm.append(session_id, "assistant", fallback)
        saved_message_id = await message_store.save_message(
            session_id, "assistant", fallback, assistant_metadata
        )
        yield AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"delta": fallback},
            session_id=session_id,
            turn_id=turn_id,
        )

    yield AgentEvent(
        type=AgentEventType.DONE,
        data={
            "text": fallback,
            "iterations": MAX_ITERATIONS,
            "reason": "max_iterations",
            "incomplete": True,
            "model": answered_model,
            "references": ref_ledger.references if ref_ledger else None,
            "message_id": saved_message_id,
        },
        session_id=session_id,
        turn_id=turn_id,
    )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

async def _update_anchor_from_tool(
    session_id: str,
    user_id: int,
    agent_type: str,
    tool_name: str,
    args: dict,
    tool_result: "ToolResult",  # noqa: F821 - runtime type
) -> None:
    """Pin MTM anchor from tool result — unchanged."""
    try:
        if tool_result.status not in ("success",):
            return
        cid = args.get("course_id") or (tool_result.data or {}).get("course_id")
        nid = args.get("node_id") or (tool_result.data or {}).get("node_id")
        if cid:
            await mtm.update_anchor(session_id, course_id=int(cid), node_id=nid)
    except Exception as exc:
        logger.debug("anchor update skipped: %s", exc)


async def _maybe_emit_title_update(
    session_id: str,
    user_message: str,
    turn_id: str,
) -> AsyncIterator[AgentEvent]:
    """Emit title update event on first turn — unchanged."""
    try:
        existing = await mtm.get_title(session_id)
        if existing:
            return
        from app.core.llm import chat_complete
        from app.core.llm_gateway import TASK_AGENT_ROUTER
        title_resp = await chat_complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a short 3-5 word conversation title in the same "
                        "language as the user message. No punctuation. Plain text only."
                    ),
                },
                {"role": "user", "content": user_message[:200]},
            ],
            model=settings.chat_model,
            max_tokens=24,
            temperature=0.3,
            task=TASK_AGENT_ROUTER,
        )
        title = (title_resp or "").strip().strip('"').strip("'")
        if title:
            await mtm.update_title(session_id, title)
            yield AgentEvent(
                type=AgentEventType.TITLE_UPDATE,
                data={"title": title},
                session_id=session_id,
                turn_id=turn_id,
            )
    except Exception as exc:
        logger.debug("title generation failed (non-fatal): %s", exc)


async def _trigger_post_turn_consolidation(
    session_id: str,
    user_id: int,
    agent_type: str,
    course_id: int | None,
    intent_type: str,
) -> None:
    """
    Increments turn count in MTM. If turn_count is a multiple of 10,
    publishes CONSOLIDATE_SESSION request to Kafka.
    """
    try:
        msgs = await stm.get_messages(session_id)
        if len(msgs) > 0 and len(msgs) % 10 == 0:
            logger.info("Triggering MTM consolidation at %d messages", len(msgs))
            from app.agents.memory.mtm import mtm
            await mtm.consolidate(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
                course_id=course_id,
                intent_type=intent_type,
            )
    except Exception as exc:
        logger.debug("post-turn consolidation skipped: %s", exc)
