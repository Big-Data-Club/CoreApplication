"""Routing vocabulary, memory continuity, and truthful personalization status."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.agents.core.planner import ExecutionPlan
from app.agents.core.router import RouterOutput
from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator
from app.agents.core.decision_explanation import build_decision_explanation
from app.agents.memory.context_builder import ContextBuilder
from app.core.llm_gateway.token_budget import estimate_messages_tokens


@pytest.mark.parametrize("alias,canonical", [
    ("content_qa", "knowledge_question"), ("recommendation_engine", "progress_advice"),
    ("quiz_assist", "interactive_exercise"), ("navigation_helper", "knowledge_question"),
    ("content_creation", "content_creation"),
])
def test_operation_aliases_cannot_fall_into_general_chat_score(alias, canonical):
    assert ExecutionPlan(intent=alias).intent == canonical
    assert RouterOutput(intent=alias, is_ambiguous=False).intent == canonical


def test_unknown_intent_is_rejected_at_planner_boundary():
    with pytest.raises(ValidationError):
        ExecutionPlan(intent="made_up_label")


def test_reported_score_reproduction_and_corrected_knowledge_score():
    orchestrator = MultiAgentOrchestrator("s", "t")
    args = dict(user_message="Giải thích chi tiết", parent_context_length=0,
                page_context={"contentTitle": "QPU"})
    old_score, _ = orchestrator.calculate_spawning_score(intent_type="general_chat", **args)
    score, breakdown = orchestrator.calculate_spawning_score(intent_type="content_qa", **args)
    assert old_score == pytest.approx(0.46)
    assert score == pytest.approx(0.74)
    assert breakdown["d_intent"] == 0.7 and breakdown["r_docs"] == 1


def test_long_deep_answer_does_not_erase_recent_dialogue():
    history = [{"role": "user", "content": "Tôi mới bắt đầu học QPU"},
               {"role": "assistant", "content": "Long explanation " * 5000 + "END_OF_ANSWER"}]
    kept, excerpted = ContextBuilder._fit_recent_dialogue(history, 400)
    assert len(kept) == 2 and excerpted
    assert kept[0]["content"] == history[0]["content"]
    assert kept[-1]["content"].endswith("END_OF_ANSWER")
    assert "middle omitted" in kept[-1]["content"]
    assert estimate_messages_tokens(kept) <= 400
    assert history[-1]["content"].startswith("Long explanation")


def test_unassessed_active_concept_is_not_zero_percent_mastery():
    section = ContextBuilder._format_ltm_facts([{
        "name": "QPU", "structural_score": 2.0, "mastery_level": 0,
        "mastery_observed": False, "struggles": False,
    }], 500)
    assert "unknown" in section and "0.0%" not in section


PROFILE = dict(user_id=10, course_id=20, completed_lessons=2, attempted_lessons=3,
               correct_checks_count=3, incorrect_checks_count=1, check_accuracy=0.75,
               struggle_nodes=[])


@pytest.fixture
def memory_deps():
    cfg = SimpleNamespace(max_context_tokens=2000, stm_budget=800,
        ltm_episodic_budget=400, ltm_facts_budget=800,
        personalize_service_url="http://profile.test", ai_service_secret="test-placeholder")
    response = MagicMock(status_code=200)
    response.json.return_value = dict(PROFILE)
    client = AsyncMock()
    client.get.return_value = response
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    with patch("app.agents.memory.context_builder.get_settings", return_value=cfg), \
         patch("app.agents.memory.context_builder.mtm.get_context", new=AsyncMock(return_value={})), \
         patch("app.agents.memory.context_builder.stm.get_window", new=AsyncMock(return_value=[])), \
         patch("app.agents.memory.context_builder.ltm.recall", new=AsyncMock(return_value=[])), \
         patch.object(ContextBuilder, "_compute_multi_signal_scoring", new=AsyncMock(return_value=[])) as scoring, \
         patch("httpx.AsyncClient", return_value=manager):
        yield response, client, scoring


async def build(**overrides):
    args = dict(user_id=10, course_id=20, session_id="s", agent_type="mentor",
                query="QPU?", intent_type="knowledge_question")
    return await ContextBuilder().build(**{**args, **overrides})


@pytest.mark.asyncio
async def test_snapshot_does_not_disable_course_profile_fetch(memory_deps):
    _, client, scoring = memory_deps
    ctx = await build(include_ltm_facts=False)
    client.get.assert_awaited_once()
    assert client.get.await_args.args[0].endswith("/student/10/course/20")
    scoring.assert_not_awaited()
    assert ctx["raw"]["profile_fetch_status"] == "loaded"
    assert "Lakehouse metrics:" in ctx["prompt_section"]
    explanation = build_decision_explanation(ctx, mode="deep", multi_agent=True,
        memory_forwarded=True, intent_type="knowledge_question", personalization_requested=False)
    assert explanation["profile_status"] == "used"
    assert explanation["personalization_context_prepared"] is True
    assert explanation["personalization_requested"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"error": "database unavailable"}, 200),
    (dict(PROFILE, user_id=99), 200),
    (dict(PROFILE, check_accuracy="bad"), 200),
    (dict(PROFILE), 503),
])
async def test_profile_errors_are_not_reported_as_no_learning_activity(memory_deps, payload, status):
    response, _, _ = memory_deps
    response.status_code = status
    response.json.return_value = payload
    ctx = await build()
    assert ctx["raw"]["profile_fetch_status"] == "error"
    assert "Lakehouse metrics" not in ctx["prompt_section"]


@pytest.mark.asyncio
async def test_successful_empty_profile_has_distinct_status(memory_deps):
    response, _, _ = memory_deps
    response.json.return_value = {**PROFILE, "completed_lessons": 0, "attempted_lessons": 0,
        "correct_checks_count": 0, "incorrect_checks_count": 0, "check_accuracy": 0}
    ctx = await build()
    assert ctx["raw"]["profile_fetch_status"] == "empty"


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides,reason", [
    ({"agent_type": "teacher"}, "not_applicable"),
    ({"course_id": None}, "no_course"), ({"memory_budget_tokens": 20}, "budget_limited"),
])
async def test_profile_fetch_respects_role_scope_and_budget(memory_deps, overrides, reason):
    _, client, _ = memory_deps
    ctx = await build(**overrides)
    client.get.assert_not_awaited()
    assert ctx["raw"]["profile_fetch_status"] == reason


@pytest.mark.asyncio
async def test_multi_agent_draft_receives_memory_and_recent_dialogue():
    requests = []
    async def stream(req):
        requests.append(req)
        yield "Answer.", None, {"choices": [{"finish_reason": "stop"}]}
    with patch("app.agents.core.sub_agents.get_gateway", return_value=SimpleNamespace(stream=stream)):
        events = [ev async for ev in MultiAgentOrchestrator("s", "t").run_multi_agent_flow(
            "Explain", 20, "general_chat", {}, memory_context="Measured mastery: 75%",
            history=[{"role": "user", "content": "I am a beginner"},
                     {"role": "tool", "content": "untrusted tool protocol"}],
        )]
    assert events[-1] == "Answer."
    assert "Measured mastery: 75%" in requests[0].messages[-1]["content"]
    assert any(m.get("content") == "I am a beginner" for m in requests[0].messages)
    assert not any(m.get("role") == "tool" for m in requests[0].messages)


def test_forwarded_memory_explanation_reports_prepared_context():
    result = build_decision_explanation({
        "prompt_section": "DURABLE MEMORY:\n- [preference] Beginner",
        "stm_messages": [{"role": "user", "content": "private"}],
        "raw": {"stm": {"token_estimate": 20}},
    }, mode="deep", multi_agent=True, memory_forwarded=True,
        intent_type="knowledge_question", personalization_requested=False)
    assert result["conversation_turns_used"] == 1
    assert result["durable_memory_used"] == 1
    assert "private" not in str(result)

@pytest.mark.asyncio
async def test_persistent_dialogue_reaches_model_context_without_second_cache_read(memory_deps):
    turns = [{"role": "user", "content": "We discussed cloud QPU pricing"},
             {"role": "assistant", "content": "And its latency"}]
    with patch('app.agents.memory.context_builder.stm.get_window', new=AsyncMock(side_effect=RuntimeError)) as cache:
        ctx = await build(history_window={"messages": turns, "source": "persistent", "status": "available"})
    cache.assert_not_awaited()
    assert ctx['stm_messages'] == turns
    assert ctx['raw']['stm']['source'] == 'persistent'

@pytest.mark.asyncio
async def test_history_outage_notice_is_in_model_prompt(memory_deps):
    ctx = await build(history_window={"messages": [], "source": "none", "status": "unavailable"})
    assert 'HISTORY UNAVAILABLE' in ctx['prompt_section']
    assert 'Do not claim this is a new conversation' in ctx['prompt_section']
