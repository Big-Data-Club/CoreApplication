from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.core.react_loop import _synthesize_after_tools
from app.core.jev_decider import decide_decomposition
from app.agents.tools.shared.assess_question import AssessQuestionTool
from app.agents.tools.base_tool import ToolResult
from mcp.tool_adapter import call_mcp_tool, get_mcp_tool_list


@pytest.mark.asyncio
async def test_jev_disabled_never_sends_question():
    settings = MagicMock(jev_enabled=False, opencode_api_key="")
    with patch("app.core.jev_decider.get_settings", return_value=settings), patch(
        "app.core.jev_decider.httpx.AsyncClient"
    ) as client:
        assert await decide_decomposition("Private learning question") is None
        client.assert_not_called()


@pytest.mark.asyncio
async def test_jev_structured_response_and_no_key_in_result():
    settings = MagicMock(jev_enabled=True, opencode_api_key="test-placeholder",
                         jev_model="jev-1.13-free", jev_timeout_seconds=1.0)
    response = MagicMock()
    response.json.return_value = {"answers": {"decompose": {"noul": 0.87}}}
    client = AsyncMock()
    client.post.return_value = response
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    with patch("app.core.jev_decider.get_settings", return_value=settings), patch(
        "app.core.jev_decider.httpx.AsyncClient", return_value=manager
    ):
        result = await decide_decomposition("How should scheduling work?")
    assert result == {"score": 0.87, "model": "jev-1.13-free"}
    assert "test-placeholder" not in str(result)
    payload = client.post.call_args.kwargs["json"]
    assert payload["questions"]["decompose"]["type"] == "noul"


@pytest.mark.asyncio
async def test_jev_rejects_invalid_score():
    settings = MagicMock(jev_enabled=True, opencode_api_key="test-placeholder",
                         jev_model="jev-1.13-free", jev_timeout_seconds=1.0)
    response = MagicMock()
    response.json.return_value = {"answers": {"decompose": {"noul": 1.5}}}
    client = AsyncMock()
    client.post.return_value = response
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    with patch("app.core.jev_decider.get_settings", return_value=settings), patch(
        "app.core.jev_decider.httpx.AsyncClient", return_value=manager
    ):
        assert await decide_decomposition("Question") is None


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
