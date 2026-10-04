from app.agents.core.decision_explanation import build_decision_explanation
from app.agents.memory.context_builder import ContextBuilder


def test_profile_metrics_are_formatted_for_prompt():
    section = ContextBuilder._format_ltm_facts(
        [], 120,
        {"completed_lessons": 3, "attempted_lessons": 5, "check_accuracy": 0.75},
    )
    assert "completed_lessons=3/5" in section
    assert "quick_check_accuracy=75.0%" in section


def test_explanation_only_reports_profile_when_in_prompt():
    context = {
        "prompt_section": "STUDENT COGNITIVE PROFILE (LTM FACTS):\n  Lakehouse metrics: completed_lessons=3/5, quick_check_accuracy=75.0%",
        "stm_messages": [{"role": "user", "content": "hello"}],
        "raw": {"stm": {"token_estimate": 12}, "personalize_profile": {
            "completed_lessons": 3, "attempted_lessons": 5,
            "check_accuracy": 0.75, "correct_checks_count": 3,
            "incorrect_checks_count": 1,
        }},
    }
    used = build_decision_explanation(
        context, mode="standard", multi_agent=False,
        intent_type="progress_advice", personalization_requested=True,
    )
    assert used["profile_status"] == "used"
    assert used["course_profile"]["quick_checks"] == 4
    assert used["conversation_turns_used"] == 1
    assert "content" not in str(used)

    context["prompt_section"] = ""
    omitted = build_decision_explanation(
        context, mode="standard", multi_agent=False,
        intent_type="progress_advice", personalization_requested=True,
    )
    assert omitted["profile_status"] == "available_not_used"
    assert "course_profile" not in omitted


def test_multi_agent_does_not_claim_memory_or_profile_use():
    context = {
        "prompt_section": "DURABLE MEMORY:\n- [preference | session | confidence=1.0] secret",
        "stm_messages": [{"role": "user", "content": "secret"}],
        "raw": {"personalize_profile": {"check_accuracy": 0.8, "attempted_lessons": 2}},
    }
    result = build_decision_explanation(
        context, mode="deep", multi_agent=True,
        intent_type="knowledge_question", personalization_requested=True,
    )
    assert result["conversation_turns_used"] == 0
    assert result["durable_memory_used"] == 0
    assert result["profile_status"] == "available_not_used"
    assert "secret" not in str(result)


def test_empty_course_profile_is_not_presented_as_personalization():
    result = build_decision_explanation(
        {"prompt_section": "", "stm_messages": [], "raw": {
            "personalize_profile": {"completed_lessons": 0, "attempted_lessons": 0,
                                    "correct_checks_count": 0, "incorrect_checks_count": 0},
        }},
        mode="standard", multi_agent=False, intent_type="general_chat",
        personalization_requested=False,
    )
    assert result["profile_status"] == "unavailable"
    assert "course_profile" not in result
