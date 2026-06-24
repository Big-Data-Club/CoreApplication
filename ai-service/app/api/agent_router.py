"""
ai-service/app/api/agent_router.py

FastAPI router for the Agent chat system.

Endpoints:
  POST /agents/chat       — SSE streaming chat response
  GET  /agents/sessions    — List user sessions
  GET  /agents/health      — Agent system health check

The /agents/chat endpoint uses Server-Sent Events (SSE) to stream
AgentEvents in real-time to the frontend. Each event is a JSON line
in SSE format.

Security: All endpoints validate the X-AI-Secret header (same as
other ai-service endpoints) or accept proxied JWT from lms-service.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.core.orchestrator import handle_chat_message
from app.agents.memory.mtm import mtm
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Request/Response models ──────────────────────────────────────────────────

class UserContext(BaseModel):
    """User identity context injected from the frontend JWT session."""
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


class ActiveCourseHint(BaseModel):
    """
    Hint from the frontend about a course the user has access to.

    Optional — the agent loads its own authoritative list, but supplying
    this seeds the cache and avoids a cold LMS round-trip on the first
    turn. Pass the full list of courses currently visible in the sidebar
    (teacher: created courses; student: ACCEPTED enrolments).
    """
    id: int
    title: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None  # "owner" | "student"


class SystemContext(BaseModel):
    """
    Out-of-band context the FE supplies when the user opens "Ask AI"
    from inside a micro-lesson. This is invisibly stitched into the
    agent's system prompt so the model knows exactly which lesson the
    student is reading, without bloating the visible chat history.

    Fields are optional — the FE typically provides ``lesson_text``
    plus ``lesson_id`` / ``node_id``. The model never sees this dict
    raw; it is rendered through ``_format_system_context`` in
    ``agents/core/prompts.py``.
    """
    lesson_id: Optional[int] = None
    lesson_title: Optional[str] = None
    node_id: Optional[int] = None
    course_id: Optional[int] = None
    lesson_text: Optional[str] = Field(default=None, max_length=20000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    agent_type: str = Field(
        default="mentor",
        pattern="^(teacher|mentor)$",
    )
    course_id: Optional[int] = None
    session_id: Optional[str] = None
    user_id: int = Field(..., gt=0)
    user_context: Optional[UserContext] = None
    active_courses: Optional[list[ActiveCourseHint]] = None
    page_context: Optional[dict] = None
    system_context: Optional[SystemContext] = None


class SessionListResponse(BaseModel):
    sessions: list[dict]


# ── Auth helper ──────────────────────────────────────────────────────────────

def _verify_secret(x_ai_secret: str | None):
    """Verify the X-AI-Secret header."""
    if not x_ai_secret or x_ai_secret != settings.ai_service_secret:
        raise HTTPException(status_code=401, detail="Invalid AI service secret")


# ── SSE Chat Endpoint ───────────────────────────────────────────────────────

@router.post("/chat")
async def chat_endpoint(
    body: ChatRequest,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret"),
):
    """
    SSE streaming chat endpoint.

    The client sends a POST with the message and receives a stream
    of Server-Sent Events. Each event is a JSON object with:
      - type: event type (text_delta, tool_start, tool_result, etc.)
      - data: event payload
      - session_id: the active session
      - turn_id: identifier for this turn

    Example frontend usage:
    ```javascript
    const response = await fetch('/api/ai/agents/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-AI-Secret': '...'},
        body: JSON.stringify({message: "Explain OOP", agent_type: "mentor", user_id: 1}),
    });
    const reader = response.body.getReader();
    // Read SSE events...
    ```
    """
    _verify_secret(x_ai_secret)

    logger.info(
        "Chat request: user=%d, agent=%s, msg='%s'",
        body.user_id, body.agent_type, body.message[:60],
    )

    async def event_stream():
        try:
            active_hint = (
                [c.model_dump() for c in body.active_courses]
                if body.active_courses else None
            )
            async for event in handle_chat_message(
                user_id=body.user_id,
                agent_type=body.agent_type,
                message=body.message,
                course_id=body.course_id,
                session_id=body.session_id,
                user_context=body.user_context.model_dump() if body.user_context else None,
                active_courses_hint=active_hint,
                page_context=body.page_context,
                system_context=body.system_context.model_dump() if body.system_context else None,
            ):
                yield event.to_sse()
        except Exception as exc:
            logger.error("Chat stream error: %s", exc)
            from app.agents.events import AgentEvent, AgentEventType
            error_event = AgentEvent(
                type=AgentEventType.ERROR,
                data={"error": str(exc)},
                session_id=body.session_id or "error",
            )
            yield error_event.to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


# ── Session history ──────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    user_id: int,
    agent_type: Optional[str] = None,
    limit: int = 10,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret"),
):
    """List recent chat sessions for a user."""
    _verify_secret(x_ai_secret)

    sessions = await mtm.list_sessions(
        user_id=user_id,
        agent_type=agent_type,
        limit=limit,
    )
    return {"sessions": sessions}

class NewSessionRequest(BaseModel):
    user_id: int
    agent_type: str = Field(pattern="^(teacher|mentor)$")
    course_id: Optional[int] = None

@router.post("/sessions/new")
async def create_new_session(
    body: NewSessionRequest,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret"),
):
    """Force create a completely new session (instead of reusing recent)."""
    _verify_secret(x_ai_secret)
    session_data = await mtm.create_new_session(
        user_id=body.user_id,
        agent_type=body.agent_type,
        course_id=body.course_id,
    )
    return session_data

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: int = 100,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret"),
):
    """Get the persistent message history for a session."""
    _verify_secret(x_ai_secret)
    from app.agents.memory.message_store import message_store
    messages = await message_store.get_messages(session_id=session_id, limit=limit)
    return {"messages": messages}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret"),
):
    """Delete a session and cascade delete its messages."""
    _verify_secret(x_ai_secret)
    await mtm.delete_session(session_id)
    return {"status": "ok"}


# ── Notebook CRUD Proxy ───────────────────────────────────────────────────────

@router.get("/notebook")
async def list_notebook(
    user_id: int,
    course_id: Optional[int] = None,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret"),
):
    """Proxy request to personalize-service to load saved notebook entries."""
    _verify_secret(x_ai_secret)
    import httpx
    url = f"{settings.personalize_service_url}/personalize/notebook"
    params = {"user_id": user_id}
    if course_id is not None:
        params["course_id"] = course_id
    headers = {"X-AI-Secret": settings.ai_service_secret}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params, headers=headers)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return {"notes": res.json()}
    except Exception as e:
        logger.error(f"Failed to proxy list_notebook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notebook/{entry_id}")
async def delete_notebook_entry(
    entry_id: str,
    user_id: int,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret"),
):
    """Proxy request to personalize-service to delete a notebook entry."""
    _verify_secret(x_ai_secret)
    import httpx
    url = f"{settings.personalize_service_url}/personalize/notebook/{entry_id}"
    params = {"user_id": user_id}
    headers = {"X-AI-Secret": settings.ai_service_secret}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.delete(url, params=params, headers=headers)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy delete_notebook_entry: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Health check ─────────────────────────────────────────────────────────────

@router.get("/health")
async def agent_health():
    """Agent system health check."""
    from app.agents.tools.registry import list_all_tools

    tools = list_all_tools()
    return {
        "status": "ok",
        "agents": list(tools.keys()),
        "tools": {k: len(v) for k, v in tools.items()},
    }
