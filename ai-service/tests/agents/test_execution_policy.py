"""Exercise the real execution boundary; no model output grants authority."""
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.core.planner import ExecutionPlan
from app.agents.core.conversation_task import DataIssue
from app.agents.tools.base_tool import ToolResult
from app.agents.tools.registry import execute_tool, get_tool_by_name, get_tool_schemas
from app.agents.tools.execution_policy import DIRECT_WRITE_TOOLS


def schema_names(agent_type):
    return {schema["function"]["name"] for schema in get_tool_schemas(agent_type)}


def test_direct_writes_are_not_disclosed_to_chat_but_remain_registered_for_mcp():
    assert not schema_names("teacher") & DIRECT_WRITE_TOOLS
    assert not schema_names("mentor") & DIRECT_WRITE_TOOLS
    assert get_tool_by_name("mcp_create_lesson") is not None
    assert "generate_content_draft" in schema_names("teacher")


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [0, None, True, "42"])
async def test_invalid_identity_never_executes(user_id):
    tool = get_tool_by_name("recall_conversation")
    with patch.object(tool, "execute", new=AsyncMock()) as execute:
        result = await execute_tool(tool.name, {}, user_id=user_id)
    assert result.data["error"] == "missing_identity"
    execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"_user_id": 7}, {"_course_id": 99}, {"_session_id": "foreign"},
    {"_content_id": 99}, {"_node_id": 99}, {"execution_plan": {}},
    {"mcp_write_authorized": True}, {"confirmed": True},
])
async def test_model_cannot_inject_internal_context_or_approval(arguments):
    tool = get_tool_by_name("recall_conversation")
    with patch.object(tool, "execute", new=AsyncMock()) as execute:
        result = await execute_tool(tool.name, arguments, user_id=42, session_id="own")
    assert result.status == "error"
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_name_cannot_cross_agent_role_or_current_disclosure():
    teacher = get_tool_by_name("generate_content_draft")
    with patch.object(teacher, "execute", new=AsyncMock()) as execute:
        result = await execute_tool(teacher.name, {"topic": "MPI"}, user_id=42, agent_type="mentor")
    assert result.data["error"] == "tool_forbidden"
    execute.assert_not_awaited()
    result = await execute_tool("recall_conversation", {}, user_id=42, allowed_tools=frozenset())
    assert result.data["error"] == "tool_not_disclosed"


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments,context_course,error", [
    ({"query": "MPI"}, None, "course_id_required"),
    ({"query": "MPI", "course_id": 99}, 27, "course_scope_mismatch"),
    ({"query": "MPI", "course_id": True}, None, "invalid_course_id"),
    ({"query": "MPI", "course_id": "27"}, None, "invalid_course_id"),
])
async def test_course_scope_is_never_invented_or_silently_replaced(arguments, context_course, error):
    with patch("app.agents.tools.registry.authorize_course", new=AsyncMock()) as access:
        result = await execute_tool("search_course_materials", arguments, user_id=42, course_id=context_course)
    assert result.data["error"] == error
    access.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name,agent_type,args,owner", [
    ("search_course_materials", "mentor", {"query": "MPI", "course_id": 27}, False),
    ("mcp_course_knowledge_read", "teacher", {"course_id": 27, "action": "outline"}, False),
    ("generate_content_draft", "teacher", {"topic": "MPI", "course_id": 27}, True),
])
async def test_revoked_course_access_is_checked_at_execution(name, agent_type, args, owner):
    tool = get_tool_by_name(name)
    with (
        patch.object(tool, "execute", new=AsyncMock()) as execute,
        patch("app.agents.tools.registry.authorize_course", new=AsyncMock(return_value=False)) as access,
    ):
        result = await execute_tool(name, args, user_id=42, agent_type=agent_type)
    assert result.data["error"] == "course_forbidden"
    access.assert_awaited_once_with(42, 27, owner_required=owner)
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_read_uses_copied_server_context_and_remains_read_scoped():
    tool = get_tool_by_name("search_course_materials")
    args = {"query": "MPI", "course_id": 27}
    with (
        patch.object(tool, "execute", new=AsyncMock(return_value=ToolResult(status="success", data={}))) as execute,
        patch("app.agents.tools.registry.authorize_course", new=AsyncMock(return_value=True)),
    ):
        result = await execute_tool(tool.name, args, user_id=42, session_id="own")
    assert result.status == "success"
    assert args == {"query": "MPI", "course_id": 27}
    assert execute.await_args.kwargs["_user_id"] == 42
    assert execute.await_args.kwargs["_course_id"] == 27
    assert execute.await_args.kwargs["_session_id"] == "own"
    assert execute.await_args.kwargs["_content_id"] is None


@pytest.mark.asyncio
async def test_model_confirmed_flag_cannot_publish_from_chat_but_mcp_write_lane_still_works():
    tool = get_tool_by_name("mcp_create_lesson")
    args = {"course_id": 27, "section_id": 4, "title": "MPI", "markdown": "text", "publish": True}
    with (
        patch.object(tool, "execute", new=AsyncMock(return_value=ToolResult(status="success", data={}))) as execute,
        patch("app.agents.tools.registry.authorize_course", new=AsyncMock(return_value=True)),
    ):
        rejected = await execute_tool(tool.name, args, user_id=42, agent_type="teacher")
        assert rejected.data["error"] == "human_review_required"
        execute.assert_not_awaited()
        accepted = await execute_tool(tool.name, args, user_id=42, agent_type="teacher", mcp_write_authorized=True)
    assert accepted.status == "success"
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_source_based_draft_must_preserve_original_problem_data():
    tool = get_tool_by_name("generate_content_draft")
    original = "sendcounts=[1,2,1], displs=[0,1,3], sendbuf=[7,8,9,10]"
    with patch.object(tool, "execute", new=AsyncMock(return_value=ToolResult(status="pending_human_approval", data={}))) as execute:
        rejected = await execute_tool(tool.name, {"topic": "MPI", "source_text": original.replace("7,8,9,10", "1,2,3,4")},
            user_id=42, agent_type="teacher", source_evidence=(original,))
        assert rejected.data["error"] == "source_mismatch"
        execute.assert_not_awaited()
        accepted = await execute_tool(tool.name, {"topic": "MPI", "source_text": original},
            user_id=42, agent_type="teacher", source_evidence=(original,))
    assert accepted.status == "pending_human_approval"


@pytest.mark.asyncio
async def test_missing_decisive_data_cannot_be_bypassed_by_model_tool_call():
    plan = ExecutionPlan(data_issues=[DataIssue(kind="missing", detail="sendbuf", question="What is sendbuf?")])
    with patch.object(get_tool_by_name("recall_conversation"), "execute", new=AsyncMock()) as execute:
        result = await execute_tool("recall_conversation", {}, user_id=42, execution_plan=plan)
    assert result.data["error"] == "unresolved_data"
    execute.assert_not_awaited()
