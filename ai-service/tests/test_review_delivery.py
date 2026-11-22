"""Run the real SM-2 class without loading model/provider SDKs."""
import ast
import asyncio
import copy
import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

import pytest


def service_class(get_connection):
    source = Path(__file__).resolve().parents[1] / "app/services/quiz_service.py"
    node = next(node for node in ast.parse(source.read_text()).body
                if isinstance(node, ast.ClassDef) and node.name == "SpacedRepetitionService")
    namespace = dict(get_ai_conn=get_connection, date=date, timedelta=timedelta,
                     hashlib=hashlib, json=json)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["SpacedRepetitionService"]()


class MemoryConnection:
    def __init__(self):
        self.receipts = {}
        self.reviews = {}
        self.progress = 0
        self.fail_progress = False

    @asynccontextmanager
    async def transaction(self):
        snapshot = copy.deepcopy((self.receipts, self.reviews, self.progress))
        try:
            yield
        except Exception:
            self.receipts, self.reviews, self.progress = snapshot
            raise

    async def fetchrow(self, query, *args):
        if "review_delivery_receipts" in query:
            return self.receipts.get(args[0])
        return self.reviews.get(args[:2])

    async def execute(self, query, *args):
        if "INSERT INTO spaced_repetitions" in query:
            self.reviews[args[:2]] = dict(easiness_factor=args[4], interval_days=args[5], repetitions=args[6])
        elif "INSERT INTO student_knowledge_progress" in query:
            if self.fail_progress:
                raise RuntimeError("injected database failure")
            self.progress += 1
        elif "INSERT INTO review_delivery_receipts" in query:
            self.receipts[args[0]] = dict(payload_hash=args[1], result=args[2])


def memory_service():
    conn = MemoryConnection()

    @asynccontextmanager
    async def connection():
        yield conn

    return service_class(connection), conn


def test_duplicate_delivery_does_not_repeat_sm2_or_mastery():
    async def run():
        service, conn = memory_service()
        first = await service.record_response(41, 7, 9, 55, 4, event_id="lms:answer:1:1")
        second = await service.record_response(41, 7, 9, 55, 4, event_id="lms:answer:1:1")
        assert first == second
        assert conn.progress == 1
        assert conn.reviews[(41, 7)]["repetitions"] == 1
        with pytest.raises(ValueError):
            await service.record_response(41, 7, 9, 55, 1, event_id="lms:answer:1:1")
        assert conn.progress == 1
    asyncio.run(run())


def test_failure_rolls_back_schedule_and_receipt_before_retry():
    async def run():
        service, conn = memory_service()
        conn.fail_progress = True
        with pytest.raises(RuntimeError):
            await service.record_response(41, 7, 9, 55, 4, event_id="lms:answer:2:1")
        assert not conn.reviews and not conn.receipts and conn.progress == 0
        conn.fail_progress = False
        await service.record_response(41, 7, 9, 55, 4, event_id="lms:answer:2:1")
        assert conn.progress == 1
    asyncio.run(run())


def test_distinct_delivery_advances_schedule_and_legacy_call_remains_valid():
    async def run():
        service, conn = memory_service()
        await service.record_response(41, 7, 9, 55, 4, event_id="one")
        result = await service.record_response(41, 7, 9, 55, 4, event_id="two")
        assert result["repetitions"] == 2 and conn.progress == 2
        result = await service.record_response(41, 8, 9, None, 4)
        assert result["repetitions"] == 1
        assert conn.progress == 2  # Nullable nodes do not create invalid mastery rows.
    asyncio.run(run())


@pytest.mark.skipif(not os.environ.get("AI_TEST_DATABASE_URL"), reason="disposable PostgreSQL required")
def test_concurrent_deliveries_on_postgres():
    async def run():
        import asyncpg
        import uuid
        pool = await asyncpg.create_pool(os.environ["AI_TEST_DATABASE_URL"], min_size=1, max_size=4)
        schema = "review_test_" + uuid.uuid4().hex
        try:
            async with pool.acquire() as conn:
                await conn.execute(f'CREATE SCHEMA "{schema}"')
                await conn.execute(f'SET search_path TO "{schema}"')
                await conn.execute("""
                    CREATE TABLE spaced_repetitions(student_id bigint,question_id bigint,node_id bigint,course_id bigint,
                        easiness_factor float,interval_days int,repetitions int,quality_last int,next_review_date date,
                        last_reviewed_at timestamptz,updated_at timestamptz,PRIMARY KEY(student_id,question_id));
                    CREATE TABLE student_knowledge_progress(student_id bigint,node_id bigint,course_id bigint,total_attempts int,
                        correct_count int,wrong_count int,mastery_level float,last_tested_at timestamptz,updated_at timestamptz,
                        PRIMARY KEY(student_id,node_id));
                """)
                migration = Path(__file__).resolve().parents[1] / "migrations/releases/2026-11/V025__review_delivery_receipts.sql"
                await conn.execute(migration.read_text())
                await conn.execute(migration.read_text())

            @asynccontextmanager
            async def connection():
                async with pool.acquire() as conn:
                    await conn.execute(f'SET search_path TO "{schema}"')
                    yield conn

            service = service_class(connection)
            results = await asyncio.gather(*[
                service.record_response(41, 7, 9, 55, 4, event_id="same-event") for _ in range(8)
            ])
            assert all(result == results[0] for result in results)
            async with connection() as conn:
                assert await conn.fetchval("SELECT total_attempts FROM student_knowledge_progress") == 1
                assert await conn.fetchval("SELECT repetitions FROM spaced_repetitions") == 1
        finally:
            async with pool.acquire() as conn:
                await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await pool.close()
    asyncio.run(run())
