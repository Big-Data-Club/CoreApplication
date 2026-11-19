"""Replay a resumed session through the real answer packer, without live models."""
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.core.conversation_task import ConversationTask
from app.agents.core.planner import ExecutionPlan, RetrievalStrategy
from app.agents.core.react_loop import run_react_loop
from app.agents.events import AgentEventType
from app.agents.memory.conversation_state import advance_dialogue
from app.core.llm_gateway.gateway import LLMGateway
from app.core.llm_gateway.token_budget import estimate_request_tokens

MPI = "MPI_Scatterv sendcounts=[1,2,1], displs=[0,1,3], sendbuf=[7,8,9,10]. Rank 1 nhận gì?"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["standard", "flash"])
@pytest.mark.parametrize("budget", [3000, 6000, 20000])
@pytest.mark.parametrize("thinking_only", [False, True])
async def test_resumed_dialogue_preserves_facts_and_recovers_thinking_only_response(mode, budget, thinking_only):
    state = advance_dialogue(None, MPI, ConversationTask(goal="Discuss MPI"), [], 27)
    plan = ExecutionPlan(intent="general_chat", requires_tool=False, selected_tools=[],
        retrieval_strategy=RetrievalStrategy(scope="none"),
        conversation_task=ConversationTask(relation="continuation", goal="Discuss rank 2", source_message_ids=[0]))
    requests = []
    model = SimpleNamespace(context_window=32768, adapter_type="test", config={"request_token_budget": budget})
    actual_gateway = LLMGateway()

    async def stream(request):
        prepared, output = actual_gateway._prepare_request(request, model, request.max_tokens, None)
        assert estimate_request_tokens(prepared.messages, prepared.extra) + output <= budget
        requests.append(prepared)
        if thinking_only and len(requests) == 1:
            yield "", None, {"model": "offline", "choices": [{"delta": {"reasoning_content": "Check indices."}, "finish_reason": "stop"}]}
            return
        yield "Rank 2 nhận [10].", None, {"model": "offline", "choices": [{"finish_reason": "stop"}]}

    async def no_title(**kwargs):
        if False:
            yield None

    gateway = SimpleNamespace(stream=stream, preview_request_budget=AsyncMock(return_value=budget))
    with ExitStack() as stack:
        def mock(name, **kwargs):
            return stack.enter_context(patch(name, **kwargs))
        mock("app.agents.core.react_loop.load_active_courses", new=AsyncMock(return_value={"courses": [{"id": 27, "title": "MPI", "nodes": []}]}))
        mock("app.agents.tools.execution_policy.authorize_course", new=AsyncMock(return_value=True))
        mock("app.agents.memory.history.load_history", new=AsyncMock(return_value={
            "messages": [{"role": "assistant", "content": "Recent answer without the original problem."}],
            "source": "persistent", "status": "available"}))
        planner = mock("app.agents.core.planner_accelerator.plan_standard_turn", new=AsyncMock(return_value=plan))
        mock("app.agents.core.react_loop.get_gateway", return_value=gateway)
        async def memory(**kwargs):
            return {"prompt_section": "", "stm_messages": kwargs["history_window"]["messages"],
                    "token_estimate": 0, "raw": {"mtm": {}}}
        builder = mock("app.agents.core.react_loop.context_builder.build", new=AsyncMock(side_effect=memory))
        mock("app.agents.core.react_loop.mtm.push_recent_course", new=AsyncMock())
        mock("app.agents.core.react_loop.stm.append", new=AsyncMock())
        mock("app.agents.core.react_loop.message_store.save_message", new=AsyncMock(return_value=202))
        save_state = mock("app.agents.core.react_loop.mtm.save_conversation_state", new=AsyncMock())
        mock("app.agents.core.react_loop.get_tool_schemas", return_value=[])
        execute = mock("app.agents.core.react_loop.execute_tool", new=AsyncMock())
        mock("app.agents.core.react_loop._trigger_post_turn_consolidation", new=AsyncMock())
        mock("app.agents.core.react_loop._maybe_emit_title_update", new=no_title)
        events = [event async for event in run_react_loop(session_id="session", user_id=42,
            agent_type="mentor", user_message="Vậy rank 2 thì sao?", course_id=27, chat_mode=mode,
            session_context={"conversation_state": state})]

    assert len(requests) == (2 if thinking_only else 1)
    assert any(MPI in m.get("content", "") for m in requests[0].messages if m["role"] == "user")
    assert any(event.type == AgentEventType.DONE for event in events)
    execute.assert_not_awaited()
    save_state.assert_awaited_once()
    assert save_state.await_args.args[:2] == ("session", 42)
    assert save_state.await_args.args[-1] == 202
    if mode == "flash":
        planner.assert_not_awaited()
        builder.assert_not_awaited()
    else:
        assert planner.await_args.kwargs["history"][0]["content"] == MPI
