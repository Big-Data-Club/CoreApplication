"""Small-model context must keep the dialogue that explains a follow-up."""
import json
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.core.prompt_budget import pack_agent_messages, remaining_memory_budget
from app.agents.core.planner import ExecutionPlan, generate_plan
from app.agents.core.conversation_task import ConversationTask
from app.agents.core.planner_budget import pack_planner_messages
from app.core.llm_gateway.errors import ContextLengthError
from app.core.llm_gateway.token_budget import estimate_request_tokens

MPI = "MPI_Scatterv sendcounts=[1,2,1], displs=[0,1,3], sendbuf=[7,8,9,10]. Rank 1 nhận gì?"


def test_compact_instructions_before_discarding_followup_facts():
    history = [{"role": "user", "content": MPI}, {"role": "assistant", "content": "Rank 1 nhận [8,9]."}]
    messages = [{"role": "system", "content": "Repeated guidance. " * 400}, *history,
                {"role": "user", "content": "Vậy rank 2 thì sao?"}]
    packed = pack_agent_messages(messages, {}, 650, compact_system_prompt="Resolve follow-ups from dialogue; ask if facts are missing.")
    assert history[0] in packed and history[1] in packed
    assert estimate_request_tokens(packed) <= 650
    assert messages[0]["content"].startswith("Repeated guidance.")


def test_compact_retrieval_before_discarding_recent_conversation():
    history = [{"role": "user", "content": MPI}, {"role": "assistant", "content": "Rank 1 nhận [8,9]."}]
    messages = [{"role": "system", "content": "Preserve facts."}, *history,
                {"role": "user", "content": "Vậy rank 2 thì sao?"},
                {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "search_course_materials", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": json.dumps({"data": {"chunks": [{"text": "Large background reading. " * 900}]}})}]
    packed = pack_agent_messages(messages, {}, 750)
    assert history[0] in packed
    assert packed[-1]["tool_call_id"] == packed[-2]["tool_calls"][0]["id"]
    assert estimate_request_tokens(packed) <= 750


@pytest.mark.parametrize("limit", [2200, 4500, 20000])
@pytest.mark.asyncio
async def test_planner_fits_real_payload_and_protects_current_request(limit):
    courses = {"courses": [{"id": i, "title": "Course title " * 30} for i in range(40)]}
    history = [{"role": "user", "content": MPI, "pinned": True},
               {"role": "assistant", "content": "Unneeded prose " * 400}]
    with patch("app.agents.core.planner.chat_complete_structured", new=AsyncMock(return_value=ExecutionPlan())) as llm:
        await generate_plan("Vậy rank 2 thì sao?", active_courses=courses, current_course_id=27, history=history)
    messages = llm.await_args.kwargs["messages"]
    original = deepcopy(messages)
    packed = llm.await_args.kwargs["message_packer"](messages, {}, limit)
    payload = json.loads(packed[1]["content"])
    assert estimate_request_tokens(packed) <= limit
    assert payload["message"] == "Vậy rank 2 thì sao?"
    assert any(item["content"] == MPI for item in payload["history"])
    assert any(course["id"] == 27 for course in payload["courses"])
    assert messages == original


def test_planner_cannot_silently_slice_oversized_current_message():
    messages = [{"role": "system", "content": "Large guidance " * 500},
                {"role": "user", "content": json.dumps({"message": "Exact input " * 2000, "history": [], "courses": []})}]
    with pytest.raises(ContextLengthError):
        pack_planner_messages(messages, {}, 2200)
    assert "Exact input " * 2000 in json.loads(messages[1]["content"])["message"]


def test_planned_tool_is_never_removed_to_make_old_history_fit():
    tools = [{"type": "function", "function": {"name": "generate_content_draft", "description": "Schema " * 900}}]
    with pytest.raises(ContextLengthError):
        pack_agent_messages([{"role": "system", "content": "Drafts require approval."},
                             {"role": "user", "content": "Create the draft"}],
                            {"tools": tools}, 600, required_tools=frozenset({"generate_content_draft"}))


def test_memory_headroom_tracks_input_cost_and_selected_tier():
    messages = [{"role": "system", "content": "Policy"}, {"role": "user", "content": MPI}]
    small = remaining_memory_budget(3000, messages, {})
    large = remaining_memory_budget(12000, messages, {})
    tools = {"tools": [{"type": "function", "function": {"name": "read", "description": "schema " * 300}}]}
    assert 0 < small < large
    assert remaining_memory_budget(3000, messages, tools) < small
    assert remaining_memory_budget(3000, [{"role": "user", "content": "source " * 5000}], {}) == 0


@pytest.mark.asyncio
async def test_planner_cannot_reference_dialogue_removed_by_actual_key_budget():
    async def complete(**kwargs):
        packed = kwargs["message_packer"](kwargs["messages"], {}, 2200)
        assert [m["message_id"] for m in json.loads(packed[1]["content"])["history"]] == [1]
        return ExecutionPlan(conversation_task=ConversationTask(relation="continuation", source_message_ids=[0, 1, 999]))
    with patch("app.agents.core.planner.chat_complete_structured", side_effect=complete):
        plan = await generate_plan("Vậy rank 2 thì sao?", history=[
            {"role": "user", "content": "Unrelated old topic " * 300},
            {"role": "user", "content": MPI, "pinned": True},
        ])
    assert plan.conversation_task.source_message_ids == [1]


@pytest.mark.asyncio
async def test_small_planner_keeps_last_clarification_for_a_short_casual_reply():
    history = [{"role": "user", "content": "Older unrelated discussion " * 700},
               {"role": "user", "content": "Mình muốn trò chuyện về kế hoạch học."},
               {"role": "assistant", "content": "Bạn muốn mình dùng tiếng Việt hay tiếng Anh?"}]
    with patch("app.agents.core.planner.chat_complete_structured", new=AsyncMock(return_value=ExecutionPlan())) as llm:
        await generate_plan("Tiếng Anh nhé", history=history)
    packed = llm.await_args.kwargs["message_packer"](llm.await_args.kwargs["messages"], {}, 2200)
    assert [item["content"] for item in json.loads(packed[1]["content"])["history"]] == [item["content"] for item in history[1:]]
