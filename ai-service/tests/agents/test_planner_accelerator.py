"""Routing safety and latency contracts; no live models or learner data."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.core.planner import ExecutionPlan
from app.agents.core.planner_accelerator import QUESTIONS, plan_standard_turn
from app.core.config import Settings

BASE = dict(user_message="Giải thích vòng lặp for trong Python?", agent_type="mentor",
            current_course_id=7, active_courses={"courses": [{"id": 7, "title": "Python"}]})


def config(mode="active", **changes):
    return SimpleNamespace(**dict(dict(jev_enabled=True, jev_planner_mode=mode,
        jev_planner_deadline_seconds=0.03, jev_planner_min_score=0.97), **changes))


def decision(score=0.99):
    return {"scores": {name: score for name in QUESTIONS}}


@pytest.fixture
def deps():
    reference = ExecutionPlan(reasoning="original planner")
    with patch("app.agents.core.planner_accelerator.get_settings", return_value=config()) as cfg, \
         patch("app.agents.core.planner_accelerator.get_gateway") as gateway, \
         patch("app.agents.core.planner.generate_plan", new=AsyncMock(return_value=reference)) as planner:
        gateway.return_value.evaluate_jev = AsyncMock(return_value=decision())
        yield cfg, gateway.return_value.evaluate_jev, planner, reference


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [dict(jev_enabled=False), dict(jev_planner_mode="off")])
async def test_disabled_keeps_original_and_never_sends_data(deps, changes):
    cfg, assess, planner, reference = deps
    cfg.return_value = config(**changes)
    assert await plan_standard_turn(**BASE) is reference
    assess.assert_not_awaited()
    planner.assert_awaited_once_with(**BASE)


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"agent_type": "teacher"}, {"history": [{"role": "user", "content": "Hi"}]},
    {"page_context": {"contentId": 3}}, {"system_context": {"lesson_id": 4}},
    {"current_course_id": None}, {"current_course_id": 99}, {"current_course_id": True},
    {"active_courses": {"courses": []}},
    {"active_courses": {"courses": [{"id": 7, "title": "Python"}, {"id": 8, "title": "SQL"}]}},
    {"user_message": "x" * 901}, {"user_message": " "},
    {"user_message": "Giải thích Python rồi tạo quiz cho tôi"},
    {"user_message": "Explain Python and save it to my notebook"},
    {"user_message": "Gợi ý bài học tiếp theo"},
    {"user_message": "Xem tiến độ và điểm của tôi"},
])
async def test_ineligible_never_calls_jev(deps, changes):
    _, assess, planner, reference = deps
    args = {**BASE, **changes}
    assert await plan_standard_turn(**args) is reference
    assess.assert_not_awaited()
    planner.assert_awaited_once_with(**args)


@pytest.mark.asyncio
async def test_accepted_skips_llm_planner_but_only_constructs_read_plan(deps):
    _, assess, planner, _ = deps
    plan = await plan_standard_turn(**BASE)
    planner.assert_not_awaited()
    assert plan.intent == "knowledge_question"
    assert plan.retrieval_strategy.scope == "course"
    assert plan.retrieval_strategy.max_expansion_level == "course"
    assert plan.selected_tools == ["search_course_materials", "explain_concept"]
    assert not plan.requires_tool and not plan.personalization_enabled
    assert plan.matched_course_id is None
    assert plan.graph_expansion_needed and plan.user_weakness_relevant
    state = assess.await_args.args[0]
    assert "current_course_id" not in state and "user_id" not in state
    assert BASE["user_message"] in state


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, {}, {"scores": {}}, decision(0.9699),
    decision(True), decision(float("nan")), decision(float("inf")), decision(1.1),
    decision("0.99"), {"scores": {"course_question": 1, "standalone": 1, "read_only": 0.1}}])
async def test_invalid_or_uncertain_decision_falls_back(deps, result):
    _, assess, planner, reference = deps
    assess.return_value = result
    assert await plan_standard_turn(**BASE) is reference
    planner.assert_awaited_once_with(**BASE)


@pytest.mark.asyncio
async def test_dependency_exception_falls_back(deps):
    _, assess, planner, reference = deps
    assess.side_effect = RuntimeError("provider unavailable")
    assert await plan_standard_turn(**BASE) is reference
    planner.assert_awaited_once()


@pytest.mark.asyncio
async def test_total_deadline_cancels_dependency_and_falls_back(deps):
    _, assess, planner, reference = deps
    cancelled = asyncio.Event()

    async def blocked(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    assess.side_effect = blocked
    assert await asyncio.wait_for(plan_standard_turn(**BASE), timeout=1) is reference
    assert cancelled.is_set()
    planner.assert_awaited_once()


@pytest.mark.asyncio
async def test_shadow_always_returns_reference_and_logs_differences(deps, caplog):
    cfg, _, planner, reference = deps
    cfg.return_value = config("shadow")

    async def original(**kwargs):
        await asyncio.sleep(0.01)
        return reference

    planner.side_effect = original
    with caplog.at_level("INFO"):
        assert await plan_standard_turn(**BASE) is reference
    assert "accepted=True" in caplog.text
    assert "differences=" in caplog.text
    assert BASE["user_message"] not in caplog.text


@pytest.mark.asyncio
async def test_shadow_does_not_wait_for_slow_jev(deps):
    cfg, assess, planner, reference = deps
    cfg.return_value = config("shadow", jev_planner_deadline_seconds=2)
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def original(**kwargs):
        await started.wait()
        return reference

    assess.side_effect = blocked
    planner.side_effect = original
    assert await asyncio.wait_for(plan_standard_turn(**BASE), timeout=0.5) is reference
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_request_cancellation_does_not_trigger_fallback(deps):
    _, assess, planner, _ = deps
    assess.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await plan_standard_turn(**BASE)
    planner.assert_not_awaited()


@pytest.mark.parametrize("fields", [
    {"jev_planner_mode": "typo"}, {"jev_planner_deadline_seconds": 0},
    {"jev_planner_deadline_seconds": 10}, {"jev_planner_min_score": 0.5},
])
def test_invalid_configuration_rejected(fields):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **fields)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,history_error,uses_jev,uses_planner", [
    ("standard", False, True, False), ("standard", True, False, True),
    ("deep", False, False, True), ("flash", False, False, False),
])
async def test_react_planning_boundary_preserves_modes_and_history_failure(
    deps, mode, history_error, uses_jev, uses_planner,
):
    from app.agents.core.react_loop import run_react_loop

    _, assess, planner, _ = deps
    with patch("app.agents.core.react_loop.load_active_courses",
               new=AsyncMock(return_value=BASE["active_courses"])), patch(
        "app.agents.memory.history.load_history",
        new=AsyncMock(return_value={"messages": [], "source": "none", "status": "unavailable" if history_error else "empty"}),
    ):
        stream = run_react_loop(session_id="test-session", user_id=42,
            agent_type="mentor", user_message=BASE["user_message"], course_id=7, chat_mode=mode)
        try:
            async for event in stream:
                if event.data.get("step") == "unified_plan":
                    break
            else:
                pytest.fail("Planning event missing")
        finally:
            await stream.aclose()
    assert assess.await_count == int(uses_jev)
    assert planner.await_count == int(uses_planner)
