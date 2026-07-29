"""Pure-stdlib tests for the provider-independent token budget helpers."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


_PATH = Path(__file__).resolve().parents[1] / "app/core/llm_gateway/token_budget.py"
_SPEC = importlib.util.spec_from_file_location("token_budget_under_test", _PATH)
assert _SPEC and _SPEC.loader
budget = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(budget)


class TokenBudgetTests(unittest.TestCase):
    def test_large_source_is_split_without_losing_characters(self) -> None:
        source = ("Khái niệm quan trọng trong bài học. " * 900) + "KẾT THÚC"
        batches = budget.pack_by_token_budget([source], max_tokens=500)
        reconstructed = "".join(part for batch in batches for part in batch)

        self.assertGreater(len(batches), 1)
        self.assertEqual(reconstructed, source)
        self.assertTrue(all(
            budget.estimate_tokens(part) <= 500
            for batch in batches for part in batch
        ))

    def test_message_estimate_includes_structured_content(self) -> None:
        messages = [{
            "role": "user",
            "content": [{"type": "text", "text": "Nội dung"}],
        }]
        self.assertGreater(budget.estimate_messages_tokens(messages), 1)


if __name__ == "__main__":
    unittest.main()
