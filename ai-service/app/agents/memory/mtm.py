"""
ai-service/app/agents/memory/mtm.py

Medium-Term Memory (MTM) — PostgreSQL-backed session context.

Stores compressed conversation summaries in the `agent_sessions` table.
When STM exceeds the token threshold, the compressor produces a JSONB
summary that is merged into the session's `compressed_ctx`.

This lets the agent "remember" key facts across many turns without
re-reading the entire conversation history.

compressed_ctx schema:
    {
        "decisions_made": ["..."],
        "content_created": ["quiz #42", "flashcard set"],
        "identified_gaps": ["Polymorphism", "Recursion"],
        "student_progress": {"avg_mastery": 0.65, "weak_count": 3},
        "pending_actions": ["Review quiz #42 draft"],
        "key_facts": {"preferred_language": "vi", "current_topic": "OOP"}
    }
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)


class MTMemory:
    """Medium-Term Memory backed by PostgreSQL agent_sessions table."""

    async def get_or_create_session(
        self,
        user_id: int,
        agent_type: str,
        course_id: Optional[int] = None,
    ) -> dict:
        """
        Get the most recent session for this user+agent, or create a new one.

        Returns:
            {
                "session_id": str (UUID),
                "context": dict (compressed_ctx JSONB),
                "turn_count": int,
            }
        """
        async with get_ai_conn() as conn:
            # Try to find an existing active session
            row = await conn.fetchrow(
                """SELECT id, compressed_ctx, turn_count
                   FROM agent_sessions
                   WHERE user_id = $1
                     AND agent_type = $2
                     AND ($3::BIGINT IS NULL OR course_id = $3)
                   ORDER BY last_active_at DESC
                   LIMIT 1""",
                user_id, agent_type, course_id,
            )

            if row:
                # Touch last_active_at
                await conn.execute(
                    "UPDATE agent_sessions SET last_active_at = NOW() WHERE id = $1",
                    row["id"],
                )
                ctx = row["compressed_ctx"]
                if isinstance(ctx, str):
                    ctx = json.loads(ctx)
                return {
                    "session_id": str(row["id"]),
                    "context": ctx or {},
                    "turn_count": row["turn_count"] or 0,
                }

            # Pre-load working state from the most recent session
            preload_ctx = {}
            last_session = await conn.fetchrow(
                """SELECT compressed_ctx FROM agent_sessions
                   WHERE user_id = $1 AND agent_type = $2
                   ORDER BY last_active_at DESC LIMIT 1""",
                user_id, agent_type
            )
            if last_session and last_session["compressed_ctx"]:
                old_ctx = last_session["compressed_ctx"]
                if isinstance(old_ctx, str):
                    old_ctx = json.loads(old_ctx)
                
                # Extract anchors from the new unified working_state or legacy key_facts
                ws = old_ctx.get("working_state", {})
                kf = old_ctx.get("key_facts", {})
                
                current_course_id = ws.get("current_course_id") or kf.get("current_course_id")
                current_topic = ws.get("current_topic") or kf.get("current_topic")
                
                if current_course_id or current_topic:
                    preload_ctx["working_state"] = {}
                    if current_course_id:
                        preload_ctx["working_state"]["current_course_id"] = current_course_id
                    if current_topic:
                        preload_ctx["working_state"]["current_topic"] = current_topic

            # Create new session
            new_row = await conn.fetchrow(
                """INSERT INTO agent_sessions
                       (user_id, agent_type, course_id, compressed_ctx, turn_count, title)
                   VALUES ($1, $2, $3, $4::jsonb, 0, NULL)
                   RETURNING id""",
                user_id, agent_type, course_id, json.dumps(preload_ctx, ensure_ascii=False),
            )
            return {
                "session_id": str(new_row["id"]),
                "context": preload_ctx,
                "turn_count": 0,
            }

    async def create_new_session(
        self,
        user_id: int,
        agent_type: str,
        course_id: Optional[int] = None,
    ) -> dict:
        """
        Create a new session, or reuse an existing empty one.
 
        If the user already has a session (same agent_type + course_id) with
        turn_count == 0, we return it instead of creating a new row. This
        prevents empty-session spam when users repeatedly click "New Chat".
        """
        async with get_ai_conn() as conn:
            existing = await conn.fetchrow(
                """SELECT id, compressed_ctx, turn_count
                   FROM agent_sessions
                   WHERE user_id = $1
                     AND agent_type = $2
                     AND ($3::BIGINT IS NULL OR course_id = $3)
                     AND turn_count = 0
                   ORDER BY last_active_at DESC
                   LIMIT 1""",
                user_id, agent_type, course_id,
            )
            if existing:
                await conn.execute(
                    "UPDATE agent_sessions SET last_active_at = NOW() WHERE id = $1",
                    existing["id"],
                )
                ctx = existing["compressed_ctx"]
                if isinstance(ctx, str):
                    ctx = json.loads(ctx)
                return {
                    "session_id": str(existing["id"]),
                    "context": ctx or {},
                    "turn_count": 0,
                    "reused": True,
                }
 
            # Pre-load working state from the most recent session
            preload_ctx = {}
            last_session = await conn.fetchrow(
                """SELECT compressed_ctx FROM agent_sessions
                   WHERE user_id = $1 AND agent_type = $2
                   ORDER BY last_active_at DESC LIMIT 1""",
                user_id, agent_type
            )
            if last_session and last_session["compressed_ctx"]:
                old_ctx = last_session["compressed_ctx"]
                if isinstance(old_ctx, str):
                    old_ctx = json.loads(old_ctx)
                
                ws = old_ctx.get("working_state", {})
                kf = old_ctx.get("key_facts", {})
                
                current_course_id = ws.get("current_course_id") or kf.get("current_course_id")
                current_topic = ws.get("current_topic") or kf.get("current_topic")
                
                if current_course_id or current_topic:
                    preload_ctx["working_state"] = {}
                    if current_course_id:
                        preload_ctx["working_state"]["current_course_id"] = current_course_id
                    if current_topic:
                        preload_ctx["working_state"]["current_topic"] = current_topic

            new_row = await conn.fetchrow(
                """INSERT INTO agent_sessions
                       (user_id, agent_type, course_id, compressed_ctx, turn_count, title)
                   VALUES ($1, $2, $3, $4::jsonb, 0, NULL)
                   RETURNING id""",
                user_id, agent_type, course_id, json.dumps(preload_ctx, ensure_ascii=False),
            )
            return {
                "session_id": str(new_row["id"]),
                "context": preload_ctx,
                "turn_count": 0,
                "reused": False,
            }
 
    async def get_title(self, session_id: str) -> Optional[str]:
        """Return the current title for a session, if any."""
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT title FROM agent_sessions WHERE id = $1",
                session_id,
            )
            return row["title"] if row else None

    async def get_context(self, session_id: str) -> dict:
        """Get the compressed context for a session."""
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT compressed_ctx FROM agent_sessions WHERE id = $1",
                session_id,
            )
            if not row:
                return {}
            ctx = row["compressed_ctx"]
            if isinstance(ctx, str):
                ctx = json.loads(ctx)
            return ctx or {}

    async def get_working_state(self, session_id: str) -> dict:
        """Get the unified working state for a session."""
        ctx = await self.get_context(session_id)
        return ctx.get("working_state", {})

    async def update_working_state(self, session_id: str, updates: dict) -> None:
        """Merge a dictionary into the session's working_state."""
        if not updates:
            return
        async with get_ai_conn() as conn:
            await conn.execute(
                """UPDATE agent_sessions
                   SET compressed_ctx = jsonb_set(
                           COALESCE(compressed_ctx, '{}'::jsonb),
                           '{working_state}',
                           COALESCE(compressed_ctx->'working_state', '{}'::jsonb)
                               || $1::jsonb,
                           true
                       ),
                       last_active_at = NOW()
                   WHERE id = $2""",
                json.dumps(updates, ensure_ascii=False),
                session_id,
            )
        logger.info("MTM working state updated: session=%s, updates=%s", session_id[:8], list(updates.keys()))

    async def save_compressed(
        self,
        session_id: str,
        compressed_ctx: dict,
        turn_count: int,
    ) -> None:
        """
        Update the session with new compressed context.

        Called after the compressor runs. Merges new context with existing
        (the compressor's output replaces the old context).
        """
        async with get_ai_conn() as conn:
            await conn.execute(
                """UPDATE agent_sessions
                   SET compressed_ctx = $1::jsonb,
                       turn_count = $2,
                       last_active_at = NOW()
                   WHERE id = $3""",
                json.dumps(compressed_ctx, ensure_ascii=False),
                turn_count,
                session_id,
            )
        logger.debug(
            "MTM updated: session=%s, turn_count=%d, keys=%s",
            session_id, turn_count, list(compressed_ctx.keys()),
        )

    async def push_recent_course(
        self,
        session_id: str,
        course_id: int,
        course_title: Optional[str] = None,
        max_keep: int = 5,
    ) -> None:
        """
        Maintain a rolling MRU list of courses the user has touched in this
        session under `compressed_ctx.key_facts.recent_courses`.

        Most recent course is pushed to the front; duplicates are de-duped
        by id; the list is capped at `max_keep`. Also pins
        `current_course_id` / `current_course_title` so the system prompt
        sees an up-to-date anchor without waiting for the compressor.
        """
        if not session_id or course_id is None:
            return

        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT compressed_ctx FROM agent_sessions WHERE id = $1",
                session_id,
            )
            if not row:
                return
            ctx = row["compressed_ctx"]
            if isinstance(ctx, str):
                ctx = json.loads(ctx)
            ctx = ctx or {}

            facts = ctx.get("key_facts") or {}
            if not isinstance(facts, dict):
                facts = {}

            recent = facts.get("recent_courses") or []
            if not isinstance(recent, list):
                recent = []

            # De-dupe by id, push to front.
            recent = [
                rc for rc in recent
                if isinstance(rc, dict) and rc.get("id") != course_id
            ]
            entry = {"id": course_id}
            if course_title:
                entry["title"] = course_title
            recent.insert(0, entry)
            recent = recent[:max_keep]

            facts["recent_courses"] = recent
            facts["current_course_id"] = course_id
            if course_title:
                facts["current_course_title"] = course_title

            await conn.execute(
                """UPDATE agent_sessions
                   SET compressed_ctx = jsonb_set(
                           COALESCE(compressed_ctx, '{}'::jsonb),
                           '{key_facts}',
                           $1::jsonb,
                           true
                       ),
                       last_active_at = NOW()
                   WHERE id = $2""",
                json.dumps(facts, ensure_ascii=False),
                session_id,
            )

    async def update_key_facts(
        self,
        session_id: str,
        updates: dict,
    ) -> None:
        """
        Merge a small dict into the session's compressed_ctx.key_facts.
 
        Used by the ReAct loop to pin anchors (current_course_id,
        current_node_id, current_topic, ...) immediately after a tool
        surfaces a concrete value — without waiting for the full
        compressor to run. Missing key_facts object is created on demand.
        """
        if not updates:
            return
        async with get_ai_conn() as conn:
            await conn.execute(
                """UPDATE agent_sessions
                   SET compressed_ctx = jsonb_set(
                           COALESCE(compressed_ctx, '{}'::jsonb),
                           '{key_facts}',
                           COALESCE(compressed_ctx->'key_facts', '{}'::jsonb)
                               || $1::jsonb,
                           true
                       ),
                       last_active_at = NOW()
                   WHERE id = $2""",
                json.dumps(updates, ensure_ascii=False),
                session_id,
            )

    async def increment_turn_count(self, session_id: str) -> int:
        """Increment and return the new turn count."""
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """UPDATE agent_sessions
                   SET turn_count = turn_count + 1,
                       last_active_at = NOW()
                   WHERE id = $1
                   RETURNING turn_count""",
                session_id,
            )
            return row["turn_count"] if row else 0

    async def update_title(self, session_id: str, title: str) -> None:
        """Set the AI-generated title for a session."""
        async with get_ai_conn() as conn:
            await conn.execute(
                "UPDATE agent_sessions SET title = $1 WHERE id = $2",
                title, session_id
            )

    async def list_sessions(
        self,
        user_id: int,
        agent_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """List recent sessions for a user (for session history UI)."""
        async with get_ai_conn() as conn:
            if agent_type:
                rows = await conn.fetch(
                    """SELECT id, agent_type, course_id, turn_count,
                              last_active_at, created_at, title
                       FROM agent_sessions
                       WHERE user_id = $1 AND agent_type = $2
                       ORDER BY last_active_at DESC
                       LIMIT $3""",
                    user_id, agent_type, limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, agent_type, course_id, turn_count,
                              last_active_at, created_at, title
                       FROM agent_sessions
                       WHERE user_id = $1
                       ORDER BY last_active_at DESC
                       LIMIT $2""",
                    user_id, limit,
                )
            return [
                {
                    "session_id": str(r["id"]),
                    "title": r["title"],
                    "agent_type": r["agent_type"],
                    "course_id": r["course_id"],
                    "turn_count": r["turn_count"],
                    "last_active_at": r["last_active_at"].isoformat()
                        if r["last_active_at"] else None,
                    "created_at": r["created_at"].isoformat()
                        if r["created_at"] else None,
                }
                for r in rows
            ]


# Singleton
mtm = MTMemory()
