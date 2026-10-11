"""Optional real PostgreSQL coverage: leases, ownership and recovery."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
import asyncpg
import pytest
from fastapi import HTTPException
from app.api.endpoints import lab_authoring as api
from app.services import lab_authoring_service as svc


def test_durable_jobs_postgres(monkeypatch):
    endpoint = os.getenv('BDC_LAB_SQL_TEST_URL')
    if not endpoint:
        pytest.skip('requires disposable PostgreSQL')
    async def run():
        conn = await asyncpg.connect(endpoint)
        schema = 'authoring_test_' + uuid4().hex
        await conn.execute(f'CREATE SCHEMA {schema}; SET search_path TO {schema}')
        @asynccontextmanager
        async def connection():
            yield conn
        monkeypatch.setattr(api, 'get_ai_conn', connection)
        monkeypatch.setattr(svc, 'get_ai_conn', connection)
        monkeypatch.setattr(api, 'get_settings', lambda: SimpleNamespace(ai_service_secret='test-secret'))
        calls = []
        async def generate(body):
            calls.append(body)
            return {'title': 'Reviewed draft', 'description': 'A valid lab problem.'}
        monkeypatch.setattr(svc, 'generate_proposal', generate)
        try:
            await conn.execute((Path(__file__).parent.parent / 'migrations/V019__lab_authoring_jobs.sql').read_text())
            body = svc.AuthoringRequest(owner_id=1, task='create_lab', lab_type='CODING', instruction='Generate a lab')
            jobs = [await api.create(body, 'test-secret') for _ in range(3)]
            with pytest.raises(HTTPException) as e:
                await api.create(body, 'test-secret')
            assert e.value.status_code == 429
            assert await svc.process_next_job()
            job_id = None
            for j in jobs:
                if (await api.status(UUID(j['id']), 1, 'test-secret'))['status'] == 'READY':
                    job_id = UUID(j['id'])
                    break
            assert job_id is not None
            with pytest.raises(HTTPException) as e:
                await api.status(job_id, 2, 'test-secret')
            assert e.value.status_code == 404
            while await svc.process_next_job():
                pass
            assert len(calls) == 3
            assert not await svc.process_next_job()
            recovered = await api.create(body, 'test-secret')
            await conn.execute("UPDATE lab_authoring_jobs SET status='RUNNING',lease_token=$1,lease_until=now()-interval '1 minute' WHERE id=$2", uuid4(), UUID(recovered['id']))
            assert await svc.process_next_job()
            assert (await api.status(UUID(recovered['id']), 1, 'test-secret'))['status'] == 'READY'
            assert len(calls) == 4
        finally:
            await conn.execute(f'DROP SCHEMA {schema} CASCADE')
            await conn.close()
    asyncio.run(run())
