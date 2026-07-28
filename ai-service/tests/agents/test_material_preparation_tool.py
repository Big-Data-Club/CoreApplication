"""Safety contract tests for the teacher material-inbox tool."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_HAS_RUNTIME_DEPS = importlib.util.find_spec("pydantic") is not None
if _HAS_RUNTIME_DEPS:
    from app.agents.tools.teacher.prepare_course_materials import PrepareCourseMaterialsTool


@unittest.skipUnless(_HAS_RUNTIME_DEPS, "ai-service dependencies are not installed")
class MaterialPreparationToolTests(unittest.TestCase):
    def test_opens_editable_workspace_without_side_effect(self):
        result = asyncio.run(PrepareCourseMaterialsTool().execute(_course_id=42, section_id=9))
        self.assertEqual(result.status, "pending_human_approval")
        self.assertEqual(result.ui_instruction["component"], "MaterialPreparationWorkspace")
        self.assertEqual(result.ui_instruction["props"], {"course_id": 42, "section_id": 9})

    def test_refuses_to_guess_a_course(self):
        result = asyncio.run(PrepareCourseMaterialsTool().execute())
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["error"], "course_required")


if __name__ == "__main__":
    unittest.main()
