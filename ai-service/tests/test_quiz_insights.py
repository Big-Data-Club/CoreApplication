"""Offline regressions for task routing, context fallback, and retry safety."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.llm_gateway import ALL_TASK_CODES, TASK_QUIZ_GEN, TASK_QUIZ_INSIGHTS
from app.core.llm_gateway.errors import ContextLengthError
from app.services import learning_design, quiz_insights_service as insights
from app.services.studio import authoring_context
from app.services.learning_context import LearningContext


def test_small_fallback_does_not_veto_large_primary():
    registry = SimpleNamespace(
        get_binding_chain=AsyncMock(return_value=[
            SimpleNamespace(model=SimpleNamespace(provider_id=1, context_window=30000)),
            SimpleNamespace(model=SimpleNamespace(provider_id=2, context_window=2000)),
        ]), list_api_keys=AsyncMock(return_value=[]),
    )
    gateway = SimpleNamespace(registry=registry, _request_budget=lambda window, limit, model: window)
    with patch.object(authoring_context, "get_gateway", return_value=gateway), patch.object(authoring_context, "get_settings", return_value=SimpleNamespace(llm_request_token_budget=30000)):
        available = asyncio.run(authoring_context._request_budget(TASK_QUIZ_GEN, 4200, 1000))
    assert available == 22400
    registry.get_binding_chain.assert_awaited_once_with(TASK_QUIZ_GEN)


def test_truly_insufficient_model_still_rejects_before_call():
    registry = SimpleNamespace(get_binding_chain=AsyncMock(return_value=[]))
    with patch.object(authoring_context, "get_gateway", return_value=SimpleNamespace(registry=registry)), patch.object(authoring_context, "get_settings", return_value=SimpleNamespace(llm_request_token_budget=2000)), pytest.raises(ContextLengthError):
        asyncio.run(authoring_context._request_budget(TASK_QUIZ_GEN, 2400, 1000))


def test_quiz_planning_uses_quiz_binding_for_both_preflight_and_call():
    context = LearningContext([{"content_id": 1, "title": "Stack", "text": "A stack uses last-in-first-out ordering."}], [], [])
    with patch.object(learning_design, "prepare_authoring_context", new=AsyncMock(return_value=SimpleNamespace(text="[SOURCE S1: Stack]\nA stack uses last-in-first-out ordering."))) as prepare, patch.object(learning_design, "chat_complete_json", new=AsyncMock(return_value={"units":[{"title":"Stack","objective":"Explain LIFO","source_refs":["S1"]}]})) as complete:
        asyncio.run(learning_design.plan_learning_units(context, kind="assessment questions", language="vi", count=1, task=TASK_QUIZ_GEN))
    assert prepare.await_args.kwargs["task"] == TASK_QUIZ_GEN
    assert prepare.await_args.kwargs["requested_output_tokens"] == 1200
    assert complete.await_args.kwargs["task"] == TASK_QUIZ_GEN


def valid_result():
    return {"summary": "Kết quả đánh giá", "strengths": [], "gaps": [], "recommendations": [], "limitations": ["Cỡ mẫu nhỏ"]}


def test_analysis_uses_dedicated_task_and_aggregates_scores():
    with patch.object(insights, "chat_complete_json", new=AsyncMock(return_value=valid_result())) as complete:
        result = asyncio.run(insights.analyze_quiz_results({"scores":[20, 80, 100], "questions":[], "pending_answers":2}))
    assert result == valid_result()
    assert TASK_QUIZ_INSIGHTS in ALL_TASK_CODES
    assert complete.await_args.kwargs["task"] == TASK_QUIZ_INSIGHTS
    evidence = json.loads(complete.await_args.kwargs["messages"][1]["content"])
    assert evidence["score_distribution"] == [0, 1, 0, 0, 2]
    assert evidence["pending_answers"] == 2


@pytest.mark.parametrize("result", [None, {}, {**valid_result(), "gaps":"invalid"}])
def test_malformed_ai_result_is_not_published_as_success(result):
    with patch.object(insights, "chat_complete_json", new=AsyncMock(return_value=result)), pytest.raises(ValueError):
        asyncio.run(insights.analyze_quiz_results({"scores":[40]}))


def test_empty_results_do_not_call_provider():
    with patch.object(insights, "chat_complete_json", new=AsyncMock()) as complete, pytest.raises(ValueError):
        asyncio.run(insights.analyze_quiz_results({"scores":[]}))
    complete.assert_not_awaited()


def test_duplicate_job_reuses_persisted_result():
    conn = AsyncMock()
    conn.transaction = lambda: AsyncMock()
    conn.fetchval.return_value = json.dumps(valid_result())
    manager = AsyncMock()
    manager.__aenter__.return_value = conn
    with patch.object(insights, "get_ai_conn", return_value=manager), patch.object(insights, "analyze_quiz_results", new=AsyncMock()) as generate:
        result = asyncio.run(insights.process_quiz_insights("stable-job-id", {"scores":[40]}))
    assert result == valid_result()
    generate.assert_not_awaited()


def test_failed_job_does_not_persist_a_success_result():
    conn = AsyncMock()
    conn.transaction = lambda: AsyncMock()
    conn.fetchval.return_value = None
    manager = AsyncMock()
    manager.__aenter__.return_value = conn
    with patch.object(insights, "get_ai_conn", return_value=manager), patch.object(insights, "analyze_quiz_results", new=AsyncMock(side_effect=TimeoutError)), pytest.raises(TimeoutError):
        asyncio.run(insights.process_quiz_insights("stable-job-id", {"scores":[40]}))
    assert not any("INSERT INTO" in call.args[0] for call in conn.execute.await_args_list)


def test_large_quiz_uses_bounded_summary_not_individual_scores():
    summary = {"graded_attempts":10000,"average_percentage":70.5,"pending_answers":12}
    with patch.object(insights, "chat_complete_json", new=AsyncMock(return_value=valid_result())) as complete:
        asyncio.run(insights.analyze_quiz_results({"summary":summary,"distribution":[{"bucket":0,"count":100}],"questions":[]}))
    evidence = json.loads(complete.await_args.kwargs["messages"][1]["content"])
    assert evidence["graded_attempts"] == 10000
    assert "scores" not in evidence
    assert len(json.dumps(evidence)) < 500
