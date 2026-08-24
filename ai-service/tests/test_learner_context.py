"""Offline tests for the deterministic learner snapshot."""
from __future__ import annotations

import unittest

from app.agents.core.learner_context import (
    fetch_learner_snapshot,
    format_learner_snapshot,
    should_inject_learner_snapshot,
)


class InjectionPolicyTest(unittest.TestCase):
    def test_teacher_never_injects(self) -> None:
        self.assertFalse(should_inject_learner_snapshot(
            agent_type="teacher", personalization_enabled=True,
            lakehouse_required=True, page_type="dashboard",
        ))

    def test_personalization_flag_injects(self) -> None:
        self.assertTrue(should_inject_learner_snapshot(
            agent_type="mentor", personalization_enabled=True,
            lakehouse_required=False, page_type="lesson",
        ))

    def test_proactive_surfaces_inject(self) -> None:
        for page in ("dashboard", "home", "course_list", ""):
            self.assertTrue(should_inject_learner_snapshot(
                agent_type="mentor", personalization_enabled=False,
                lakehouse_required=False, page_type=page,
            ), page)

    def test_plain_lesson_without_flags_skips(self) -> None:
        self.assertFalse(should_inject_learner_snapshot(
            agent_type="mentor", personalization_enabled=False,
            lakehouse_required=False, page_type="lesson",
        ))


class FormatterTest(unittest.TestCase):
    def test_full_snapshot_renders_facts(self) -> None:
        text = format_learner_snapshot({
            "due_count": 7,
            "due_topics": ["Big-O", "Hash tables"],
            "weak": [
                {"name": "Đệ quy", "mastery": 0.22},
                {"name": "Cây AVL", "mastery": 0.35},
            ],
            "strong": ["Mảng", "Vòng lặp"],
        })
        self.assertIn("VERIFIED LEARNER FACTS", text)
        self.assertIn("7 flashcard(s) are DUE", text)
        self.assertIn("Đệ quy (mastery 22%)", text)
        self.assertIn("Mảng", text)

    def test_empty_snapshot_warns_not_invents(self) -> None:
        text = format_learner_snapshot({"due_count": 0, "due_topics": [], "weak": [], "strong": []})
        self.assertIn("No mastery/review data yet", text)
        self.assertIn("Do not invent weaknesses", text)


if __name__ == "__main__":
    unittest.main()
