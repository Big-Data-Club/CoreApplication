from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agents.core.react_loop import _synthesize_after_tools
from app.agents.tools.base_tool import ToolResult
from app.agents.tools.shared.assess_question import AssessQuestionTool
from app.core.jev_decider import decide_decomposition
from app.core.llm_gateway.bootstrap import _bootstrap_system_one
from app.core.llm_gateway.errors import NoKeyAvailableError
from app.core.llm_gateway.system_one import decide_system_one
from app.core.llm_gateway.types import ALL_TASK_CODES, TASK_JEV_DECISION
from app.api.endpoints.admin_llm import (
    BindingIn, TestCallIn as AdminTestCallIn, test_call as admin_test_call,
    upsert_binding,
)
from mcp.tool_adapter import call_mcp_tool, get_mcp_tool_list


def _binding(provider_id=17, provider_code="zen", model_name="jev-other",
             protocol="system_one", base_url="https://zen.example.test/api/v2",
             endpoint_path="systemone"):
    model = MagicMock(
        id=provider_id + 100, provider_id=provider_id,
        provider_code=provider_code, model_name=model_name,
        config={"api_protocol": protocol, "endpoint_path": endpoint_path},
    )
    binding = MagicMock(model=model)
    provider = MagicMock(id=provider_id, enabled=True, base_url=base_url)
    return binding, provider


def _registry(*entries):
    providers = {provider.id: provider for _, provider in entries}
    return MagicMock(
        get_binding_chain=AsyncMock(return_value=[binding for binding, _ in entries]),
        get_provider=AsyncMock(side_effect=lambda provider_id: providers[provider_id]),
    )


def _response(score, *, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = {
        "answers": {"decompose": {"noul": score}},
        "usage": {"input_tokens": 296, "output_tokens": 20},
    }
    return response


def _client(*responses):
    client = AsyncMock()
    client.post.side_effect = responses
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    return manager, client


@pytest.mark.asyncio
async def test_system_one_bootstrap_seeds_visible_model_and_task_once():
    provider = MagicMock(id=17)
    model = MagicMock(id=117)
    registry = MagicMock(
        get_provider_by_code=AsyncMock(return_value=None),
        upsert_provider=AsyncMock(return_value=provider),
        list_models=AsyncMock(return_value=[]),
        upsert_model=AsyncMock(return_value=model),
        list_bindings=AsyncMock(return_value=[]),
        upsert_binding=AsyncMock(),
    )
    await _bootstrap_system_one(registry)
    assert registry.upsert_provider.await_args.kwargs["code"] == "opencode_zen"
    assert registry.upsert_model.await_args.kwargs["config"] == {"api_protocol": "system_one"}
    assert registry.upsert_binding.await_args.kwargs["task_code"] == TASK_JEV_DECISION

    registry.get_provider_by_code.return_value = provider
    registry.list_models.return_value = [MagicMock(id=117, model_name="jev-1.13-free")]
    registry.list_bindings.return_value = [MagicMock()]
    registry.upsert_provider.reset_mock()
    registry.upsert_model.reset_mock()
    registry.upsert_binding.reset_mock()
    await _bootstrap_system_one(registry)
    registry.upsert_provider.assert_not_awaited()
    registry.upsert_model.assert_not_awaited()
    registry.upsert_binding.assert_not_awaited()


@pytest.mark.asyncio
async def test_jev_disabled_never_loads_binding_or_sends_question():
    registry = _registry(_binding())
    pool = MagicMock(lease=AsyncMock())
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=False)):
        assert await decide_system_one("Private learning question",
                                       registry=registry, key_pool=pool) is None
    registry.get_binding_chain.assert_not_called()
    pool.lease.assert_not_called()


@pytest.mark.asyncio
async def test_jev_uses_bound_model_provider_url_and_managed_key():
    registry = _registry(_binding())
    pool = MagicMock(
        lease=AsyncMock(return_value=MagicMock(id=4, plaintext="test-placeholder")),
        record_success=AsyncMock(),
    )
    manager, client = _client(_response(0.87))
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=True, jev_timeout_seconds=1.0)), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient", return_value=manager
    ), patch("app.core.llm_gateway.system_one.record_usage", new=AsyncMock()) as usage_log:
        result = await decide_system_one("How should scheduling work?",
                                         registry=registry, key_pool=pool)
    assert result["score"] == 0.87
    assert result["model"] == "jev-other"
    assert result["provider"] == "zen"
    assert "test-placeholder" not in str(result)
    registry.get_binding_chain.assert_awaited_once_with(TASK_JEV_DECISION)
    pool.lease.assert_awaited_once_with(17, exclude_ids=set())
    pool.record_success.assert_awaited_once_with(4, 316)
    assert usage_log.await_args.kwargs["model"].model_name == "jev-other"
    assert usage_log.await_args.kwargs["task_code"] == TASK_JEV_DECISION
    assert client.post.call_args.args[0] == "https://zen.example.test/api/v2/systemone"
    assert client.post.call_args.kwargs["json"]["model"] == "jev-other"


