from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.llm_gateway.response_content import split_content, provider_thinking
from app.agents.core.sub_agents import DraftingSpecialist
from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator
from app.agents.events import AgentEvent, AgentEventType


def test_structured_thinking_never_becomes_answer_text():
    blocks = [
        {"type": "thinking", "thinking": [{"type": "text", "text": "Check indices."}], "closed": True},
        {"type": "text", "text": "Rank 2 receives [10]."},
        {"type": "image_url", "image_url": "private-image"},
        None,
    ]
    assert split_content(blocks) == ("Rank 2 receives [10].", "Check indices.")
    assert provider_thinking({"choices": [{"message": {"content": blocks}}]}) == "Check indices."
    assert provider_thinking(SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(reasoning_content="SDK reasoning"), message=None,
    )])) == "SDK reasoning"
    assert split_content(None) == ("", "")
    assert provider_thinking({"choices": []}) == ""


@pytest.mark.asyncio
async def test_multistep_provider_reasoning_is_recorded_without_polluting_answer():
    class Gateway:
        async def stream(self, req):
            yield "", None, {"choices": [{"delta": {"content": [
                {"type": "thinking", "thinking": [{"type": "text", "text": "Verify displacement."}]},
            ]}}]}
            yield "[10]", None, {"choices": [{"delta": {"content": "[10]"}, "finish_reason": "stop"}]}

    draft = DraftingSpecialist("session", "turn")
    orchestrator = MultiAgentOrchestrator("session", "turn")
    orchestrator._record_event(AgentEvent(type=AgentEventType.SUBAGENT_SPAWN,
        data={"subagent_id": draft.subagent_id, "role": "draft", "task": "answer"},
        session_id="session", turn_id="turn"))
    with patch("app.agents.core.sub_agents.get_gateway", return_value=Gateway()):
        events = [ev async for ev in draft.execute("Rank 2?", "MPI Scatterv")]
    assert events[-1] == "[10]"
    thinking = [ev for ev in events if isinstance(ev, AgentEvent) and ev.type == AgentEventType.THINKING]
    assert len(thinking) == 1
    for ev in events:
        if isinstance(ev, AgentEvent):
            orchestrator._record_event(ev)
    assert "Verify displacement." in orchestrator.multi_agent_logs[0]["thinking"]
    visible = "".join(ev.data.get("delta", "") for ev in events
        if isinstance(ev, AgentEvent) and ev.type == AgentEventType.SUBAGENT_THINK)
    assert visible == "[10]"
