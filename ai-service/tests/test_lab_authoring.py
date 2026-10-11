import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.services import lab_authoring_service as svc
from app.api.endpoints import lab_authoring as api


def payload():
    return dict(title='Special elements', description='Return the sum of special squares.', test_cases=[], runtime_tasks=[], starter_code={}, warnings=[])


def test_bounded_input_and_output():
    with pytest.raises(ValidationError):
        svc.AuthoringRequest(owner_id=1, task='unknown', lab_type='CODING', instruction='hello')
    with pytest.raises(ValidationError):
        svc.AuthoringRequest(owner_id=1, task='create_lab', lab_type='CODING', instruction='hello', source={'x': 'x' * 100001})
    with pytest.raises(ValidationError):
        svc.LabProposal.model_validate({**payload(), 'published': True})
    with pytest.raises(ValidationError):
        svc.CaseDraft(name='test', input='x' * 16385, expected='1')
    case = svc.CaseDraft(name='sample', input='[1]', expected='1', is_sample=True, is_hidden=True)
    assert not case.is_hidden
    with pytest.raises(ValidationError):
        svc.StepDraft(title='Bad path', description='A test', verifier_type='FILE_EXISTS', verifier_config={'path': '../etc/passwd'}, order_index=0)


def test_auth_and_cross_owner_status(monkeypatch):
    monkeypatch.setattr(api, 'get_settings', lambda: SimpleNamespace(ai_service_secret='secret'))
    for secret in (None, '', 'wrong'):
        with pytest.raises(HTTPException) as e:
            api.verify(secret)
        assert e.value.status_code == 401
    api.verify('secret')
    class Conn:
        async def fetchrow(self, query, job_id, owner_id):
            assert 'owner_id=$2' in query
            assert owner_id == 7
            return None
    @asynccontextmanager
    async def connection():
        yield Conn()
    monkeypatch.setattr(api, 'get_ai_conn', connection)
    with pytest.raises(HTTPException) as e:
        asyncio.run(api.status(uuid4(), 7, 'secret'))
    assert e.value.status_code == 404


def test_gateway_task_and_semantic_contract(monkeypatch):
    calls = []
    async def llm(**kwargs):
        calls.append(kwargs)
        return payload()
    monkeypatch.setattr(svc, 'chat_complete_json', llm)
    for task in ('format_lab', 'create_lab', 'create_lab_testcase', 'edit_testcase', 'create_lab_generator'):
        request = svc.AuthoringRequest(owner_id=1, task=task, lab_type='CODING', instruction='Generate safely')
        assert asyncio.run(svc.generate_proposal(request))['title'] == 'Special elements'
        assert calls[-1]['task'] == task
        assert 'stdin/stdout' in calls[-1]['messages'][0]['content']
    async def invalid(**kwargs):
        return {**payload(), 'runtime_tasks': [{'title': 'Step', 'description': 'Run step', 'verifier_type': 'COMMAND_EXIT', 'verifier_config': {'command': 'true'}, 'order_index': 0}]}
    monkeypatch.setattr(svc, 'chat_complete_json', invalid)
    with pytest.raises(ValueError):
        asyncio.run(svc.generate_proposal(request))


@pytest.mark.parametrize('fails', [False, True])
def test_worker_duplicate_and_failure(monkeypatch, fails):
    claimed = False
    writes = []
    class Conn:
        async def fetchrow(self, query, token):
            nonlocal claimed
            assert 'FOR UPDATE SKIP LOCKED' in query
            if claimed:
                return None
            claimed = True
            return {'id': uuid4(), 'request': json.dumps(dict(owner_id=1, task='create_lab', lab_type='CODING', instruction='Create a lab'))}
        async def execute(self, query, *args):
            assert 'lease_token=$5' in query
            writes.append(args)
    @asynccontextmanager
    async def connection():
        yield Conn()
    calls = []
    async def generate(body):
        calls.append(body)
        if fails:
            raise ValueError('malformed LLM output')
        return payload()
    monkeypatch.setattr(svc, 'get_ai_conn', connection)
    monkeypatch.setattr(svc, 'generate_proposal', generate)
    async def run():
        assert await svc.process_next_job()
        assert not await svc.process_next_job()
    asyncio.run(run())
    assert len(calls) == 1
    assert writes[0][0] == ('FAILED' if fails else 'READY')
    assert writes[0][2] is not None if fails else writes[0][2] is None
