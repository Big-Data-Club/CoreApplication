"""
ai-service/app/agents/core/orchestrator.py

Session Orchestrator — top-level entry point for agent chat.

This is the single function that the API endpoint calls.
It manages the full session lifecycle:
  1. Session resolution (get or create MTM session)
  2. LTM collection initialization
  3. Delegating to the ReAct loop
  4. Session event emission

Separating this from react_loop.py keeps concerns clean:
  - orchestrator = session management + lifecycle
  - react_loop   = reasoning + tool execution
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from app.agents.events import AgentEvent, AgentEventType
from app.agents.memory.mtm import mtm
from app.agents.memory.ltm import ltm
from app.agents.core.react_loop import run_react_loop

logger = logging.getLogger(__name__)


async def handle_chat_message(
    user_id: int,
    agent_type: str,
    message: str,
    course_id: int | None = None,
    session_id: str | None = None,
    user_context: dict | None = None,
    active_courses_hint: list[dict] | None = None,
    page_context: dict | None = None,
    system_context: dict | None = None,
) -> AsyncIterator[AgentEvent]:
    """
    Top-level entry point for processing a chat message.

    This async generator yields all events needed by the SSE endpoint.

    Args:
        user_id: Authenticated user ID (from JWT via lms-service proxy).
        agent_type: "teacher" or "mentor".
        message: The user's message text.
        course_id: Optional EXPLICIT course context — when the FE opens a
            course-scoped chat panel ("Quiz for course X"), it pins the
            scope. Omit (None) for a global session where the user can
            roam across all their courses.
        session_id: Optional existing session ID. If None, creates/finds one.
        user_context: Optional user identity (name, email, role) from JWT.
        active_courses_hint: Optional list of {id, title, status} from the
            FE. When supplied we warm the active-courses cache so the very
            first turn doesn't pay a cold LMS round-trip. Authoritative
            data is still loaded from LMS.

    Yields:
        AgentEvent objects for SSE streaming.
    """
    # If the FE supplied an active-courses hint, warm the cache up front
    # so the ReAct loop's `load_active_courses()` returns immediately.
    if active_courses_hint:
        from app.agents.memory.active_courses import seed_active_courses_cache
        seed_active_courses_cache(
            user_id=user_id,
            agent_type=agent_type,
            courses=active_courses_hint,
        )

    # ── 1. Resolve session ────────────────────────────────────────────────────
    if session_id:
        # Use existing session — just verify it exists and retrieve context + turn count
        session_info = await mtm.get_session(session_id)
        if session_info:
            session_data = {
                "session_id": session_id,
                "context": session_info["context"],
                "turn_count": session_info["turn_count"],
            }
        else:
            # Fallback to creating a new session if the provided session_id wasn't found
            session_data = await mtm.create_new_session(
                user_id=user_id,
                agent_type=agent_type,
                course_id=course_id,
            )
            session_id = session_data["session_id"]
    else:
        # Create a new session instead of reusing the most recent active one
        # to respect the clean slate / new conversation request when session_id is None.
        session_data = await mtm.create_new_session(
            user_id=user_id,
            agent_type=agent_type,
            course_id=course_id,
        )
        session_id = session_data["session_id"]

    logger.info(
        "Chat session: id=%s, user=%d, agent=%s, turn=%d",
        session_id[:8], user_id, agent_type, session_data.get("turn_count", 0),
    )

    # ── 2. Emit session event (tells frontend the session ID) ────────────────
    yield AgentEvent(
        type=AgentEventType.SESSION,
        data={
            "session_id": session_id,
            "agent_type": agent_type,
            "is_new": session_data.get("turn_count", 0) == 0,
        },
        session_id=session_id,
    )

    # ── 3. Ensure LTM collection exists (idempotent, first call only) ────────
    try:
        await ltm.ensure_collection()
    except Exception as exc:
        logger.warning("LTM collection init failed (non-fatal): %s", exc)

    # ── 4. Delegate to ReAct loop ────────────────────────────────────────────
    async for event in run_react_loop(
        session_id=session_id,
        user_id=user_id,
        agent_type=agent_type,
        user_message=message,
        course_id=course_id,
        user_context=user_context,
        page_context=page_context,
        system_context=system_context,
    ):
        yield event
