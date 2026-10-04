"""Small, bounded account of evidence actually made available to an answer."""

from __future__ import annotations

from typing import Any
import re
from app.core.llm_gateway.token_budget import estimate_messages_tokens


def build_decision_explanation(
    memory_ctx: dict[str, Any], *, mode: str, multi_agent: bool,
    intent_type: str, personalization_requested: bool,
    learner_snapshot: dict[str, Any] | None = None,
    memory_forwarded: bool = False,
) -> dict[str, Any]:
    """Describe prompt inputs, never raw dialogue, private notes, or model reasoning."""
    raw = memory_ctx.get("raw") or {}
    prompt = memory_ctx.get("prompt_section") or ""
    history = memory_ctx.get("stm_messages") or []
    profile = raw.get("personalize_profile") or {}
    profile_has_activity = bool(
        not profile.get("error") and (
            profile.get("attempted_lessons")
            or profile.get("correct_checks_count")
            or profile.get("incorrect_checks_count")
            or profile.get("struggle_nodes")
        )
    )
    profile_in_prompt = "Lakehouse metrics:" in prompt
    memory_used = mode != "flash" and (not multi_agent or memory_forwarded)
    if multi_agent and memory_forwarded:
        history = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")]
    episode_block = (
        prompt.split("PAST INTERACTIONS (LTM EPISODIC):", 1)[1].split("\n\n", 1)[0]
        if "PAST INTERACTIONS (LTM EPISODIC):" in prompt else ""
    )

    explanation: dict[str, Any] = {
        "mode": mode,
        "multi_agent_executed": multi_agent,
        "memory_forwarded": memory_used,
        "intent": intent_type,
        "personalization_requested": bool(personalization_requested),
        "personalization_context_prepared": bool(memory_used and (
            profile_in_prompt or (learner_snapshot and (
                learner_snapshot.get("due_count") or learner_snapshot.get("weak") or learner_snapshot.get("strong")
            )) or ("STUDENT COGNITIVE PROFILE" in prompt
                   and re.search(r"\(Mastery: \d+(?:\.\d+)?%\)", prompt))
        )),
        "conversation_turns_used": len(history) if (memory_used or mode == "flash") else 0,
        "conversation_tokens": (
            estimate_messages_tokens(history) if multi_agent and memory_forwarded else
            (raw.get("stm") or {}).get("token_estimate", 0) if memory_used else 0
        ),
        "durable_memory_used": (
            sum(line.startswith("- [") for line in prompt.splitlines())
            if memory_used and "DURABLE MEMORY" in prompt else 0
        ),
        "past_episodes_used": (
            sum(line.startswith("  - ") for line in episode_block.splitlines())
            if memory_used else 0
        ),
        "profile_status": (
            "used" if memory_used and profile_in_prompt else
            "available_not_used" if profile_has_activity else "unavailable"
        ),
        "profile_fetch_status": raw.get("profile_fetch_status", "not_requested"),
        "conversation_messages_available": (raw.get("stm") or {}).get("available_count", len(history)),
        "conversation_history_excerpted": (raw.get("stm") or {}).get("excerpted", False),
    }

    if memory_used and profile_in_prompt:
        explanation["course_profile"] = {
            "completed_lessons": profile.get("completed_lessons", 0),
            "attempted_lessons": profile.get("attempted_lessons", 0),
            "check_accuracy": profile.get("check_accuracy", 0),
            "quick_checks": (profile.get("correct_checks_count") or 0)
                + (profile.get("incorrect_checks_count") or 0),
        }

    if memory_used and learner_snapshot is not None:
        explanation["learner_snapshot"] = {
            "due_count": learner_snapshot.get("due_count", 0),
            "weak": [
                {"name": str(item.get("name", ""))[:100], "mastery": item.get("mastery", 0)}
                for item in (learner_snapshot.get("weak") or [])[:3]
            ],
            "strong": [str(item)[:100] for item in (learner_snapshot.get("strong") or [])[:2]],
        }

    return explanation
