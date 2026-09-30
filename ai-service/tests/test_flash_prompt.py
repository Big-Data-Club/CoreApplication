"""Unit coverage for the latency-first Flash prompt."""
from app.agents.core.prompts import build_flash_system_prompt
from app.core.llm_gateway import ALL_TASK_CODES, TASK_AGENT_FLASH


def test_flash_has_a_dedicated_model_binding_task():
    assert TASK_AGENT_FLASH == "agent_flash"
    assert TASK_AGENT_FLASH in ALL_TASK_CODES


def test_flash_prompt_is_direct_and_bounds_lesson_text():
    prompt = build_flash_system_prompt(
        agent_type="mentor",
        user_context={"name": "Lan"},
        page_context={
            "contentTitle": "OOP",
            "contentBody": "x" * 1601,
        },
    )

    assert "Do not call tools" in prompt
    assert "<thought>" in prompt
    assert "Lan" in prompt
    # The request pipeline compacts Flash context to 1,600 characters before
    # it reaches this formatter; the formatter must not expand it again.
    assert len(prompt) < 2_500
