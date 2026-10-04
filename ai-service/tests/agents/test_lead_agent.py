import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from app.agents.core.lead_agent import (
    Assignment, LeadPlan, SharedBoard, Artifact, bounded, make_lead_plan,
    execute_assignment, prepare_collaboration,
)
from app.agents.events import AgentEvent, AgentEventType
from app.core.llm_gateway.token_budget import estimate_tokens


def assignment(key='work_compare', **kwargs):
    return dict(id=key, role='Compare costs', objective='Compare QPU tradeoffs',
                executor='llm', consumes=['task'], **kwargs)


def plan(tasks=None, inputs=None):
    tasks = [assignment()] if tasks is None else tasks
    return LeadPlan(rationale='Separate independent questions', assignments=tasks,
                    answer_inputs=inputs or [a['id'] for a in tasks], critique=False)


@pytest.mark.parametrize('tasks,inputs', [
    ([dict(assignment(), consumes=['work_compare'])], ['work_compare']),
    ([assignment(), assignment()], ['work_compare']),
    ([dict(assignment(), executor='shell')], ['work_compare']),
    ([assignment()], ['task']),
    ([assignment()], ['foreign_session_memory']),
    ([dict(assignment(), consumes=['task', 'task'])], ['work_compare']),
    ([dict(assignment(), executor='retrieval'), dict(assignment('work_second'), executor='retrieval')], ['work_compare','work_second']),
])
def test_invalid_or_unnecessary_plans_are_rejected(tasks, inputs):
    with pytest.raises(ValidationError):
        plan(tasks, inputs)


def test_shared_board_is_scoped_selective_and_bounded():
    board = SharedBoard({'task': 'QPU', 'memory': 'PRIVATE LEARNING PROFILE'})
    board.publish('work_compare', Artifact('x ' * 9000, 'analysis', 'work_compare', ('task',)))
    view = board.read(['task', 'work_compare'], budget=400)
    assert 'PRIVATE' not in view
    assert 'kind=analysis' in view and 'sources=task' in view
    assert estimate_tokens(view) <= 400
    assert estimate_tokens(bounded('Xin chào ' * 3000, 50)) <= 50
    with pytest.raises(ValueError):
        board.publish('task', Artifact('overwrite', 'analysis', 'worker'))
    with pytest.raises(KeyError):
        SharedBoard({'task': 'other user'}).read(['work_compare'])


@pytest.mark.asyncio
async def test_policy_keeps_evidence_and_quality_gates():
    board = SharedBoard({'task': 'QPU'})
    with patch('app.agents.core.lead_agent.chat_complete_structured', new=AsyncMock(return_value=plan())):
        with pytest.raises(ValueError, match='required evidence'):
            await make_lead_plan('QPU', board, require_evidence=True, quality_gate=True, system_one_enabled=False)
    candidate = plan([dict(assignment(), executor='retrieval')])
    with patch('app.agents.core.lead_agent.chat_complete_structured', new=AsyncMock(return_value=candidate)):
        result = await make_lead_plan('QPU', board, require_evidence=True, quality_gate=True, system_one_enabled=False)
    assert result.critique


@pytest.mark.asyncio
async def test_disabled_system_one_cannot_be_selected():
    candidate = plan([dict(assignment(), executor='system_one')])
    with patch('app.agents.core.lead_agent.chat_complete_structured', new=AsyncMock(return_value=candidate)):
        with pytest.raises(ValueError, match='disabled'):
            await make_lead_plan('QPU', SharedBoard({'task': 'QPU'}), require_evidence=False, quality_gate=False, system_one_enabled=False)


ARGS = dict(query='QPU', course_id=7, memory_context='private memory',
    history=[{'role': 'user', 'content': 'old discussion'}], page_context=None,
    system_context=None, require_evidence=False, quality_gate=False,
    session_id='session', turn_id='turn', system_one_enabled=False)


@pytest.mark.asyncio
async def test_parallel_workers_join_before_dependent_worker_and_select_final_context():
    candidate = plan([assignment('work_cost'), assignment('work_latency'),
        dict(assignment('work_compare'), consumes=['work_cost', 'work_latency'])], ['work_compare', 'history'])
    active, peak = 0, 0
    started = set()
    both = asyncio.Event()
    async def execute(a, board, **kwargs):
        nonlocal active, peak
        if a.id == 'work_compare':
            assert 'work_cost' in board.read(a.consumes)
            assert 'work_latency' in board.read(a.consumes)
        active += 1
        peak = max(peak, active)
        started.add(a.id)
        if {'work_cost','work_latency'} <= started:
            both.set()
        await asyncio.wait_for(both.wait(), 1)
        await asyncio.sleep(0)
        active -= 1
        return Artifact(a.id, 'analysis', a.id), []
    with patch('app.agents.core.lead_agent.make_lead_plan', new=AsyncMock(return_value=candidate)), patch('app.agents.core.lead_agent.execute_assignment', execute):
        output = [item async for item in prepare_collaboration(**ARGS)]
    assert peak == 2
    handoff = output[-1]
    assert handoff['memory'] == '' and handoff['history'] == ARGS['history']
    assert 'private memory' not in handoff['context']
    assert handoff['trace']['steps'][2]['consumes'] == ['work_cost', 'work_latency']
    assert len([e for e in output if isinstance(e, AgentEvent) and e.type == AgentEventType.SUBAGENT_DONE]) == 3


