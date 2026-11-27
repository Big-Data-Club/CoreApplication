"""Run only against an explicitly supplied disposable PostgreSQL database."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import pytest

from app.api.endpoints.quiz_index import IndexRequest
from app.services import quiz_index_service as service


def test_private_index_postgres_lifecycle():
    dsn = os.getenv("QUIZ_INDEX_TEST_DSN")
    if not dsn:
        pytest.skip("Disposable QUIZ_INDEX_TEST_DSN not supplied")
    asyncio.run(lifecycle(dsn))


async def lifecycle(dsn):
    schema = "quiz_index_test_" + uuid4().hex
    admin = await asyncpg.connect(dsn)
    pool = None
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=3, server_settings={"search_path": schema}
        )

        @asynccontextmanager
        async def database():
            async with pool.acquire() as conn:
                yield conn

        async with database() as conn:
            await conn.execute(
                """CREATE TABLE knowledge_nodes(id BIGSERIAL PRIMARY KEY,course_id BIGINT,name TEXT,
              name_vi TEXT,name_en TEXT,description TEXT,auto_generated BOOLEAN DEFAULT false,source_content_id BIGINT)"""
            )
            sql = (
                Path(__file__).parents[1]
                / "migrations/releases/2026-11-27/V026__quiz_question_index.sql"
            ).read_text()
            await conn.execute(sql)
            await conn.execute(sql)
        client = SimpleNamespace(
            upsert=AsyncMock(), search_batch=AsyncMock(return_value=[[]])
        )

        async def embeddings(texts):
            return [[1.0] + [0.0] * 1023 for _ in texts]

        body = IndexRequest(
            quiz_id=42,
            course_id=7,
            requester_id=3,
            revision="a" * 32,
            question_id=12,
            source_hash="b" * 32,
            name="Temporal difference",
            description="A reviewed concept",
            total=1,
        )
        with patch.object(service, "get_ai_conn", database), patch.object(
            service, "create_passage_embeddings_batch", embeddings
        ), patch.object(
            service, "settings", SimpleNamespace(neo4j_enabled=False)
        ), patch.object(
            service.qdrant_service, "_get_client", return_value=client
        ):
            first = await service.resolve_node(body)
            second = await service.resolve_node(body)
            assert first == second
            body.question_id = 13
            assert await service.resolve_node(body) == first
            async with database() as conn:
                assert await conn.fetchval("SELECT count(*) FROM knowledge_nodes") == 1
                foreign = await conn.fetchval(
                    "INSERT INTO knowledge_nodes(course_id,name) VALUES(8,'Foreign') RETURNING id"
                )
            body.node_id = foreign
            with pytest.raises(ValueError, match="belong"):
                await service.resolve_node(body)
            body.node_id = 0
            with patch.object(service, "dispatch", AsyncMock()) as dispatch:
                queued = await service.queue(body)
                duplicate = await service.queue(body)
                assert queued["job_id"] == duplicate["job_id"]
                assert (
                    dispatch.await_count == 2
                )  # Safe redelivery after uncertain publication.
            page = {
                "course_id": 7,
                "data": [
                    {
                        "id": 12,
                        "node_id": first["node_id"],
                        "question_text": "Question",
                        "options": [],
                        "source_hash": "b" * 32,
                    }
                ],
            }
            head = {"course_id": 7, "data": {"revision": "a" * 32, "total": 1}}
            with patch.object(
                service,
                "source",
                AsyncMock(side_effect=[head, page, {"course_id": 7, "data": []}, head]),
            ), patch.object(service, "ensure_collection", AsyncMock()):
                result = await service.process(queued["job_id"], 42)
                assert result == {"status": "ready", "chunks": 1}
                assert (await service.state(body))["items"][0]["node_id"] == first[
                    "node_id"
                ]
            with patch.object(service, "dispatch", AsyncMock()) as dispatch:
                assert (await service.queue(body))["status"] == "ready"
                dispatch.assert_not_awaited()
            body.revision = "c" * 32
            assert (await service.state(body))["status"] == "stale"
            with pytest.raises(ValueError, match="refresh"):
                await service.search(body)
    finally:
        if pool:
            await pool.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()
