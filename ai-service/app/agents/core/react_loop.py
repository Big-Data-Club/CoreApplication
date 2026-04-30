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
from app.agents.memory.compressor import compress_conversation
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
COMPRESS_CHECK_INTERVAL = 6  # check compression every N turns


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
    # Step 1: Classify intent (fast — ~100ms)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    intent_type = await classify_intent(user_message, agent_type)

    yield AgentEvent(
        type=AgentEventType.THINKING,
        data={"step": "intent", "intent": intent_type},
        session_id=session_id,
        turn_id=turn_id,
    )

    logger.debug("Intent classified: %s (%.0fms)",
                 intent_type, (time.monotonic() - start_time) * 1000)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1.5: Load active courses + resolve course scope
    #
    # The agent is GLOBAL (manages many courses). Before we touch memory or
    # tools, we figure out which course(s) this turn applies to. The scope
    # is propagated everywhere downstream: prompt anchor, retrieval slot,
    # tool injection, clarification options.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    active_courses = await load_active_courses(
        user_id=user_id,
        agent_type=agent_type,
    )

    # Read the prior MTM anchor (current_course_id, etc.) so the scope
    # resolver can recognise deictic references.
    prior_mtm_ctx = await mtm.get_context(session_id)

    scope = await resolve_course_scope(
        user_message=user_message,
        active_courses=active_courses,
        mtm_ctx=prior_mtm_ctx,
        explicit_course_id=course_id,
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

        # (b) Parameter clarification — only if scope was clean enough.
        param_clarify: dict | None = None
        if scope_clarify is None and scope.mode != "ambiguous":
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

        clarify_result = scope_clarify or param_clarify
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

    # Add STM history (filtered — only user/assistant/tool roles)
    for m in stm_history:
        role = m.get("role", "")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
        elif role == "tool" and content:
            messages.append({
                "role": "tool",
                "content": content,
                "tool_call_id": m.get("tool_call_id", "unknown"),
            })

    # Add the current user message
    messages.append({"role": "user", "content": user_message})

    # Save user message to STM and persistent store
    await stm.append(session_id, "user", user_message)
    await message_store.save_message(session_id, "user", user_message)

    # Get tool schemas for this agent
    tool_schemas = get_tool_schemas(agent_type)

    # Track assistant message across iterations for persistent storage
    assistant_text = ""
    assistant_metadata: dict = {"toolActivities": []}

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

        try:
            async for delta_text, usage, chunk in gateway.stream(req):
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta is None:
                    continue

                # Stream text deltas to frontend
                if delta_text:
                    collected_text += delta_text
                    assistant_text += delta_text
                    yield AgentEvent(
                        type=AgentEventType.TEXT_DELTA,
                        data={"delta": delta_text},
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
                },
                session_id=session_id,
                turn_id=turn_id,
            )
 
            # Post-turn: compression check (non-blocking for user)
            await _post_turn_maintenance(
                session_id=session_id,
                user_id=user_id,
                agent_type=agent_type,
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

            # ── Execute the tool ─────────────────────────────────────────
            # `effective_course_id` reflects the scope resolver's decision:
            # the focused course for "single", None for "multi"/"all"/
            # "none"/"ambiguous" (so cross-course tools run unscoped).
            tool_result = await execute_tool(
                name=tool_name,
                arguments=args,
                user_id=user_id,
                course_id=effective_course_id,
            )

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
                await _post_turn_maintenance(
                    session_id=session_id,
                    user_id=user_id,
                    agent_type=agent_type,
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Post-turn maintenance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _post_turn_maintenance(
    session_id: str,
    user_id: int,
    agent_type: str,
) -> None:
    """
    Background maintenance after a turn completes.
 
    Handles STM → MTM compression. Title generation is handled inline
    in the ReAct loop via `_maybe_emit_title_update` so the frontend
    receives the title as a streaming SSE event.
    """
    try:
        turn_count = await mtm.increment_turn_count(session_id)
 
        if turn_count % COMPRESS_CHECK_INTERVAL != 0:
            return
 
        if await stm.should_compress(session_id):
            logger.info(
                "Triggering MTM compression: session=%s, turn=%d",
                session_id[:8], turn_count,
            )
 
            all_messages = await stm.get_all(session_id)
            existing_ctx = await mtm.get_context(session_id)
 
            compressed = await compress_conversation(
                messages=all_messages,
                agent_type=agent_type,
                existing_ctx=existing_ctx,
            )
 
            await mtm.save_compressed(
                session_id=session_id,
                compressed_ctx=compressed,
                turn_count=turn_count,
            )
 
            await stm.trim_to_recent(session_id, keep_last=4)
 
            logger.info(
                "MTM compression done: session=%s, keys=%s",
                session_id[:8], list(compressed.keys()),
            )
 
    except Exception as exc:
        logger.error("Post-turn maintenance failed: %s", exc)
 
 
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