@pytest.mark.asyncio
async def test_jev_falls_back_to_model_from_another_provider():
    registry = _registry(
        _binding(17, "zen", "bad-jev"),
        _binding(23, "second", "good-jev", base_url="https://other.example.test/system",
                 endpoint_path="decision/systemone"),
    )
    pool = MagicMock(
        lease=AsyncMock(side_effect=[
            MagicMock(id=4, plaintext="bad-key"),
            MagicMock(id=8, plaintext="good-key"),
        ]),
        record_generic_failure=AsyncMock(), record_success=AsyncMock(),
    )
    manager, client = _client(_response(1.5), _response(0.91))
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=True, jev_timeout_seconds=1.0)), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient", return_value=manager
    ), patch("app.core.llm_gateway.system_one.record_usage", new=AsyncMock()):
        result = await decide_system_one("Question", registry=registry, key_pool=pool)
    assert result["model"] == "good-jev"
    assert result["provider"] == "second"
    assert result["fallback_used"] is True
    assert client.post.call_args.args[0] == "https://other.example.test/system/decision/systemone"
    pool.record_generic_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_jev_retries_another_key_after_auth_failure():
    registry = _registry(_binding())
    pool = MagicMock(
        lease=AsyncMock(side_effect=[
            MagicMock(id=4, plaintext="bad-key"),
            MagicMock(id=5, plaintext="good-key"),
        ]),
        record_auth_failure=AsyncMock(), record_success=AsyncMock(),
    )
    manager, client = _client(_response(0, status=401), _response(0.77))
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=True, jev_timeout_seconds=1.0)), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient", return_value=manager
    ), patch("app.core.llm_gateway.system_one.record_usage", new=AsyncMock()):
        result = await decide_system_one("Question", registry=registry, key_pool=pool)
    assert result["score"] == 0.77
    assert result["attempt_no"] == 2
    assert client.post.await_count == 2
    pool.record_auth_failure.assert_awaited_once_with(4, "System One authentication failed")


@pytest.mark.asyncio
async def test_jev_skips_chat_model_or_invalid_url_without_leasing_key():
    registry = _registry(
        _binding(17, protocol="chat"),
        _binding(23, base_url="http://other.example.test/api"),
    )
    pool = MagicMock(lease=AsyncMock())
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=True)):
        assert await decide_system_one("Question", registry=registry, key_pool=pool) is None
    pool.lease.assert_not_called()


@pytest.mark.asyncio
async def test_jev_without_admin_key_falls_back_without_http_call():
    registry = _registry(_binding())
    pool = MagicMock(lease=AsyncMock(side_effect=NoKeyAvailableError("none")))
    with patch("app.core.llm_gateway.system_one.get_settings",
               return_value=MagicMock(jev_enabled=True)), patch(
        "app.core.llm_gateway.system_one.httpx.AsyncClient"
    ) as client:
        assert await decide_system_one("Question", registry=registry, key_pool=pool) is None
    client.assert_not_called()


@pytest.mark.asyncio
async def test_jev_uses_gateway_entry_point():
    gateway = MagicMock(decide_jev=AsyncMock(return_value={"score": 0.87}))
    with patch("app.core.jev_decider.get_gateway", return_value=gateway):
        assert await decide_decomposition("Question") == {"score": 0.87}
    gateway.decide_jev.assert_awaited_once_with("Question")
    assert TASK_JEV_DECISION in ALL_TASK_CODES


@pytest.mark.asyncio
async def test_admin_rejects_chat_model_for_system_one_binding():
    registry = MagicMock(get_model=AsyncMock(return_value=MagicMock(config={})),
                         upsert_binding=AsyncMock())
    with patch("app.api.endpoints.admin_llm._verify"), patch(
        "app.api.endpoints.admin_llm.get_registry", return_value=registry
    ):
        with pytest.raises(HTTPException) as error:
            await upsert_binding(BindingIn(task_code=TASK_JEV_DECISION, model_id=1), MagicMock())
    assert error.value.status_code == 400
    registry.upsert_binding.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_test_call_uses_system_one_task_path():
    decision = {
        "score": 0.87, "model": "other-jev", "provider": "other-provider",
        "fallback_used": True, "attempt_no": 1,
        "input_tokens": 12, "output_tokens": 3, "latency_ms": 100,
    }
    gateway = MagicMock(decide_jev=AsyncMock(return_value=decision), chat=AsyncMock())
    with patch("app.api.endpoints.admin_llm._verify"), patch(
        "app.api.endpoints.admin_llm.get_gateway", return_value=gateway
    ):
        result = await admin_test_call(AdminTestCallIn(task=TASK_JEV_DECISION, prompt="Question"), MagicMock())
    assert result["model"] == "other-jev"
    assert result["usage"]["total_tokens"] == 15
    gateway.decide_jev.assert_awaited_once_with("Question")
    gateway.chat.assert_not_awaited()


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
