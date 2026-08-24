"""Offline tests for LLM-output and tool-argument safety helpers."""
from __future__ import annotations

import unittest

from app.core.llm import ensure_dict
from app.agents.tools.base_tool import sanitize_query


class EnsureDictTest(unittest.TestCase):
    """chat_complete_json may parse to a top-level array - every caller that
    needs .get() must survive it (root cause of several production errors)."""

    def test_dict_passthrough(self) -> None:
        self.assertEqual(ensure_dict({"a": 1}), {"a": 1})

    def test_list_collapses_to_first_object(self) -> None:
        self.assertEqual(ensure_dict([1, "x", {"q": 1}, {"q": 2}]), {"q": 1})
        self.assertEqual(ensure_dict([]), {})
        self.assertEqual(ensure_dict(["str", 2]), {})

    def test_scalars_and_none_become_empty(self) -> None:
        for bad in ("text", 42, None, 3.14, True):
            self.assertEqual(ensure_dict(bad), {})


class SanitizeQueryTest(unittest.TestCase):
    def test_collapses_whitespace(self) -> None:
        self.assertEqual(sanitize_query("  data\nwarehouse\tETL  "), "data warehouse ETL")

    def test_caps_length_at_word_boundary(self) -> None:
        q = " ".join(["word"] * 200)
        out = sanitize_query(q, max_len=100)
        self.assertLessEqual(len(out), 100)
        self.assertFalse(out.endswith("wor"))  # cut at a space, not mid-word

    def test_non_string_input(self) -> None:
        self.assertEqual(sanitize_query(None), "")
        self.assertEqual(sanitize_query(123), "123")


if __name__ == "__main__":
    unittest.main()
