"""Run only against an explicitly supplied disposable PostgreSQL database."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import httpx
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
            recovery_sql = (
                Path(__file__).parents[1]
                / "migrations/releases/2026-11-27/V027__quiz_index_recovery.sql"
            ).read_text()
            await conn.execute(recovery_sql)
            await conn.execute(recovery_sql)
        client = SimpleNamespace(
            upsert=AsyncMock(),
            search_batch=AsyncMock(return_value=[[]]),
            collection_exists=AsyncMock(return_value=True),
            delete=AsyncMock(),
            create_payload_index=AsyncMock(),
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

            # Lost Kafka notification: the persisted pending job is recovered
            # without publishing again, and a fresh claim owns its generation.
            body.revision, body.force = "a" * 32, True
            with patch.object(service, "dispatch", AsyncMock()):
                queued = await service.queue(body)
            async with database() as conn:
                await conn.execute(
                    "UPDATE quiz_index_jobs SET updated_at=now()-interval '1 minute' WHERE quiz_id=42"
                )
            with patch.object(
                service,
                "source",
                AsyncMock(side_effect=[head, page, {"course_id": 7, "data": []}, head]),
            ), patch.object(service, "ensure_collection", AsyncMock()):
                await service.recover_due()
            async with database() as conn:
                recovered = await conn.fetchrow(
                    "SELECT * FROM quiz_index_jobs WHERE quiz_id=42"
                )
            assert recovered["status"] == "ready"
            assert recovered["attempts"] == 1
            assert recovered["generation"] == recovered["claim_id"]
            assert str(recovered["generation"]) != queued["job_id"]

            # A transient error schedules recovery; duplicates during backoff
            # cannot consume another attempt or publish an incomplete index.
            with patch.object(service, "dispatch", AsyncMock()):
                queued = await service.queue(body)
            with patch.object(
                service,
                "source",
                AsyncMock(side_effect=httpx.ConnectTimeout("test timeout")),
            ):
                with pytest.raises(httpx.ConnectTimeout):
                    await service.process(queued["job_id"], 42)
                assert (await service.process(queued["job_id"], 42))[
                    "status"
                ] == "already_claimed"
                assert (await service.state(body))["status"] == "pending"
                async with database() as conn:
                    assert (
                        await conn.fetchval(
                            "SELECT attempts FROM quiz_index_jobs WHERE quiz_id=42"
                        )
                        == 1
                    )
                for _ in range(2):
                    async with database() as conn:
                        await conn.execute(
                            "UPDATE quiz_index_jobs SET retry_at=now()-interval '1 second' WHERE quiz_id=42"
                        )
                    await service.recover_due()
                async with database() as conn:
                    exhausted = await conn.fetchrow(
                        "SELECT * FROM quiz_index_jobs WHERE quiz_id=42"
                    )
                assert exhausted["attempts"] == 3
                assert exhausted["status"] == "failed"
                assert exhausted["retry_at"] is None
                assert (await service.state(body))["status"] == "failed"
                await service.recover_due()
                async with database() as conn:
                    assert (
                        await conn.fetchval(
                            "SELECT attempts FROM quiz_index_jobs WHERE quiz_id=42"
                        )
                        == 3
                    )

            # A crash at the final attempt is terminal after lease expiry.
            async with database() as conn:
                await conn.execute(
                    "UPDATE quiz_index_jobs SET status='processing',lease_until=now()-interval '1 second' WHERE quiz_id=42"
                )
            await service.recover_due()
            async with database() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT last_error_code FROM quiz_index_jobs WHERE quiz_id=42"
                    )
                    == "recovery_exhausted"
                )

            # Permission/source errors are terminal without automatic retries.
            with patch.object(service, "dispatch", AsyncMock()):
                queued = await service.queue(body)
            with patch.object(
                service, "source", AsyncMock(side_effect=ValueError("Quiz changed"))
            ):
                with pytest.raises(ValueError):
                    await service.process(queued["job_id"], 42)
            async with database() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT retry_at FROM quiz_index_jobs WHERE quiz_id=42"
                    )
                    is None
                )

            # Simulate a paused worker outliving its lease. A duplicate cannot
            # claim a live lease; once expired, a new claim publishes a separate
            # generation and the old worker cannot change the ready result.
            with patch.object(service, "dispatch", AsyncMock()):
                queued = await service.queue(body)
            blocked, release = asyncio.Event(), asyncio.Event()
            calls = 0

            async def collections():
                nonlocal calls
                calls += 1
                if calls == 1:
                    blocked.set()
                    await release.wait()

            async def sources(quiz_id, requester_id, *, head=False, after=0):
                if head:
                    return {"course_id": 7, "data": {"revision": "a" * 32, "total": 1}}
                return {"course_id": 7, "data": []} if after else page

            with patch.object(service, "source", sources), patch.object(
                service, "ensure_collection", collections
            ):
                old = asyncio.create_task(service.process(queued["job_id"], 42))
                try:
                    await asyncio.wait_for(blocked.wait(), 2)
                    assert (await service.process(queued["job_id"], 42))[
                        "status"
                    ] == "already_claimed"
                    async with database() as conn:
                        await conn.execute(
                            "UPDATE quiz_index_jobs SET lease_until=now()-interval '1 second' WHERE quiz_id=42"
                        )
                    assert (await service.process(queued["job_id"], 42))[
                        "status"
                    ] == "ready"
                    async with database() as conn:
                        winner = await conn.fetchval(
                            "SELECT generation FROM quiz_index_jobs WHERE quiz_id=42"
                        )
                    release.set()
                    with pytest.raises(ValueError, match="superseded"):
                        await old
                    async with database() as conn:
                        final = await conn.fetchrow(
                            "SELECT status,generation FROM quiz_index_jobs WHERE quiz_id=42"
                        )
                    assert final["status"] == "ready"
                    assert final["generation"] == winner
                finally:
                    old.cancel()
                    await asyncio.gather(old, return_exceptions=True)
    finally:
        if pool:
            await pool.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()
