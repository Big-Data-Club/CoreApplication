"""Offline tests for planner-driven tool gating."""
from __future__ import annotations

import unittest

from app.agents.core.tool_gating import select_tool_schemas


def _schema(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


ALL = [_schema(n) for n in [
    "search_course_materials", "search_web", "fetch_page", "explain_concept",
    "diagnose_knowledge_gap", "create_mini_challenge", "generate_flashcard",
    "get_study_plan", "get_recommendations", "save_to_notebook",
    "list_knowledge_nodes", "list_my_courses",
]]


class ToolGatingTest(unittest.TestCase):
    def test_empty_selection_discloses_everything(self) -> None:
        schemas, gated = select_tool_schemas(ALL, [])
        self.assertFalse(gated)
        self.assertEqual(len(schemas), len(ALL))

    def test_focused_selection_is_small(self) -> None:
        schemas, gated = select_tool_schemas(
            ALL, ["explain_concept", "create_mini_challenge"],
        )
        self.assertTrue(gated)
        names = {s["function"]["name"] for s in schemas}
        # Strict: only what the planner chose (no retrieval core joined,
        # because none of the selected tools is itself a retrieval tool).
        self.assertEqual(names, {"explain_concept", "create_mini_challenge"})

    def test_retrieval_selection_expands_with_core(self) -> None:
        schemas, gated = select_tool_schemas(ALL, ["search_web"])
        self.assertTrue(gated)
        names = {s["function"]["name"] for s in schemas}
        self.assertTrue(names >= {"search_web", "search_course_materials", "fetch_page"})

    def test_non_retrieval_selection_stays_strict(self) -> None:
        schemas, gated = select_tool_schemas(ALL, ["save_to_notebook"])
        self.assertTrue(gated)
        self.assertEqual([s["function"]["name"] for s in schemas], ["save_to_notebook"])

    def test_planner_hallucinations_dropped(self) -> None:
        schemas, gated = select_tool_schemas(ALL, ["make_coffee", "explain_concept"])
        self.assertTrue(gated)
        names = {s["function"]["name"] for s in schemas}
        self.assertNotIn("make_coffee", names)
        self.assertIn("explain_concept", names)

    def test_large_selection_not_worth_gating(self) -> None:
        half_plus = ["search_course_materials", "search_web", "fetch_page",
                     "explain_concept", "diagnose_knowledge_gap", "generate_flashcard",
                     "get_study_plan"]
        schemas, gated = select_tool_schemas(ALL, half_plus)
        self.assertFalse(gated)
        self.assertEqual(len(schemas), len(ALL))


if __name__ == "__main__":
    unittest.main()
