"""Regression tests for Deep answers cut mid-table or at the synthesis cap."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.agents.core.answer_completion import (
    AnswerCompletion, continue_answer, _request_answer_continuation,
)
from app.agents.core.react_loop import _synthesize_after_tools, _stream_synthesis_after_tools
from app.agents.core.sub_agents import DraftingSpecialist
from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator
from app.agents.core.sse_keepalive import with_keepalive
from app.agents.events import AgentEvent, AgentEventType
from app.core.llm_gateway import ChatRequest, TASK_AGENT_REACT
from app.core.llm_gateway.token_budget import estimate_tokens


class Gateway:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        assert request.extra == {}
        text, terminal = self.responses.pop(0)
        yield text, None, {"model": "test-model"}
        if isinstance(terminal, BaseException):
            raise terminal
        if terminal is not None:
            yield None, None, {"choices": [{"finish_reason": terminal}]}


@pytest.fixture
def limits():
    cfg = SimpleNamespace(agent_deep_max_answer_continuations=12,
        agent_deep_max_answer_tokens=24000, agent_deep_answer_chunk_tokens=4096,
        agent_max_answer_continuations=3, agent_max_continuation_tokens=6000)
    with patch("app.agents.core.answer_completion.get_settings", return_value=cfg):
        yield cfg


def request():
    return ChatRequest(task=TASK_AGENT_REACT, messages=[{"role": "user", "content": "Thuê cloud QPU?"}])


async def collect(gateway, state, mode="deep"):
    return [part async for part in continue_answer(gateway, request(), state, mode)]


@pytest.mark.asyncio
async def test_deep_can_continue_beyond_three_calls_and_finish_table(limits):
    initial = "| Yếu tố | Gợi ý |\n|---|---|\n| Latency | Độ trễ từ"
    gateway = Gateway((" vài mili giây", "length"), (" đến nhiều giây", "length"),
                      (" tùy kết nối", "length"), (" và hàng đợi. |", "stop"))
    state = AnswerCompletion(initial, "length")
    parts = await collect(gateway, state)
    assert state.text == initial + "".join(parts)
    assert state.text.endswith("và hàng đợi. |")
    assert state.continuations == 4 and not state.incomplete
    assert all(req.max_tokens == 4096 for req in gateway.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["stop", "end_turn", "stop_sequence", "content_filter", "safety"])
async def test_finished_or_filtered_answers_are_not_extended(limits, terminal):
    gateway = Gateway()
    state = AnswerCompletion("Answer", terminal)
    assert await collect(gateway, state) == []
    assert not gateway.requests
    assert state.incomplete == (terminal in ("content_filter", "safety"))


@pytest.mark.asyncio
async def test_standard_preserves_three_call_limit(limits):
    gateway = Gateway(*[(f" additional segment {n}.", "length") for n in range(4)])
    state = AnswerCompletion("Initial", "length")
    await collect(gateway, state, "standard")
    assert state.continuations == 3 and state.incomplete
    assert state.stop_cause == "answer_budget_exhausted"
    assert "lượt hoàn tất cuối" in str(gateway.requests[-1].messages)


@pytest.mark.asyncio
async def test_remaining_budget_caps_next_request_without_slicing_answer(limits):
    limits.agent_deep_max_answer_tokens = 1100
    state = AnswerCompletion("x" * 2160, "length")  # 900 estimated tokens
    gateway = Gateway((" Complete.", "stop"))
    await collect(gateway, state)
    assert gateway.requests[0].max_tokens == 200
    assert state.text == "x" * 2160 + " Complete."
    assert not state.incomplete


@pytest.mark.asyncio
async def test_exhausted_budget_does_not_call_provider(limits):
    limits.agent_deep_max_answer_tokens = 1024
    state = AnswerCompletion("x" * 3000, "length")
    gateway = Gateway()
    assert await collect(gateway, state) == []
    assert state.incomplete and state.stop_cause == "answer_budget_exhausted"


@pytest.mark.asyncio
@pytest.mark.parametrize("repeated", ["", "Already written answer."])
async def test_no_progress_stops_without_claiming_completion(limits, repeated):
    gateway = Gateway((repeated, "stop"))
    state = AnswerCompletion("Already written answer.", "length")
    assert await collect(gateway, state) == []
    assert len(gateway.requests) == 1 and state.incomplete


@pytest.mark.asyncio
async def test_interrupted_continuation_keeps_partial_text_and_resumes(limits):
    gateway = Gateway((" tiếp nối một", httpx.ReadError("connection reset")), (" phần còn lại.", "stop"))
    state = AnswerCompletion("Đầu", "length")
    await collect(gateway, state)
    assert state.text == "Đầu tiếp nối một phần còn lại."
    assert not state.incomplete


@pytest.mark.asyncio
async def test_missing_finish_reason_is_recovered(limits):
    gateway = Gateway((" phần hoàn tất.", "stop"))
    state = AnswerCompletion("Đầu", None)
    await collect(gateway, state)
    assert not state.incomplete and state.continuations == 1


@pytest.mark.asyncio
async def test_persistent_network_failures_are_bounded(limits):
    gateway = Gateway(*[("", httpx.ReadError("reset")) for _ in range(4)])
    state = AnswerCompletion("Partial", "stream_interrupted")
    await collect(gateway, state)
    assert len(gateway.requests) == 2
    assert state.stop_cause == "stream_retry_exhausted" and state.incomplete


@pytest.mark.asyncio
async def test_cancelled_request_is_not_retried(limits):
    gateway = Gateway(("", asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await collect(gateway, AnswerCompletion("Partial", "length"))
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_continuation_strips_tool_protocol_and_does_not_reuse_stale_packer(limits):
    req = request()
    req.messages += [
        {"role": "assistant", "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a", "content": "Evidence"},
    ]
    req.extra = {"tools": [{"type": "function"}]}
    req.message_packer = lambda *_: [{"role": "user", "content": "Old prompt"}]
    gateway = Gateway((" complete.", "stop"))
    await _request_answer_continuation(gateway, req, "Partial", question="Thuê QPU?")
    followup = gateway.requests[0]
    packed = followup.message_packer(followup.messages, {}, 10000)
    assert "Tiếp tục chính xác" in str(packed) and "Thuê QPU?" in str(packed)
    assert all(m["role"] != "tool" and "tool_calls" not in m and "tool_call_id" not in m for m in packed)
    assert req.extra != {}  # caller's request is not mutated


@pytest.mark.asyncio
async def test_small_prompt_budget_preserves_question_tail_and_selects_evidence(limits):
    import json
    from app.core.llm_gateway.token_budget import estimate_request_tokens
    req = request()
    req.messages.append({"role": "tool", "content": json.dumps({"data": {"chunks": [
        {"id": "source-1", "text": "Evidence " * 3000},
    ]}})})
    gateway = Gateway((" done.", "stop"))
    previous = "Earlier answer " * 2000 + "TABLE_ROW_END"
    await _request_answer_continuation(gateway, req, previous, question="Thuê QPU?")
    followup = gateway.requests[0]
    packed = followup.message_packer(followup.messages, {}, 1500)
    assert "Thuê QPU?" in packed[0]["content"]
    assert "TABLE_ROW_END" in packed[0]["content"]
    assert "Evidence" in str(packed) and "evidence" in str(packed).lower()
    assert estimate_request_tokens(packed, {}) <= 1500
    assert all(m["role"] != "tool" for m in packed)


@pytest.mark.asyncio
async def test_final_synthesis_continues_in_deep(limits):
    gateway = Gateway(("Độ trễ từ", "length"), (" vài mili giây. |", "stop"))
    answer, reason = await _synthesize_after_tools(gateway, [], "QPU?", mode="deep")
    assert answer == "Độ trễ từ vài mili giây. |" and reason == "stop"
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_synthesis_yields_first_segment_before_requesting_continuation(limits):
    gateway = Gateway(("Partial", "length"), (" complete.", "stop"))
    state = AnswerCompletion("", None)
    stream = _stream_synthesis_after_tools(gateway, [], "QPU?", state, mode="deep")
    assert await anext(stream) == "Partial"
    assert len(gateway.requests) == 1
    assert await anext(stream) == " complete."
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert not state.incomplete


@pytest.mark.asyncio
async def test_deep_draft_and_revision_use_completion_policy(limits):
    gateway = Gateway(("<thought>private</thought>Độ trễ từ", "length"),
                      (" vài mili giây. |", "stop"), ("Revised.", "stop"))
    draft = DraftingSpecialist("session", "turn")
    with patch("app.agents.core.sub_agents.get_gateway", return_value=gateway):
        events = [ev async for ev in draft.execute("QPU?", "Evidence")]
        assert events[-1] == "Độ trễ từ vài mili giây. |"
        visible = "".join(ev.data.get("delta", "") for ev in events if isinstance(ev, AgentEvent))
        assert visible == events[-1] and "private" not in visible
        assert draft.completion.continuations == 1 and not draft.completion.incomplete
        revised = [ev async for ev in draft.execute("QPU?", "Evidence", "Fix it")]
        assert revised[-1] == "Revised."
        assert draft.completion.continuations == 0


@pytest.mark.asyncio
async def test_orchestrator_propagates_incomplete_draft(limits):
    limits.agent_deep_max_answer_continuations = 0
    gateway = Gateway(("Partial draft", "length"))
    orchestrator = MultiAgentOrchestrator("session", "turn")
    with patch("app.agents.core.sub_agents.get_gateway", return_value=gateway):
        events = [ev async for ev in orchestrator.run_multi_agent_flow(
            "QPU?", None, "general_chat", {"depth_signal": 0.8})]
    assert events[-1] == "Partial draft"
    assert orchestrator.answer_incomplete
    assert orchestrator.answer_finish_reason == "length"
    assert not any(isinstance(ev, AgentEvent) and ev.type == AgentEventType.CRITIQUE_PHASE for ev in events)


@pytest.mark.asyncio
async def test_keepalive_does_not_cancel_slow_generator_and_closes_on_disconnect():
    release, closed = asyncio.Event(), asyncio.Event()
    async def source():
        try:
            await release.wait()
            yield "data: answer\n\n"
            await asyncio.Event().wait()
        finally:
            closed.set()
    stream = with_keepalive(source(), interval=0.001)
    assert await anext(stream) == ": keepalive\n\n"
    assert not closed.is_set()
    release.set()
    assert await anext(stream) == "data: answer\n\n"
    assert await anext(stream) == ": keepalive\n\n"
    await stream.aclose()
    assert closed.is_set()
