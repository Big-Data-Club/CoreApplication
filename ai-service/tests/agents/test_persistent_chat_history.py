from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
import pytest
from pydantic import ValidationError
from app.agents.memory.history import load_history
from app.agents.memory.message_store import MessageStore
from app.agents.core.orchestrator import handle_chat_message
from app.agents.events import AgentEvent, AgentEventType
from app.api.agent_router import FeedbackRequest, submit_message_feedback

@pytest.mark.asyncio
@pytest.mark.parametrize('cached', [[], RuntimeError('cache down'), [{'role': 'user', 'content': 'old'}]])
async def test_durable_history_survives_expiry_outage_and_stale_cache(cached):
    turns = [{'role': 'user', 'content': 'QPU'}, {'role': 'assistant', 'content': 'latency'}]
    with patch('app.agents.memory.history.stm.get_window', new=AsyncMock(return_value=cached if isinstance(cached, list) else [], side_effect=cached if isinstance(cached, Exception) else None)), patch('app.agents.memory.history.message_store.get_recent_context', new=AsyncMock(return_value=turns)) as read:
        result = await load_history('session', 42)
    assert result['messages'] == turns
    assert result['source'] == 'persistent'
    read.assert_awaited_once_with('session', 42, 30)

@pytest.mark.asyncio
async def test_outage_is_not_new_conversation():
    with patch('app.agents.memory.history.stm.get_window', new=AsyncMock(side_effect=RuntimeError)), patch('app.agents.memory.history.message_store.get_recent_context', new=AsyncMock(side_effect=RuntimeError)):
        assert (await load_history('s', 42))['status'] == 'unavailable'

@pytest.mark.asyncio
async def test_partial_answer_persisted_on_error():
    async def stream(**kwargs):
        yield AgentEvent(type=AgentEventType.TEXT_DELTA, data={'delta': 'Cloud QPU'}, session_id='s')
        yield AgentEvent(type=AgentEventType.ERROR, data={'error': 'Disconnected'}, session_id='s')
    with patch('app.agents.core.orchestrator.mtm.get_session', new=AsyncMock(return_value={'user_id': 42, 'agent_type': 'mentor', 'context': {}, 'turn_count': 3})), patch('app.agents.core.orchestrator.run_react_loop', stream), patch('app.agents.memory.message_store.message_store.save_message', new=AsyncMock(return_value=99)) as save, patch('app.agents.memory.stm.stm.append', new=AsyncMock()):
        events = [e async for e in handle_chat_message(42, 'mentor', 'continue', session_id='s', chat_mode='flash')]
    save.assert_awaited_once()
    assert save.call_args.args[2] == 'Cloud QPU'
    assert save.call_args.kwargs['metadata']['incomplete']
    assert events[-1].data['message_id'] == 99

@pytest.mark.asyncio
async def test_foreign_session_cannot_reach_model():
    with patch('app.agents.core.orchestrator.mtm.get_session', new=AsyncMock(return_value={'user_id': 7, 'agent_type': 'mentor'})), patch('app.agents.core.orchestrator.run_react_loop') as run:
        events = [e async for e in handle_chat_message(42, 'mentor', 'hello', session_id='s')]
    run.assert_not_called()
    assert events[-1].data['code'] == 'session_not_found'

@pytest.mark.asyncio
@pytest.mark.parametrize('rating', ['like', 'dislike', None])
async def test_feedback_write_clear_and_read(rating):
    conn = AsyncMock()
    conn.fetchrow.return_value = {'id': 12}
    conn.fetch.return_value = [{'id': 12, 'role': 'assistant', 'content': 'QPU', 'metadata': {}, 'created_at': None, 'feedback': rating}]
    @asynccontextmanager
    async def connection():
        yield conn
    with patch('app.api.agent_router._verify_secret'), patch('app.core.database.get_ai_conn', connection), patch('app.agents.memory.message_store.get_ai_conn', connection):
        result = await submit_message_feedback(FeedbackRequest(message_id=12, session_id='s', rating=rating), 42)
        messages = await MessageStore().get_messages('s', user_id=42)
    assert result['rating'] == rating == messages[0]['feedback']
    assert "m.role = 'assistant'" in conn.fetchrow.call_args.args[0]
    assert conn.fetchrow.call_args.args[1:] == (12, 's', 42)
    assert ('DELETE' if rating is None else 'ON CONFLICT') in conn.execute.call_args.args[0]
    sql, *args = conn.fetch.call_args.args
    assert 'ORDER BY m.id DESC LIMIT' in sql and 'ORDER BY id ASC' in sql
    assert 's.user_id = $3' in sql and args == ['s', 100, 42]

@pytest.mark.asyncio
async def test_feedback_rejects_foreign_message():
    from fastapi import HTTPException
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    @asynccontextmanager
    async def connection():
        yield conn
    with patch('app.api.agent_router._verify_secret'), patch('app.core.database.get_ai_conn', connection):
        with pytest.raises(HTTPException) as error:
            await submit_message_feedback(FeedbackRequest(message_id=12, session_id='s', rating='like'), 42)
    assert error.value.status_code == 404
    conn.execute.assert_not_awaited()

def test_missing_rating_cannot_clear_feedback():
    with pytest.raises(ValidationError):
        FeedbackRequest(message_id=12, session_id='s')

@pytest.mark.asyncio
async def test_cache_write_failure_does_not_prevent_persistent_write():
    from app.agents.memory.stm import STMemory
    with patch('app.agents.memory.stm._get_redis', side_effect=RuntimeError('cache unavailable')):
        await STMemory().append('s', 'user', 'Remember QPU')
