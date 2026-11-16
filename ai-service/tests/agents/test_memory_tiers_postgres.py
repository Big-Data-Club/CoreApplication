"""Run against a disposable PostgreSQL DSN only; each test owns its schema."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.agents.memory.ltm import LTMemory
from app.agents.memory.message_store import MessageStore
from app.agents.memory.mtm import MTMemory


@pytest.mark.asyncio
async def test_memory_scope_provenance_archive_idempotency_and_cursor_cas():
    dsn = os.environ.get("AGENT_STATE_TEST_DSN")
    if not dsn:
        pytest.skip("Set AGENT_STATE_TEST_DSN to a disposable PostgreSQL database")
    import asyncpg
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    schema = "memory_test_" + uuid4().hex

    @asynccontextmanager
    async def connection():
        async with pool.acquire() as conn:
            await conn.execute("SELECT set_config('search_path', $1, false)", schema)
            yield conn

    memory, transcript, episodes = MTMemory(), MessageStore(), LTMemory()
    try:
        async with pool.acquire() as conn:
            await conn.execute(f'CREATE SCHEMA "{schema}"')
        async with connection() as conn:
            await conn.execute("""CREATE TABLE agent_sessions(
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id BIGINT, agent_type TEXT,
                course_id BIGINT, compressed_ctx JSONB DEFAULT '{}', title TEXT,
                turn_count BIGINT DEFAULT 0, last_active_at TIMESTAMPTZ DEFAULT NOW());
                CREATE TABLE agent_messages(id BIGSERIAL PRIMARY KEY,
                session_id UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
                role TEXT, content TEXT, metadata JSONB);
                CREATE TABLE agent_episodes(id UUID PRIMARY KEY,
                session_id UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
                user_id BIGINT, agent_type TEXT, summary TEXT, course_id BIGINT,
                qdrant_point_id BIGINT, created_at TIMESTAMPTZ DEFAULT NOW());""")
        with (
            patch("app.agents.memory.mtm.get_ai_conn", connection),
            patch("app.agents.memory.message_store.get_ai_conn", connection),
            patch("app.agents.memory.ltm.get_ai_conn", connection),
            patch("app.agents.memory.ltm.settings.use_qdrant", False),
        ):
            old = await memory.create_new_session(42, "mentor", 27)
            old_id = old["session_id"]
            # Global new chat cannot reuse an empty course chat.
            current = await memory.create_new_session(42, "mentor")
            current_id = current["session_id"]
            assert current_id != old_id and current["context"] == {}
            assert (await memory.get_or_create_session(42, "mentor"))["session_id"] == current_id
            foreign = (await memory.create_new_session(7, "mentor"))["session_id"]
            teacher = (await memory.create_new_session(42, "teacher"))["session_id"]
            msg_id = await transcript.save_message(old_id, "user", "Keep it concise: 100%_literal\\value")
            assert msg_id
            await transcript.save_message(old_id, "assistant", "Keep it detailed instead")
            assert await transcript.search_history(old_id, 7) == []
            assert len(await transcript.search_history(old_id, 42, "100%_literal\\value")) == 1
            assert await transcript.search_history(old_id, 42, "' OR 1=1 --") == []
            assert await transcript.search_history(old_id, 42, "100%_missing") == []
            assert len(await transcript.search_history(old_id, 42, role="all")) == 2
            pref = {"kind": "preference", "key": "response_style", "scope": "user",
                    "value": "concise", "source": "user_statement", "source_message_id": msg_id,
                    "source_quote": "Keep it concise", "confidence": 0.9}
            await memory.save_compressed(old_id, {"memory_items": [pref], "working_state": {"current_topic": "MPI"}}, 2)
            for sid in (foreign, teacher):
                await memory.save_compressed(sid, {"memory_items": [{**pref, "source_message_id": 999, "value": "foreign"}]}, 2)
            prefs = await memory.get_user_preferences(42, "mentor", current_id)
            assert len(prefs) == 1 and prefs[0]["value"] == "concise"
            # Two overlapping jobs cannot both overwrite the same cursor revision.
            outcomes = await asyncio.gather(
                memory.save_compressed(old_id, {"_last_consolidated_message_id": 10}, 2, expected_cursor=0),
                memory.save_compressed(old_id, {"_last_consolidated_message_id": 20}, 2, expected_cursor=0),
            )
            assert sorted(outcomes) == [False, True]
            assert not await memory.save_compressed(old_id, {"_last_consolidated_message_id": 1}, 1, expected_cursor=0)
            # Same range replay keeps the canonical durable summary and one row.
            first = await episodes.store_episode(old_id, 42, "mentor", "MPI original", 27, "test-range")
            assert await episodes.store_episode(old_id, 42, "mentor", "invented replay", 27, "test-range") == first
            await episodes.store_episode(current_id, 42, "mentor", "Global", idempotency_key="global-range")
            await episodes.store_episode(foreign, 7, "mentor", "Foreign", idempotency_key="foreign-range")
            with pytest.raises(ValueError):
                await episodes.store_episode(old_id, 7, "mentor", "Wrong owner")
            assert [ep["summary"] for ep in await episodes.recall(42, "mentor", "MPI")] == ["Global"]
            scoped = await episodes.recall(42, "mentor", "MPI", top_k=10, course_ids=[27])
            assert {ep["summary"] for ep in scoped} == {"Global", "MPI original"}
            assert all(ep["score"] is None for ep in scoped)
            async with connection() as conn:
                assert await conn.fetchval("SELECT count(*) FROM agent_episodes WHERE session_id=$1", old_id) == 1
                await conn.execute("DELETE FROM agent_sessions WHERE id=$1", old_id)
            assert not await transcript.search_history(old_id, 42)
            assert await memory.get_user_preferences(42, "mentor", current_id) == []
            assert [ep["summary"] for ep in await episodes.recall(42, "mentor", "MPI", course_ids=[27])] == ["Global"]
    finally:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await pool.close()
