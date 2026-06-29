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
from app.agents.core.prompts import build_system_prompt
from app.agents.core.scope_resolver import (
    apply_scope_to_course_id,
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


# -----------------------------------------------------------------------------
# [PATCH 1] Dynamic max_tokens
# -----------------------------------------------------------------------------

def _resolve_max_tokens(intent_type: str, has_page_context: bool) -> int:
    """
    Allocate the token budget for the LLM based on the expected complexity of the response.

    Instead of a hardcoded 2048 for all cases, the budget is adjusted according to the intent:
    - content_creation / interactive_exercise: needs long generation -> 4096
    - knowledge_question + page_context (currently studying a lesson): requires deep explanation -> 3500
    - standard knowledge_question: -> 3000
    - progress_advice: -> 2500
    - general_chat / fallback: -> 2048
    """
    if intent_type in ("content_creation", "interactive_exercise"):
        return 4096
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

        if tool_name == "search_course_materials":
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

    execution_plan = await generate_plan(
        user_message=user_message,
        active_courses=active_courses,
        agent_type=agent_type,
        current_course_id=course_id,
        page_context=page_context,
        system_context=system_context,
        history=history_turns,
    )

    router_output = await classify_intent(
        user_message=user_message,
        active_courses=active_courses,
        agent_type=agent_type,
        current_course_id=course_id,
        page_context=page_context,
    )
    
    intent_type = execution_plan.user_intent

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

    focus_course_id = course_id
    if not focus_course_id and page_context:
        focus_course_id = page_context.get("courseId") or page_context.get("course_id")
    if not focus_course_id and system_context:
        focus_course_id = system_context.get("course_id") or system_context.get("courseId")

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
        query=user_message,
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
                    user_message=user_message,
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
        user_message=user_message,
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

    if score >= 0.45:
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
            metadata = {
                "thinking": "Multi-agent orchestration executed successfully.",
                "toolActivities": [],
                "multiAgentLogs": orchestrator.multi_agent_logs,
                "critiqueReport": orchestrator.critique_report,
                "consolidation": orchestrator.consolidation,
                "spawningScore": orchestrator.spawning_score,
                "spawningBreakdown": orchestrator.spawning_breakdown,
            }
            await message_store.save_message(
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
                    "references": None,
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
            yield AgentEvent(
                type=AgentEventType.THINKING,
                data={
                    "step": "multi_agent_fallback",
                    "detail": f"Sub-agent error: {str(exc)[:120]}. Falling back to standard generation.",
                },
                session_id=session_id,
                turn_id=turn_id,
            )

    # -- Step 4: Build messages ------------------------------------------------
    active_courses_section = format_active_courses_for_prompt(active_courses)

    # Use ctx_decision.effective_* instead of raw page_context/system_context
    # When the user pivots, effective_page_context = None -> prevents context-lock
    system_prompt = build_system_prompt(
        agent_type=agent_type,
        memory_context=memory_ctx["prompt_section"],
        user_context=user_context,
        active_courses_section=active_courses_section,
        page_context=ctx_decision.effective_page_context,
        system_context=ctx_decision.effective_system_context,
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
    effective_message = user_message
    if (
        ctx_decision.suggested_search_topic
        and not ctx_decision.use_page_context
    ):
        effective_message = (
            f"{user_message}\n\n"
            f"[System hint: user appears to be asking about '{ctx_decision.suggested_search_topic}' "
            f"- search this topic cross-course if needed]"
        )
        logger.debug("Injected search topic hint: %s", ctx_decision.suggested_search_topic)

    messages.append({"role": "user", "content": effective_message})

    tool_schemas = get_tool_schemas(agent_type)
    assistant_text = ""
    assistant_thinking = ""
    turn_references = []
    assistant_metadata: dict = {"toolActivities": [], "references": []}

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
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue

                if delta_text:
                    parsed_events = parser.feed(delta_text)
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

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        while tc.index >= len(collected_tool_calls):
                            collected_tool_calls.append({"id": "", "name": "", "arguments": ""})
                        entry = collected_tool_calls[tc.index]
                        if tc.id:
                            entry["id"] = tc.id
                        if tc.function and tc.function.name:
                            entry["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            entry["arguments"] += tc.function.arguments

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
            if turn_references:
                assistant_metadata["references"] = turn_references
            await message_store.save_message(
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
                    "references": turn_references if turn_references else None,
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
                args = {}
            if not isinstance(args, dict):
                args = {}

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
                if tool_name == "search_course_materials":
                    chunks = tool_result.data.get("chunks") or []
                    for ch in chunks:
                        turn_references.append({
                            "title": ch.get("title") or "Tài liệu khóa học",
                            "content": ch.get("text") or "",
                            "relevance_score": ch.get("similarity") or 0.0,
                            "source_type": "material",
                            "page_number": ch.get("page_number"),
                        })
                elif tool_name == "search_web":
                    web_results = tool_result.data.get("results") or []
                    for wr in web_results:
                        turn_references.append({
                            "title": wr.get("title") or "Kết quả Web",
                            "content": wr.get("snippet") or "",
                            "relevance_score": 1.0,
                            "source_type": "web",
                            "url": wr.get("url"),
                        })

            if tool_result.ui_instruction:
                assistant_metadata["uiComponent"] = tool_result.ui_instruction
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
                if turn_references:
                    assistant_metadata["references"] = turn_references
                await message_store.save_message(
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
    fallback = (
        "Tôi đã thực hiện nhiều bước nhưng chưa hoàn tất. "
        "Bạn có thể thử lại với yêu cầu cụ thể hơn không?"
    )
    await stm.append(session_id, "assistant", fallback)
    await message_store.save_message(
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
        data={"text": fallback, "iterations": MAX_ITERATIONS, "reason": "max_iterations"},
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
        existing = await message_store.get_conversation_title(session_id)
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
            await message_store.set_conversation_title(session_id, title)
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