"""
ai-service/app/agents/core/react_loop.py

ReAct Loop — the central reasoning engine for both agents.

This is the CORE of the entire multi-agent system. It orchestrates:
  1. Intent classification (Router)
  2. Memory assembly (ContextBuilder)
  3. Clarification gating
  4. Iterative Reason+Act loop with Groq streaming
  5. Tool execution via the Registry
  6. STM persistence and MTM compression triggers

Flow diagram:

  User message
      │
      ▼
  ┌────────────────┐
  │ classify_intent│ ← fast LLM (8b)
  └──────┬─────────┘
         ▼
  ┌───────────────────┐
  │ context_builder   │ ← weighted memory fetch
  │  .build(intent)   │
  └──────┬────────────┘
         ▼
  ┌───────────────────┐
  │ should_clarify?   │ ← fast LLM check
  │  confidence < 0.7 │──yes──▶ yield CLARIFICATION → return
  └──────┬────────────┘
         │ no
         ▼
  ┌─────────────────────────────────────────┐
  │ for iteration in range(MAX_ITERATIONS): │
  │   1. Groq streaming (70b + tools)       │
  │   2. If text only → yield deltas → DONE │
  │   3. If tool_calls:                     │
  │      a. yield TOOL_START                │
  │      b. execute_tool()                  │
  │      c. yield TOOL_RESULT / UI          │
  │      d. append tool result to messages  │
  │      e. loop back to step 1             │
  └─────────────────────────────────────────┘
         │
         ▼
  ┌───────────────────┐
  │ Post-turn:        │
  │  - Save to STM    │
  │  - Check compress │
  │  - Trigger MTM    │
  └───────────────────┘

Max iterations: 5 (prevents infinite tool-calling loops)
Model: quiz_model (llama-3.3-70b-versatile) for reasoning quality
Streaming: Groq native streaming with tool_calls collection
"""
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
from app.agents.core.router import classify_intent
from app.agents.core.clarification import (
    build_scope_clarification,
    should_clarify,
)
from app.agents.core.prompts import build_system_prompt
from app.agents.core.scope_resolver import (
    apply_scope_to_course_id,
    resolve_course_scope,
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
                    suffix = self.buffer[-i:]
                    if end_tag.startswith(suffix):
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
            if self.tag_checked:
                if self.buffer:
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1.5: Load active courses
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    active_courses = await load_active_courses(
        user_id=user_id,
        agent_type=agent_type,
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1: Classify intent (fast — structured)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    router_output = await classify_intent(
        user_message=user_message,
        active_courses=active_courses,
        agent_type=agent_type,
    )
    intent_type = router_output.intent

    yield AgentEvent(
        type=AgentEventType.THINKING,
        data={"step": "intent", "intent": intent_type},
        session_id=session_id,
        turn_id=turn_id,
    )

    logger.debug("Intent classified: %s (%.0fms)",
                 intent_type, (time.monotonic() - start_time) * 1000)

    # Read the prior MTM anchor (current_course_id, etc.) so the scope
    # resolver can recognise deictic references.
    prior_mtm_ctx = await mtm.get_context(session_id)

    scope = await resolve_course_scope(
        user_message=user_message,
        active_courses=active_courses,
        mtm_ctx=prior_mtm_ctx,
        explicit_course_id=course_id,
        router_matched_course_id=router_output.matched_course_id,
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
    # courses MRU list as well — useful when the user bounces between
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2: Assemble weighted context from all memory tiers
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    memory_ctx = await context_builder.build(
        user_id=user_id,
        session_id=session_id,
        agent_type=agent_type,
        query=user_message,
        course_id=effective_course_id,
        intent_type=intent_type,
        scope_course_ids=scope.candidate_course_ids or None,
        page_context=page_context,
        system_context=system_context,
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3: Clarification Gate (scope first, then parameter)
    #
    # Two distinct flows:
    #   (a) SCOPE — the scope resolver flagged genuine ambiguity about
    #       which course this applies to. Cheap, deterministic.
    #   (b) PARAMETER — an action-tool needs user-only input
    #       (difficulty, count, …). LLM-assisted, low-confidence only.
    #
    # We dropped the old intent-based skip-list (content_creation,
    # interactive_exercise, progress_advice). Those intents are exactly
    # where the wrong-course problem hurts most — silent guessing led to
    # quizzes for the wrong course / wrong topic. Now we trust the scope
    # resolver to keep the parameter clarifier from firing on already-
    # answered questions, and we cap total clarifications per session.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    stm_history = memory_ctx["stm_messages"]
    clarify_count = sum(
        1 for m in stm_history if m.get("role") == "clarification"
    )

    if clarify_count < MAX_CLARIFICATIONS_PER_SESSION:
        # (a) Scope clarification — runs first, no LLM call.
        scope_clarify = build_scope_clarification(scope)

        # (b) Router clarification — runs if router flagged ambiguity (e.g., vague request, missing params)
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

        # (c) Parameter clarification — fallback if both scope and router are clean.
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

            # Save to STM
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3.5: Multi-Agent Spawning Decision & Flow
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator
    
    parent_context_length = memory_ctx.get("token_estimate", 0) + len(user_message) // 4
    orchestrator = MultiAgentOrchestrator(session_id, turn_id)
    score, breakdown = orchestrator.calculate_spawning_score(
        user_message=user_message,
        intent_type=intent_type,
        parent_context_length=parent_context_length
    )
    
    yield AgentEvent(
        type=AgentEventType.THINKING,
        data={
            "step": "multi_agent_decision",
            "score": score,
            "breakdown": breakdown
        },
        session_id=session_id,
        turn_id=turn_id,
    )
    
    if score >= 0.5:
        logger.info("Spawning multi-agent flow: score=%s >= 0.5", score)
        try:
            final_answer = ""
            async for ev in orchestrator.run_multi_agent_flow(
                query=user_message,
                course_id=effective_course_id,
                intent_type=intent_type,
                score_breakdown=breakdown,
                page_context=page_context,
                system_context=system_context,
            ):
                if isinstance(ev, AgentEvent):
                    yield ev
                else:
                    final_answer = ev
            
            # Save assistant response to STM and persistent store
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

            # Log full telemetry trace for future training/tuning datasets
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
                    final_answer=final_answer
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
            logger.warning("Multi-agent flow failed. Falling back to parent ReAct loop: %s", exc)
            yield AgentEvent(
                type=AgentEventType.THINKING,
                data={
                    "step": "multi_agent_fallback",
                    "detail": f"Sub-agent error detected: {str(exc)}. Falling back to standard generation."
                },
                session_id=session_id,
                turn_id=turn_id,
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 4: Build messages array for the LLM
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Ground-truth anchor: real list of (course_id, [node_id]) the user
    # actually has access to. Same shape for teacher and mentor; the LLM
    # has nothing to fabricate.
    active_courses_section = format_active_courses_for_prompt(active_courses)

    system_prompt = build_system_prompt(
        agent_type=agent_type,
        memory_context=memory_ctx["prompt_section"],
        user_context=user_context,
        active_courses_section=active_courses_section,
        page_context=page_context,
        system_context=system_context,
    )

    # Start with system prompt
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add STM history (filtered — only user/assistant/tool/clarification roles)
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

    # Add the current user message
    messages.append({"role": "user", "content": user_message})

    # Get tool schemas for this agent
    tool_schemas = get_tool_schemas(agent_type)

    # Track assistant message across iterations for persistent storage
    assistant_text = ""
    assistant_thinking = ""
    turn_references = []
    assistant_metadata: dict = {"toolActivities": [], "references": []}


    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 5: ReAct Iterations
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    final_text = ""

    for iteration in range(MAX_ITERATIONS):
        iter_start = time.monotonic()
        iter_id = f"{turn_id}-{iteration}"

        logger.debug("ReAct iteration %d/%d", iteration + 1, MAX_ITERATIONS)

        # ── 5a. Call LLMGateway with streaming ───────────────────────────────
        gateway = get_gateway()
        req = ChatRequest(
            task=TASK_AGENT_REACT,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
            extra={"tools": tool_schemas, "tool_choice": "auto"} if tool_schemas else {},
        )

        # ── 5b. Collect streaming response ───────────────────────────────────
        collected_text = ""
        collected_tool_calls: list[dict] = []
        parser = ThoughtStreamParser()

        try:
            async for delta_text, usage, chunk in gateway.stream(req):
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta is None:
                    continue

                # Stream text deltas to frontend
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

                # Collect tool calls (streamed incrementally)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        # Extend the list if needed
                        while tc.index >= len(collected_tool_calls):
                            collected_tool_calls.append({
                                "id": "",
                                "name": "",
                                "arguments": "",
                            })

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
                    "Tool-call validation failed on iter %d; asking LLM to "
                    "retry with a valid schema. err=%s",
                    iteration + 1, err_str[:200],
                )
                yield AgentEvent(
                    type=AgentEventType.THINKING,
                    data={
                        "step": "tool_retry",
                        "detail": "adjusting tool arguments",
                    },
                    session_id=session_id,
                    turn_id=turn_id,
                )
                # Append a system-style nudge so the next streaming call
                # steers the model toward a valid call (or a text answer).
                messages.append({
                    "role": "system",
                    "content": (
                        "Your previous tool call was REJECTED by schema "
                        "validation with this error:\n"
                        f"  {err_str}\n"
                        "Fix your tool call:\n"
                        "- Use ONLY the enum values listed in the tool "
                        "schema.\n"
                        "- If you wanted to create a quiz/test/questions, "
                        "call `generate_quiz_draft` (NOT "
                        "`generate_content_draft`).\n"
                        "- `generate_content_draft.content_type` MUST be "
                        "one of: outline, summary, slide_structure, "
                        "lesson_plan, explanation.\n"
                        "- If you are missing a required ID (course_id, "
                        "node_id), call the corresponding `list_*` tool "
                        "first.\n"
                        "Retry now with a corrected call, or reply in "
                        "natural language if no tool fits."
                    ),
                })
                # Drop any partial collected state and retry the iteration.
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

        # Flush any remaining tokens inside parser buffer
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

        iter_ms = (time.monotonic() - iter_start) * 1000
        logger.debug(
            "Iteration %d: text=%d chars, tool_calls=%d (%.0fms)",
            iteration + 1, len(collected_text),
            len(collected_tool_calls), iter_ms,
        )

        # ── 5c. NO tool calls → text response → DONE ────────────────────────
        if not collected_tool_calls:
            final_text = collected_text

            # Save assistant response to STM
            await stm.append(session_id, "assistant", collected_text)

            # Save full assistant response to persistent store BEFORE title gen
            # so the first-turn check sees consistent state.
            if assistant_thinking:
                assistant_metadata["thinking"] = assistant_thinking
            if turn_references:
                assistant_metadata["references"] = turn_references

            await message_store.save_message(
                session_id, "assistant", assistant_text, assistant_metadata
            )
 
            # Title generation runs inline on the first completed turn so we
            # can stream a `title_update` event to the frontend before DONE.
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
 
            # Post-turn: trigger background consolidation if needed
            await _trigger_post_turn_consolidation(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
                course_id=effective_course_id,
                intent_type=intent_type,
            )
            return

        # ── 5d. TOOL CALLS → execute and loop ───────────────────────────────
        # Add assistant message with tool_calls to the conversation
        assistant_msg: dict = {
            "role": "assistant",
            "content": collected_text or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in collected_tool_calls
                if tc["id"] and tc["name"]  # skip incomplete tool calls
            ],
        }
        messages.append(assistant_msg)

        # Execute each tool call
        for tc in collected_tool_calls:
            tool_name = tc["name"]
            if not tool_name:
                continue

            # Parse arguments
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
            # Models sometimes emit "null" (or a bare value) for a no-arg tool;
            # json.loads then returns None / a non-dict, and .keys() explodes.
            if not isinstance(args, dict):
                args = {}

            # ── Yield TOOL_START ─────────────────────────────────────────
            assistant_metadata["toolActivities"].append({
                "tool": tool_name,
                "status": "running",
                "args": args
            })
            yield AgentEvent(
                type=AgentEventType.TOOL_START,
                data={"tool": tool_name, "args": args},
                session_id=session_id,
                turn_id=iter_id,
            )

            logger.info("Executing tool: %s(%s)", tool_name, list(args.keys()))

            # Extract content_id and node_id from page_context or system_context if present
            loop_content_id = None
            loop_node_id = None
            if page_context:
                loop_content_id = page_context.get("contentId") or page_context.get("content_id")
                loop_node_id = page_context.get("nodeId") or page_context.get("node_id")
            if not loop_content_id and system_context:
                loop_content_id = system_context.get("lesson_id") or system_context.get("content_id")
            if not loop_node_id and system_context:
                loop_node_id = system_context.get("node_id")

            # Safely cast to int
            try:
                if loop_content_id is not None:
                    loop_content_id = int(loop_content_id)
            except (ValueError, TypeError):
                loop_content_id = None

            try:
                if loop_node_id is not None:
                    loop_node_id = int(loop_node_id)
            except (ValueError, TypeError):
                loop_node_id = None

            tool_result = await execute_tool(
                name=tool_name,
                arguments=args,
                user_id=user_id,
                course_id=effective_course_id,
                session_id=session_id,
                content_id=loop_content_id,
                node_id=loop_node_id,
            )

            # Extract references from successful search tools
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
                            "content_id": ch.get("content_id")
                        })
                elif tool_name == "search_web":
                    web_results = tool_result.data.get("results") or []
                    for wr in web_results:
                        turn_references.append({
                            "title": wr.get("title") or "Kết quả Web",
                            "content": wr.get("snippet") or "",
                            "relevance_score": 1.0,
                            "source_type": "web",
                            "url": wr.get("url")
                        })

            # ── Yield UI component if present ────────────────────────────
            if tool_result.ui_instruction:
                assistant_metadata["uiComponent"] = tool_result.ui_instruction
                yield AgentEvent(
                    type=AgentEventType.UI_COMPONENT,
                    data=tool_result.ui_instruction,
                    session_id=session_id,
                    turn_id=iter_id,
                )

            # ── Yield HITL if pending approval ───────────────────────────
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

            # ── Yield TOOL_RESULT ────────────────────────────────────────
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

            # ── Pin working-memory anchor from this tool result ──────
            # Both agents benefit from anchor pinning — mentor uses it to
            # remember which course the student last asked about, teacher
            # uses it for "this quiz / this node" deictic resolution.
            await _update_anchor_from_tool(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
                tool_name=tool_name,
                args=args,
                tool_result=tool_result,
            )

            # ── HITL early exit: stop the loop and let the widget
            #    be the primary response. No further LLM iteration
            #    needed — the teacher reviews via the widget. ─────────
            if tool_result.status == "pending_human_approval":
                logger.info(
                    "HITL break: tool=%s, stopping ReAct loop",
                    tool_name,
                )
                # Save a concise assistant summary to STM
                await stm.append(
                    session_id, "assistant", tool_result.message,
                )
                # Save full assistant state to persistent store
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

            # ── Add tool result to messages for next LLM iteration ───────
            result_summary = {
                "status": tool_result.status,
                "message": tool_result.message,
                "data": tool_result.data,
            }
            result_content = json.dumps(
                result_summary,
                ensure_ascii=False,
                default=str,
            )
            # Truncate very large tool results to save tokens
            if len(result_content) > 3000:
                result_content = result_content[:3000] + '..."}'

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_content,
            })

            logger.info(
                "Tool result: %s → %s (%d chars)",
                tool_name, tool_result.status, len(result_content),
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Max iterations reached — should rarely happen
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.warning("ReAct max iterations reached: session=%s", session_id[:8])

    fallback = (
        "Tôi đã thực hiện nhiều bước nhưng chưa hoàn tất. "
        "Bạn có thể thử lại với yêu cầu cụ thể hơn không?"
    )
    await stm.append(session_id, "assistant", fallback)
    await message_store.save_message(session_id, "assistant", fallback, assistant_metadata)

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
        },
        session_id=session_id,
        turn_id=turn_id,
    )

    total_ms = (time.monotonic() - start_time) * 1000
    logger.info("ReAct finished: session=%s, %.0fms", session_id[:8], total_ms)

    await _trigger_post_turn_consolidation(
        session_id=session_id,
        user_id=user_id,
        agent_type=agent_type,
        course_id=effective_course_id,
        intent_type=intent_type,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Working-memory anchor helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 
# Tools whose successful output pins mutation of the teacher anchor cache.
_ANCHOR_INVALIDATING_TOOLS = {
    "create_section",
    "trigger_auto_index",
}
 
 
async def _update_anchor_from_tool(
    session_id: str,
    user_id: int,
    agent_type: str,
    tool_name: str,
    args: dict,
    tool_result: "ToolResult",  # noqa: F821 — runtime type
) -> None:
    """
    Pin concrete (course_id, node_id, topic) values surfaced by a tool
    into MTM key_facts so the NEXT turn's system prompt shows a
    CURRENT ANCHOR. This is what lets "cái này / vấn đề này" resolve
    without the LLM having to guess.

    Also invalidates the active_courses cache when a tool mutates the
    course structure so the fresh data appears on the next turn.
    """
    status = getattr(tool_result, "status", None)
    if status not in ("success", "pending_human_approval"):
        return
 
    data = getattr(tool_result, "data", None)
    if not isinstance(data, dict):
        data = {}
 
    updates: dict = {}
 
    if tool_name == "list_my_courses":
        courses = data.get("courses") or []
        if len(courses) == 1 and courses[0].get("id") is not None:
            updates["current_course_id"] = courses[0]["id"]
 
    elif tool_name == "list_knowledge_nodes":
        nodes = data.get("nodes") or []
        cid = args.get("course_id")
        if cid:
            updates["current_course_id"] = cid
        # Pin the node only when the result is unambiguous
        # (exact-match search → single node).
        if len(nodes) == 1:
            n = nodes[0]
            if n.get("id") is not None:
                updates["current_node_id"] = n["id"]
            topic = n.get("name_vi") or n.get("name")
            if topic:
                updates["current_topic"] = topic
 
    elif tool_name in ("generate_quiz_draft", "generate_content_draft"):
        cid = data.get("course_id") or args.get("course_id")
        nid = data.get("node_id") or args.get("node_id")
        topic = data.get("topic") or args.get("topic")
        if cid is not None:
            updates["current_course_id"] = cid
        if nid is not None:
            updates["current_node_id"] = nid
        if topic:
            updates["current_topic"] = topic
 
    if tool_name in _ANCHOR_INVALIDATING_TOOLS:
        invalidate_active_courses(user_id)
 
    if not updates:
        return
 
    try:
        await mtm.update_key_facts(session_id, updates)
    except Exception as exc:  # noqa: BLE001 — anchor update must never break the turn
        logger.warning(
            "anchor update failed: session=%s, tool=%s, err=%s",
            session_id[:8], tool_name, exc,
        )



async def _maybe_emit_title_update(
    session_id: str,
    user_message: str,
    turn_id: str,
) -> AsyncIterator[AgentEvent]:
    """
    If the session has no title yet, generate one and yield a TITLE_UPDATE
    event so the sidebar can refresh in realtime. Silent on failure — the
    session just stays untitled.
    """
    try:
        existing_title = await mtm.get_title(session_id)
        if existing_title:
            return
 
        title = await _generate_session_title(user_message)
        if not title:
            return
 
        await mtm.update_title(session_id, title)
        logger.info("Session %s titled: %s", session_id[:8], title)
 
        yield AgentEvent(
            type=AgentEventType.TITLE_UPDATE,
            data={"title": title},
            session_id=session_id,
            turn_id=turn_id,
        )
    except Exception as exc:
        logger.warning("Title generation failed (non-fatal): %s", exc)
 
 
async def _generate_session_title(first_message: str) -> str | None:
    """
    Ask the fast chat model for a short, human-readable chat title.
 
    Returns the cleaned title string, or None on failure.
    """
    from app.core.llm import chat_complete
    from app.core.llm_gateway import TASK_CHAT

    prompt = (
        "Tạo một tiêu đề ngắn gọn (3-6 từ, tối đa 50 ký tự) tóm tắt cuộc hội "
        "thoại dựa trên tin nhắn đầu tiên. "
        "Giữ nguyên ngôn ngữ của tin nhắn. "
        "Không dùng ngoặc kép, không thêm dấu chấm, không thêm tiền tố như "
        "\"Tiêu đề:\". Chỉ trả về tiêu đề.\n\n"
        f"Tin nhắn: {first_message[:500]}"
    )

    try:
        content = await chat_complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=24,
            temperature=0.3,
            task=TASK_CHAT,
        )
        if not content:
            return None
        title = content.strip()
    except Exception as exc:
        logger.warning("Title generation LLM call failed: %s", exc)
        return None
    # Strip common junk: quotes, trailing punctuation, label prefixes
    for prefix in ("Tiêu đề:", "Title:", "tiêu đề:", "title:"):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix):].strip()
    title = title.strip(" \"'`.:\n\r\t")
 
    if len(title) > 60:
        title = title[:57].rstrip() + "..."
 
    return title or None


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
        from app.agents.memory.mtm import mtm
        from app.agents.memory.stm import stm
        from app.worker.kafka_producer import publish_consolidation_request
        from uuid import uuid4

        new_turn_count = await mtm.increment_turn_count(session_id)
        logger.info("Session %s turn count incremented to %d", session_id[:8], new_turn_count)

        if new_turn_count > 0 and new_turn_count % 10 == 0:
            messages = await stm.get_window(session_id, n_turns=10)
            context = {
                "course_id": course_id,
                "agent_type": agent_type,
                "intent": intent_type,
                "user_id": user_id,
            }
            job_id = str(uuid4())
            await publish_consolidation_request(
                user_id=user_id,
                session_id=session_id,
                messages=messages,
                context=context,
                job_id=job_id
            )
            logger.info("Triggered session consolidation for user %d, session %s, job_id %s", user_id, session_id, job_id)
    except Exception as exc:
        logger.exception("Failed to trigger post-turn consolidation: %s", exc)