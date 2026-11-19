"""Regression coverage for small-budget dialogue and repeated read recovery."""
import json
from copy import deepcopy
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.core.conversation_task import ConversationTask
from app.agents.core.planner import ExecutionPlan, RetrievalStrategy
from app.agents.core.react_loop import run_react_loop
from app.agents.core.tool_gating import compact_tool_schemas
from app.agents.core.prompt_budget import pack_agent_messages
from app.agents.events import AgentEventType
from app.agents.memory.context_builder import ContextBuilder
from app.agents.tools.base_tool import ToolResult
from app.agents.tools.registry import get_tool_schemas
from app.core.llm_gateway.token_budget import estimate_tokens, estimate_request_tokens


def test_schema_compaction_preserves_rules_and_original_registry():
    schemas = get_tool_schemas("mentor")
    original = json.dumps(schemas, sort_keys=True)
    compact = compact_tool_schemas(schemas)
    assert estimate_tokens(compact) < estimate_tokens(schemas)
    assert json.dumps(schemas, sort_keys=True) == original

    def rules(value):
        if isinstance(value, dict):
            return {k: rules(v) for k, v in value.items() if k != "description"}
        return [rules(v) for v in value] if isinstance(value, list) else value
    assert rules(compact) == rules(schemas)


def test_unused_schemas_yield_before_retrieved_evidence_is_lost():
    evidence = json.dumps({"status": "success", "data": {"results": [{"snippet": "Monte Carlo " * 50}]}})
    tool = next(s for s in get_tool_schemas("mentor") if s["function"]["name"] == "recall_conversation")
    extra = {"tools": [tool, {"type": "function", "function": {
        "name": "unused", "description": "Unused instructions " * 500,
        "parameters": {"type": "object", "properties": {}},
    }}]}
    messages = [{"role": "system", "content": "Answer from the user's dialogue."},
        {"role": "user", "content": "Monte Carlo?"}, {"role": "assistant", "content": "Sampling."},
        {"role": "user", "content": "What did I ask?"},
        {"role": "assistant", "tool_calls": [{"id": "read", "type": "function",
            "function": {"name": "recall_conversation", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "read", "content": evidence}]
    packed = pack_agent_messages(messages, extra, 900)
    assert packed[-1]["content"] == evidence
    assert [s["function"]["name"] for s in extra["tools"]] == ["recall_conversation"]
    assert estimate_request_tokens(packed, extra) <= 900


@pytest.mark.asyncio
async def test_durable_preferences_cannot_starve_recent_dialogue():
    question = "giải thuật monte carlo hoạt động như thế nào"
    history = [{"role": "user", "content": question}, {"role": "assistant", "content": "Lấy mẫu và tính trung bình."}]
    memory = [{"kind": "preference", "key": f"style-{i}", "scope": "user",
        "value": "Giải thích từng bước với ví dụ cụ thể. " * 4,
        "source": "user_statement", "confidence": 1.0} for i in range(3)]
    with patch("app.agents.memory.context_builder.mtm.get_user_preferences", new=AsyncMock(return_value=[])):
        context = await ContextBuilder().build(user_id=42, session_id="owned", agent_type="mentor",
            query="tôi đã hỏi gì", intent_type="general_chat", memory_budget_tokens=240,
            history_window={"messages": history, "source": "persistent", "status": "available"},
            session_context={"memory_items": memory})
    assert any(m["role"] == "user" and m["content"] == question for m in context["stm_messages"])
    assert context["token_estimate"] <= 240


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,status", [("recall_conversation", "success"), ("search_course_materials", "error"),
                                       ("search_course_materials", "success")])
async def test_repeated_reads_synthesize_once_and_preserve_final_trace(tool, status):
    plan = ExecutionPlan(intent="knowledge_question", requires_tool=True, selected_tools=[tool],
        retrieval_strategy=RetrievalStrategy(scope="single_course"),
        conversation_task=ConversationTask(relation="continuation", goal="Review Monte Carlo"))
    history = [{"role": "user", "content": "giải thuật monte carlo hoạt động như thế nào"},
               {"role": "assistant", "content": "Lấy mẫu và tính trung bình."}]
    requests = []

    async def stream(req):
        requests.append(req)
        if req.message_packer:
            extra = deepcopy(req.extra)
            packed = req.message_packer(req.messages, extra, 4250)
            assert estimate_request_tokens(packed, extra) <= 4250
            assert any("monte carlo" in str(m.get("content", "")) for m in packed if m["role"] == "user")
        if req.extra.get("tools"):
            yield "", None, {"model": "retrieval-model", "choices": [{"delta": {"tool_calls": [{
                "index": 0, "id": f"call-{len(requests)}", "function": {"name": tool,
                "arguments": json.dumps({} if tool == "recall_conversation" else {"query": "Monte Carlo", "course_id": 99 if status == "error" else 27})},
            }]}, "finish_reason": "tool_calls"}]}
        else:
            assert any("monte carlo" in str(m.get("content", "")) for m in req.messages if m["role"] == "user")
            if tool == "search_course_materials" and status == "success":
                for index in range(6):
                    assert f"KEY_POINT_{index}" in str(req.messages)
            yield "", None, {"model": "final-model", "choices": [{"delta": {"reasoning_content": "Check prior dialogue."}}]}
            yield "Bạn đã hỏi về Monte Carlo.", None, {"model": "final-model", "choices": [{"finish_reason": "stop"}]}

    async def memory(**kwargs):
        assert kwargs["memory_budget_tokens"] >= 750
        selected, excerpted = ContextBuilder._fit_recent_dialogue(kwargs["history_window"]["messages"], kwargs["memory_budget_tokens"])
        assert selected
        return {"prompt_section": "", "stm_messages": selected, "token_estimate": 100,
                "raw": {"mtm": {}, "stm": {"available_count": len(history), "excerpted": excerpted}}}

    async def no_title(**kwargs):
        if False:
            yield None

    class Reader:
        def __init__(self):
            self.notes, self.examined_refs, self.missing_aspects = {}, set(), []

        async def read(self, sources, question):
            for row in sources:
                self.notes[row["ref"]] = [{"quote": row["text"][-80:], "aspect": "key concept"}]
                self.examined_refs.add(row["ref"])

        def snapshot(self):
            return {"reader_batches": 2, "reader_complete_sources": len(self.notes)}

    result = ToolResult(status=status, data={"results": [{"snippet": history[0]["content"]}]}
        if status == "success" else {"error": "course_scope_mismatch", "verified_course_id": 27},
        message="Found prior messages" if status == "success" else "course_scope_mismatch")
    if tool == "search_course_materials" and status == "success":
        result.data = {"chunks": [{"chunk_id": f"source-{index}", "text": "Background material. " * 500 + f" KEY_POINT_{index}",
            "similarity": .8} for index in range(6)]}
    with ExitStack() as stack:
        def mock(name, **kwargs):
            return stack.enter_context(patch(name, **kwargs))
        mock("app.agents.core.react_loop.load_active_courses", new=AsyncMock(return_value={"courses": [{"id": 27, "title": "RL", "nodes": []}]}))
        mock("app.agents.tools.execution_policy.authorize_course", new=AsyncMock(return_value=True))
        mock("app.agents.memory.history.load_history", new=AsyncMock(return_value={"messages": history, "source": "persistent", "status": "available"}))
        mock("app.agents.core.planner_accelerator.plan_standard_turn", new=AsyncMock(return_value=plan))
        mock("app.agents.core.react_loop.get_gateway", return_value=SimpleNamespace(stream=stream, preview_request_budget=AsyncMock(return_value=6000)))
        mock("app.agents.core.react_loop.SourceReader", new=Reader)
        mock("app.agents.core.react_loop.context_builder.build", new=AsyncMock(side_effect=memory))
        mock("app.agents.core.react_loop.mtm.push_recent_course", new=AsyncMock())
        mock("app.agents.core.react_loop.mtm.save_conversation_state", new=AsyncMock())
        mock("app.agents.core.react_loop.stm.append", new=AsyncMock())
        save = mock("app.agents.core.react_loop.message_store.save_message", new=AsyncMock(return_value=202))
        execute = mock("app.agents.core.react_loop.execute_tool", new=AsyncMock(return_value=result))
        mock("app.agents.core.react_loop._update_anchor_from_tool", new=AsyncMock())
        mock("app.agents.core.react_loop._trigger_post_turn_consolidation", new=AsyncMock())
        mock("app.agents.core.react_loop._maybe_emit_title_update", new=no_title)
        events = [ev async for ev in run_react_loop(session_id="owned", user_id=42,
            agent_type="mentor", user_message="tôi đã hỏi gì", course_id=27, chat_mode="standard", session_context={})]
    execute.assert_awaited_once()
    assert len(requests) == 3  # Two tool rounds, then one answer-only synthesis.
    assert len([ev for ev in events if ev.type == AgentEventType.TOOL_START]) == 1
    visible = "".join(ev.data["delta"] for ev in events if ev.type == AgentEventType.TEXT_DELTA)
    assert visible == "Bạn đã hỏi về Monte Carlo."
    assert "Check prior dialogue." not in visible
    assert any(ev.type == AgentEventType.THINKING and ev.data.get("delta") == "Check prior dialogue." for ev in events)
    metadata = save.call_args.args[3]
    assert metadata["thinking"] == "Check prior dialogue."
    assert metadata["model"] == "final-model" == events[-1].data["model"]
    assert len(metadata["toolActivities"]) == 1
    if status == "error":
        assert "course_scope_mismatch" not in metadata["toolActivities"][0]["message"]
    if tool == "search_course_materials" and status == "success":
        assert metadata["decisionExplanation"]["retrieval_evidence"]["reader_complete_sources"] == 6
        assert metadata["decisionExplanation"]["retrieval_evidence"]["prepared_sources"] == 6
