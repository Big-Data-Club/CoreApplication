"""Durable, bounded consolidation of one session's new dialogue batch."""
from __future__ import annotations

from app.agents.memory.compressor import compress_conversation
from app.agents.memory.ltm import ltm
from app.agents.memory.message_store import message_store
from app.agents.memory.mtm import mtm
from app.agents.memory.stm import stm


async def consolidate_session_job(job_payload: dict) -> dict:
    session_id = job_payload.get("session_id")
    user_id = job_payload.get("user_id")
    context = job_payload.get("context") or {}
    course_id = context.get("course_id")
    agent_type = context.get("agent_type", "mentor")
    if not session_id or not user_id:
        raise ValueError("Consolidation requires session_id and user_id")

    existing_ctx = await mtm.get_context(session_id)
    cursor = int(existing_ctx.get("_last_consolidated_message_id") or 0)
    # Owner check and ID cursor both live in the database query. Raw chat is
    # never placed in Kafka and transient read failures must propagate.
    messages = await message_store.get_unconsolidated(
        session_id, int(user_id), cursor, limit=100,
    )
    if not messages:
        return {"messages": 0, "cursor": cursor}

    new_ctx = await compress_conversation(
        messages, agent_type, existing_ctx, strict=True,
    )
    new_cursor = int(messages[-1]["id"])
    new_ctx["_last_consolidated_message_id"] = new_cursor
    result = {"messages": len(messages), "cursor": new_cursor}

    # Optional LTM recall contains only a compact factual episode. Write it
    # before advancing the MTM cursor, so a Kafka replay can repair a failed
    # MTM write without duplicating the episode.
    facts = new_ctx.get("key_facts") or {}
    gaps = new_ctx.get("identified_gaps") or []
    decisions = new_ctx.get("decisions_made") or []
    summary = "; ".join(str(value) for value in (
        facts.get("current_topic"),
        ", ".join(str(gap) for gap in gaps[:3]),
        decisions[-1] if decisions else None,
    ) if value)[:600]
    if summary:
        result["episode_id"] = await ltm.store_episode(
            session_id=session_id,
            user_id=int(user_id),
            agent_type=agent_type,
            summary_text=summary,
            course_id=int(course_id) if course_id is not None else None,
            idempotency_key=f"{session_id}:{cursor}:{new_cursor}",
        )

    await mtm.save_compressed(
        session_id, new_ctx, int(context.get("turn_count") or 0),
    )
    # Redis is only a small hot window. The durable transcript and MTM state
    # retain continuity if the chat resumes after TTL expiry.
    await stm.trim_to_recent(session_id, keep_last=6)
    return result
