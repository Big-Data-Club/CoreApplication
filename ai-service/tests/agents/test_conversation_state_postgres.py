"""Real JSONB update ordering; run only against an explicit disposable test DSN."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.agents.memory.mtm import MTMemory


@pytest.mark.asyncio
async def test_state_owner_ordering_concurrency_and_summary_merge():
    dsn = os.environ.get("AGENT_STATE_TEST_DSN")
    if not dsn:
        pytest.skip("Set AGENT_STATE_TEST_DSN to a disposable PostgreSQL database")
    import asyncpg
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    schema = "dialogue_test_" + uuid4().hex
    memory = MTMemory()
    state = {"version": 1, "course_id": 27, "sources": [], "task": None}

    @asynccontextmanager
    async def connection():
        async with pool.acquire() as conn:
            await conn.execute("SELECT set_config('search_path', $1, false)", schema)
            yield conn

    try:
        async with pool.acquire() as conn:
            await conn.execute(f'CREATE SCHEMA "{schema}"')
        async with connection() as conn:
            await conn.execute("""CREATE TABLE agent_sessions(
                id TEXT PRIMARY KEY, user_id BIGINT, compressed_ctx JSONB,
                turn_count BIGINT DEFAULT 0, last_active_at TIMESTAMPTZ DEFAULT NOW());
                INSERT INTO agent_sessions(id,user_id,compressed_ctx)
                VALUES ('own',42,'{"existing":"retained"}'),('foreign',7,'{}');""")
        with patch("app.agents.memory.mtm.get_ai_conn", connection):
            await memory.save_conversation_state("own", 42, state, 101)
            await memory.save_conversation_state("own", 42, state, 99)
            await memory.save_conversation_state("own", 7, state, 1000)
            await memory.save_conversation_state("foreign", 42, state, 1000)
            async with connection() as conn:
                ctx = json.loads(await conn.fetchval("SELECT compressed_ctx FROM agent_sessions WHERE id='own'"))
                assert ctx["conversation_state"]["message_id"] == 101
                assert ctx["existing"] == "retained"
                assert await conn.fetchval("SELECT compressed_ctx->'conversation_state' FROM agent_sessions WHERE id='foreign'") is None
            await asyncio.gather(memory.save_conversation_state("own", 42, state, 105),
                                 memory.save_conversation_state("own", 42, state, 106))
            await memory.save_compressed("own", {"key_facts": {"current_topic": "MPI"}}, 10)
            async with connection() as conn:
                ctx = json.loads(await conn.fetchval("SELECT compressed_ctx FROM agent_sessions WHERE id='own'"))
                assert ctx["conversation_state"]["message_id"] == 106
                assert ctx["key_facts"]["current_topic"] == "MPI"
                # Recover a malformed legacy cursor instead of failing forever.
                await conn.execute("UPDATE agent_sessions SET compressed_ctx=jsonb_set(compressed_ctx,'{conversation_state,message_id}',$1::jsonb) WHERE id='own'", json.dumps("invalid"))
            await memory.save_conversation_state("own", 42, state, 107)
            async with connection() as conn:
                assert await conn.fetchval("SELECT compressed_ctx->'conversation_state'->>'message_id' FROM agent_sessions WHERE id='own'") == "107"
    finally:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await pool.close()
