"""Offline contract tests for the citation & surface-awareness pipeline.

These run in CI without LLM keys: they pin the *contract* that makes
answers verifiable (prompt rules, ledger behaviour, surface directives,
citation validation) rather than model output quality.
"""
from __future__ import annotations

import unittest

from app.agents.core.references import ReferenceLedger, validate_inline_citations
from app.agents.core.prompts import (
    MENTOR_SYSTEM_PROMPT,
    TEACHER_SYSTEM_PROMPT,
    _surface_directive,
    build_system_prompt,
)


class CitationPromptContractTest(unittest.TestCase):
    def test_mentor_prompt_has_citation_rule(self) -> None:
        self.assertIn("Citations & Sources", MENTOR_SYSTEM_PROMPT)
        self.assertIn("`ref`", MENTOR_SYSTEM_PROMPT)
        self.assertIn("NEVER invent", MENTOR_SYSTEM_PROMPT)

    def test_teacher_prompt_has_citation_rule(self) -> None:
        self.assertIn("`ref`", TEACHER_SYSTEM_PROMPT)
        self.assertIn("never fabricate", TEACHER_SYSTEM_PROMPT)

    def test_both_templates_render_with_surface_directive(self) -> None:
        for agent in ("mentor", "teacher"):
            prompt = build_system_prompt(
                agent_type=agent,
                memory_context="MEM",
                active_courses_section="ACTIVE",
            )
            self.assertIn("Surface Mode", prompt)
            self.assertIn("No page signal", prompt)

    def test_dashboard_page_context_switches_mode(self) -> None:
        for agent in ("mentor", "teacher"):
            prompt = build_system_prompt(
                agent_type=agent,
                memory_context="MEM",
                active_courses_section="ACTIVE",
                page_context={"pageType": "dashboard"},
            )
            self.assertIn("PROACTIVE DASHBOARD MODE", prompt)


class ReferenceLedgerTest(unittest.TestCase):
    def test_dedup_returns_stable_index(self) -> None:
        led = ReferenceLedger()
        a = led.add({"source_type": "web", "url": "http://x", "title": "t", "content": "c", "relevance_score": 1.0})
        b = led.add({"source_type": "material", "content_id": 7, "page_number": 3, "content": "abc", "title": "d", "relevance_score": 0.9})
        c = led.add({"source_type": "web", "url": "http://x", "title": "t", "content": "c", "relevance_score": 1.0})
        self.assertEqual((a, b, c), (1, 2, 1))
        self.assertEqual(len(led), 2)

    def test_distinct_pages_are_distinct_refs(self) -> None:
        led = ReferenceLedger()
        a = led.add({"source_type": "material", "content_id": 7, "page_number": 1, "content": "abc", "title": "d", "relevance_score": 0.9})
        b = led.add({"source_type": "material", "content_id": 7, "page_number": 2, "content": "abc", "title": "d", "relevance_score": 0.8})
        self.assertNotEqual(a, b)

    def test_validate_inline_citations(self) -> None:
        self.assertEqual(validate_inline_citations("x [1] y [2]", 2), [])
        self.assertEqual(validate_inline_citations("x [3] y", 2), [3])
        # No refs collected -> every marker is dangling by definition
        self.assertEqual(validate_inline_citations("x [1] y", 0), [])


class SurfaceDirectiveTest(unittest.TestCase):
    def test_lesson_surface_is_grounded(self) -> None:
        directive = _surface_directive({
            "pageType": "lesson",
            "courseId": 3,
            "contentId": 42,
        })
        self.assertIn("GROUNDED LESSON MODE", directive)
        self.assertIn("primary source of truth", directive)

    def test_dashboard_surface_is_proactive(self) -> None:
        directive = _surface_directive({"pageType": "dashboard"})
        self.assertIn("PROACTIVE DASHBOARD MODE", directive)
        self.assertIn("get_study_plan", directive)

    def test_unknown_surface_neutral(self) -> None:
        directive = _surface_directive(None)
        self.assertIn("No page signal", directive)


if __name__ == "__main__":
    unittest.main()
