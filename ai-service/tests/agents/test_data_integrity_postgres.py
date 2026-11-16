"""Canonical vector hydration against an explicit disposable PostgreSQL DSN."""
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.services.rag_service import RAGService


@pytest.mark.asyncio
async def test_vector_candidates_cannot_restore_deleted_wrong_course_or_failed_chunks():
    dsn = os.environ.get("AGENT_STATE_TEST_DSN")
    if not dsn:
        pytest.skip("Set AGENT_STATE_TEST_DSN to a disposable PostgreSQL database")
    import asyncpg
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    schema = "evidence_test_" + uuid4().hex

    @asynccontextmanager
    async def connection():
        async with pool.acquire() as conn:
            await conn.execute("SELECT set_config('search_path', $1, false)", schema)
            yield conn

    try:
        async with pool.acquire() as conn:
            await conn.execute(f'CREATE SCHEMA "{schema}"')
        async with connection() as conn:
            await conn.execute("""CREATE TABLE document_chunks(
                id BIGINT PRIMARY KEY, course_id BIGINT, node_id BIGINT, content_id BIGINT,
                chunk_text TEXT, status TEXT DEFAULT 'ready', source_type TEXT DEFAULT 'document',
                page_number INT, start_time_sec INT, end_time_sec INT, language TEXT DEFAULT 'en');
                INSERT INTO document_chunks(id,course_id,content_id,node_id,chunk_text,status) VALUES
                (1,27,1770,5,'Canonical MPI data','ready'),
                (2,99,8888,5,'Private other course','ready'),
                (3,27,1770,5,'Invalidated chunk','error'),
                (4,27,1770,5,'Deleted chunk','ready'),
                (5,27,1771,6,'Different lesson','ready');
                DELETE FROM document_chunks WHERE id=4;""")
        points = [SimpleNamespace(id=i, score=0.9, payload={
            "course_id": 27, "chunk_text": "Forged index payload"}) for i in range(1, 6)]
        rag = RAGService()
        with patch("app.services.rag_service.get_ai_conn", connection):
            chunks = await rag._verified_vector_chunks(points, course_id=27)
            assert {c.chunk_id for c in chunks} == {1, 5}
            assert all(c.chunk_text != "Forged index payload" for c in chunks)
            chunks = await rag._verified_vector_chunks(points, course_id=27, content_id=1770)
            assert [c.chunk_id for c in chunks] == [1]
            assert chunks[0].chunk_text == "Canonical MPI data"
            assert not await rag._verified_vector_chunks(points, course_id=27, content_id=8888)
            assert not await rag._verified_vector_chunks(points, course_id=27, node_id=100)
            assert not await rag._verified_vector_chunks(points, course_id=27, content_ids=[])
    finally:
        async with pool.acquire() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await pool.close()