@pytest.mark.asyncio
async def test_failed_worker_cancels_sibling_and_does_not_publish_handoff():
    candidate = plan([assignment('work_one'), assignment('work_two')])
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def execute(a, board, **kwargs):
        if a.id == 'work_one':
            await started.wait()
            raise TimeoutError('provider deadline')
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    output = []
    with patch('app.agents.core.lead_agent.make_lead_plan', new=AsyncMock(return_value=candidate)), patch('app.agents.core.lead_agent.execute_assignment', execute):
        with pytest.raises(ExceptionGroup):
            async for item in prepare_collaboration(**ARGS):
                output.append(item)
    assert cancelled.is_set()
    assert all(isinstance(item, AgentEvent) for item in output)


@pytest.mark.asyncio
@pytest.mark.parametrize('score', [None, True, float('nan'), 1.5, 0.7])
async def test_system_one_signal_is_validated_and_never_evidence(score):
    gateway = SimpleNamespace(evaluate_jev=AsyncMock(return_value={'scores': {'satisfies_objective': score}}))
    args = dict(session_id='s', turn_id='t', query='QPU', course_id=7, page_context=None, system_context=None)
    a = Assignment(**dict(assignment(), executor='system_one'))
    with patch('app.agents.core.lead_agent.get_gateway', return_value=gateway):
        if score == 0.7:
            artifact, refs = await execute_assignment(a, SharedBoard({'task':'QPU'}), **args)
            assert artifact.kind == 'decision' and refs == []
        else:
            with pytest.raises(ValueError):
                await execute_assignment(a, SharedBoard({'task':'QPU'}), **args)


@pytest.mark.asyncio
async def test_orchestrator_lead_failure_falls_back_before_answer_stream():
    from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator
    async def failed(**kwargs):
        raise ValueError('bad generated plan')
        yield
    class Draft:
        completion = None
        answered_model = 'test'
        async def execute(self, *args, **kwargs):
            yield 'Fallback answer'
    with patch('app.agents.core.multi_agent_orchestrator.get_settings', return_value=SimpleNamespace(agent_lead_mode='active', jev_enabled=False)), patch('app.agents.core.lead_agent.prepare_collaboration', failed), patch('app.agents.core.multi_agent_orchestrator.DraftingSpecialist', return_value=Draft()):
        output = [item async for item in MultiAgentOrchestrator('s','t').run_multi_agent_flow('Hello', None, 'general_chat', {})]
    assert output[-1] == 'Fallback answer'
    assert any(isinstance(e, AgentEvent) and e.data.get('step') == 'lead_fallback' for e in output)

@pytest.mark.asyncio
async def test_active_handoff_drives_writer_and_does_not_repeat_retrieval():
    from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator
    calls = []
    async def prepared(**kwargs):
        yield {'context': 'Evidence [1] plus selected analysis', 'memory': '', 'history': [],
               'references': [{'id': 'source1'}], 'critique': False,
               'answer_role': 'QPU tradeoff explainer', 'trace': {'mode': 'lead'}}
    class Draft:
        completion = None
        answered_model = 'test'
        async def execute(self, *args, **kwargs):
            calls.append((args, kwargs, self.role_label))
            yield 'Answer [1]'
    orchestrator = MultiAgentOrchestrator('s', 't')
    with patch('app.agents.core.multi_agent_orchestrator.get_settings', return_value=SimpleNamespace(agent_lead_mode='active', jev_enabled=False)), patch('app.agents.core.lead_agent.prepare_collaboration', prepared), patch('app.agents.core.multi_agent_orchestrator.DraftingSpecialist', return_value=Draft()), patch('app.agents.core.multi_agent_orchestrator.RetrievalSpecialist') as retrieval:
        output = [item async for item in orchestrator.run_multi_agent_flow('QPU', 7, 'knowledge_question', {}, memory_context='private unused learner context')]
    retrieval.assert_not_called()
    assert output[-1] == 'Answer [1]'
    assert calls[0][1] == {'memory_context': '', 'history': []}
    assert calls[0][2] == 'QPU tradeoff explainer'
    assert orchestrator.collected_references == [{'id': 'source1'}]
    assert orchestrator.answer_memory_context == ''


@pytest.mark.asyncio
async def test_parent_cancellation_cleans_up_all_workers():
    candidate = plan([assignment('work_one'), assignment('work_two')])
    started = asyncio.Event()
    count = 0
    closed = []
    async def execute(a, board, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.append(a.id)
    async def consume():
        return [item async for item in prepare_collaboration(**ARGS)]
    with patch('app.agents.core.lead_agent.make_lead_plan', new=AsyncMock(return_value=candidate)), patch('app.agents.core.lead_agent.execute_assignment', execute):
        task = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert set(closed) == {'work_one', 'work_two'}

@pytest.mark.asyncio
async def test_lead_generation_receives_full_contract_and_parses_real_structured_boundary():
    candidate = plan()
    with patch('app.core.llm.chat_complete', new=AsyncMock(return_value=candidate.model_dump_json())) as generate:
        actual = await make_lead_plan('QPU', SharedBoard({'task': 'QPU'}),
            require_evidence=False, quality_gate=False, system_one_enabled=False)
    assert actual.assignments[0].executor == 'llm'
    prompt = generate.call_args.kwargs['messages'][0]['content']
    assert 'Return only one JSON object' in prompt
    assert '"consumes"' in prompt and '"answer_inputs"' in prompt
    assert generate.await_count == 1
