from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.core.react_loop import _synthesize_after_tools
from app.core.jev_decider import decide_decomposition
from app.core.llm_gateway.system_one import decide_system_one
from app.agents.tools.shared.assess_question import AssessQuestionTool
from app.agents.tools.base_tool import ToolResult
from mcp.tool_adapter import call_mcp_tool, get_mcp_tool_list


@pytest.mark.asyncio
async def test_jev_disabled_never_sends_question():
    registry = MagicMock(get_provider_by_code=AsyncMock())
    pool = MagicMock(lease=AsyncMock())
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=False)):
        assert await decide_system_one("Private learning question",
                                       registry=registry, key_pool=pool) is None
    registry.get_provider_by_code.assert_not_called()
    pool.lease.assert_not_called()


@pytest.mark.asyncio
async def test_jev_structured_response_and_no_key_in_result():
    settings = MagicMock(jev_enabled=True, jev_model="jev-1.13-free",
                         jev_timeout_seconds=1.0)
    registry = MagicMock(get_provider_by_code=AsyncMock(
        return_value=MagicMock(id=17, enabled=True)))
    pool = MagicMock(
        lease=AsyncMock(return_value=MagicMock(id=4, plaintext="test-placeholder")),
        record_success=AsyncMock(), record_generic_failure=AsyncMock(),
    )
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"answers": {"decompose": {"noul": 0.87}},
                                  "usage": {"input_tokens": 296, "output_tokens": 20}}
    client = AsyncMock()
    client.post.return_value = response
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    with patch("app.core.llm_gateway.system_one.get_settings", return_value=settings), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient", return_value=manager
    ), patch("app.core.llm_gateway.system_one.record_usage", new=AsyncMock()) as usage_log:
        result = await decide_system_one("How should scheduling work?",
                                         registry=registry, key_pool=pool)
    assert result == {"score": 0.87, "model": "jev-1.13-free"}
    assert "test-placeholder" not in str(result)
    pool.lease.assert_awaited_once_with(17)
    pool.record_success.assert_awaited_once_with(4, 316)
    assert usage_log.await_args.kwargs["provider_code"] == "opencode_zen"
    assert usage_log.await_args.kwargs["task_code"] == "jev_decision"
    assert usage_log.await_args.kwargs["success"] is True
    payload = client.post.call_args.kwargs["json"]
    assert payload["questions"]["decompose"]["type"] == "noul"


@pytest.mark.asyncio
async def test_jev_rejects_invalid_score():
    settings = MagicMock(jev_enabled=True, jev_model="jev-1.13-free",
                         jev_timeout_seconds=1.0)
    registry = MagicMock(get_provider_by_code=AsyncMock(
        return_value=MagicMock(id=17, enabled=True)))
    pool = MagicMock(lease=AsyncMock(return_value=MagicMock(id=4, plaintext="test-placeholder")),
                     record_generic_failure=AsyncMock())
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"answers": {"decompose": {"noul": 1.5}}}
    client = AsyncMock()
    client.post.return_value = response
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    with patch("app.core.llm_gateway.system_one.get_settings", return_value=settings), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient", return_value=manager
    ):
        assert await decide_system_one("Question", registry=registry, key_pool=pool) is None
    pool.record_generic_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_jev_uses_gateway_entry_point():
    gateway = MagicMock(decide_jev=AsyncMock(return_value={"score": 0.87}))
    with patch("app.core.jev_decider.get_gateway", return_value=gateway):
        assert await decide_decomposition("Question") == {"score": 0.87}
    gateway.decide_jev.assert_awaited_once_with("Question")


@pytest.mark.asyncio
async def test_jev_auth_failure_marks_managed_key():
    settings = MagicMock(jev_enabled=True, jev_model="jev-1.13-free",
                         jev_timeout_seconds=1.0)
    registry = MagicMock(get_provider_by_code=AsyncMock(
        return_value=MagicMock(id=17, enabled=True)))
    pool = MagicMock(lease=AsyncMock(return_value=MagicMock(id=4, plaintext="bad-key")),
                     record_auth_failure=AsyncMock())
    response = MagicMock(status_code=401)
    client = AsyncMock()
    client.post.return_value = response
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    with patch("app.core.llm_gateway.system_one.get_settings", return_value=settings), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient", return_value=manager
    ):
        assert await decide_system_one("Question", registry=registry, key_pool=pool) is None
    pool.record_auth_failure.assert_awaited_once_with(4, "System One authentication failed")


@pytest.mark.asyncio
async def test_jev_without_admin_key_falls_back_without_http_call():
    from app.core.llm_gateway.errors import NoKeyAvailableError

    registry = MagicMock(get_provider_by_code=AsyncMock(
        return_value=MagicMock(id=17, enabled=True)))
    pool = MagicMock(lease=AsyncMock(side_effect=NoKeyAvailableError("none")))
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=True)), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient"
    ) as client:
        assert await decide_system_one("Question", registry=registry, key_pool=pool) is None
    client.assert_not_called()


@pytest.mark.asyncio
async def test_final_synthesis_disables_tools_and_uses_evidence():
    async def stream(req):
        assert req.extra == {}
        assert req.messages[-2]["role"] == "tool"
        assert "Không gọi thêm công cụ" in req.messages[-1]["content"]
        yield "Câu trả lời từ tài liệu.", None, {}

    gateway = MagicMock(stream=stream)
    result = await _synthesize_after_tools(
        gateway, [{"role": "tool", "content": "Evidence"}], lambda *a, **kw: [],
        "How to schedule HPC and QC?",
    )
    assert result == "Câu trả lời từ tài liệu."


@pytest.mark.asyncio
async def test_assess_question_is_advisory_and_fails_closed_when_unavailable():
    with patch("app.agents.tools.shared.assess_question.decide_decomposition",
               new=AsyncMock(return_value=None)):
        unavailable = await AssessQuestionTool().execute(question="How to schedule HPC and QC?")
    assert unavailable.status == "error"
    with patch("app.agents.tools.shared.assess_question.decide_decomposition",
               new=AsyncMock(return_value={"score": 0.87, "model": "jev-1.13-free"})):
        result = await AssessQuestionTool().execute(question="How to schedule HPC and QC?")
    assert result.data == {"decomposition_score": 0.87,
                           "model": "jev-1.13-free", "advisory_only": True}


@pytest.mark.asyncio
async def test_mcp_exposes_assessment_without_write_permission():
    with patch("mcp.tool_adapter._ALLOWED_TOOLS", {"assess_question"}), patch(
        "mcp.tool_adapter.AssessQuestionTool.execute",
        new=AsyncMock(return_value=ToolResult(
            status="success", data={"decomposition_score": 0.87}, message="Assessed",
        )),
    ), patch("mcp.tool_adapter._audit", new=AsyncMock()):
        descriptors = get_mcp_tool_list()
        result = await call_mcp_tool("assess_question", {"question": "Explain scheduling"}, 42)
    assert len(descriptors) == 1
    assert descriptors[0]["annotations"]["readOnlyHint"] is True
    assert result["isError"] is False
