"""Fast, dependency-free checks for agentic memory and orchestration policy."""
from __future__ import annotations

import unittest

from app.agents.core.agentic_protocol import (
    AgentTask,
    build_orchestration_plan,
    default_capability_registry,
)
from app.agents.memory.memory_policy import (
    migrate_legacy_memory,
    normalize_memory_items,
    select_memory_for_prompt,
)


class AgenticFoundationTest(unittest.TestCase):
    def test_evidence_task_gets_retrieval_draft_and_quality_gate(self) -> None:
        task = AgentTask(
            objective="Explain an HPC scheduling trade-off",
            intent="knowledge_question",
            require_evidence=True,
            quality_gate=True,
        )
        plan = build_orchestration_plan(task, default_capability_registry())
        self.assertEqual(
            [step.capability for step in plan.steps],
            ["evidence_retrieval", "response_drafting", "quality_critique"],
        )

    def test_low_risk_task_uses_only_drafting(self) -> None:
        task = AgentTask(
            objective="Say hello", intent="general_chat", require_evidence=False, quality_gate=False,
        )
        plan = build_orchestration_plan(task, default_capability_registry())
        self.assertEqual([step.capability for step in plan.steps], ["response_drafting"])

    def test_memory_policy_excludes_completed_and_wrong_course(self) -> None:
        items = normalize_memory_items([
            {"kind": "anchor", "value": "HPC course", "scope": "course", "course_id": 38, "confidence": 0.9},
            {"kind": "pending_action", "value": "Review quiz", "status": "completed", "confidence": 1.0},
            {"kind": "preference", "value": "Vietnamese", "scope": "user", "confidence": 0.8},
        ])
        selected = select_memory_for_prompt(items, course_id=26)
        self.assertEqual([item["value"] for item in selected], ["Vietnamese"])

    def test_legacy_memory_stays_usable(self) -> None:
        migrated = migrate_legacy_memory({
            "key_facts": {"current_topic": "Apptainer", "preferred_language": "vi"},
            "pending_actions": ["Review lesson draft"],
        })
        self.assertEqual(len(migrated), 3)


if __name__ == "__main__":
    unittest.main()
