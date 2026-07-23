from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GROQ_API_KEY", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep these unit tests independent of optional provider SDKs. The production
# symbols are patched below before any call is made.
llm_stub = types.ModuleType("app.core.llm")
llm_stub.chat_complete_json = AsyncMock()
gateway_stub = types.ModuleType("app.core.llm_gateway")
gateway_stub.TASK_QUIZ_GEN = "quiz_gen"
sys.modules.setdefault("app.core.llm", llm_stub)
sys.modules.setdefault("app.core.llm_gateway", gateway_stub)

from app.core.llm_gateway import TASK_QUIZ_GEN
from app.services.quiz_parse_service import QuizParseService


class QuizParseNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QuizParseService()

    def test_dropdown_blanks_keep_options_grouped_by_blank(self) -> None:
        raw = [{
            "question_type": "FILL_BLANK_DROPDOWN",
            "question_text": "Use {BLANK_1} to lock and {BLANK_2} to install.",
            "answer_options": [
                {"option_text": "uv lock", "is_correct": True, "blank_id": 1},
                {"option_text": "uv sync", "is_correct": False, "blank_id": 1},
                {"option_text": "uv sync", "is_correct": True, "blank_id": 2},
                {"option_text": "uv build", "is_correct": False, "blank_id": 2},
            ],
            "correct_answers": [],
            "settings": None,
        }]

        questions = self.service._normalize(raw, 10)

        self.assertEqual(len(questions), 1)
        question = questions[0]
        self.assertEqual(question["settings"]["blank_count"], 2)
        self.assertEqual([o["blank_id"] for o in question["answer_options"]], [1, 1, 2, 2])

    def test_invalid_choice_question_is_not_offered_to_teacher(self) -> None:
        raw = [{
            "question_type": "SINGLE_CHOICE",
            "question_text": "Which command?",
            "answer_options": [
                {"option_text": "uv lock", "is_correct": True},
                {"option_text": "uv sync", "is_correct": True},
            ],
        }]
        self.assertEqual(self.service._normalize(raw, 10), [])

    def test_long_pastes_are_split_on_paragraph_boundaries(self) -> None:
        text = ("Question one\n\n" + "x" * 7000 + "\n\n" + "Question two\n\n" + "y" * 7000)
        chunks = self.service._chunk_text(text, max_chars=8000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 8000 for chunk in chunks))


class QuizSourceGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_forwards_dropdown_format_instruction(self) -> None:
        service = QuizParseService()
        response = [{
            "question_type": "FILL_BLANK_DROPDOWN",
            "question_text": "Use {BLANK_1} to install locked dependencies.",
            "answer_options": [
                {"option_text": "uv sync", "is_correct": True, "blank_id": 1},
                {"option_text": "uv build", "is_correct": False, "blank_id": 1},
            ],
            "correct_answers": [],
            "settings": None,
        }]
        with patch(
            "app.services.quiz_parse_service.chat_complete_json",
            new=AsyncMock(return_value=response),
        ) as mocked:
            questions = await service.parse(
                "Use ___ to install locked dependencies.",
                instructions="Use a dropdown blank",
            )

        self.assertEqual(questions[0]["question_type"], "FILL_BLANK_DROPDOWN")
        self.assertIn("Use a dropdown blank", mocked.await_args.kwargs["messages"][1]["content"])

    async def test_generation_uses_quiz_gateway_task_and_requested_language(self) -> None:
        service = QuizParseService()
        response = [{
            "question_type": "SINGLE_CHOICE",
            "question_text": "Which command updates uv?",
            "answer_options": [
                {"option_text": "uv self update", "is_correct": True},
                {"option_text": "uv build", "is_correct": False},
            ],
            "correct_answers": [],
            "settings": None,
            "explanation": "The standalone installer supports uv self update.",
        }]

        with patch(
            "app.services.quiz_parse_service.chat_complete_json",
            new=AsyncMock(return_value=response),
        ) as mocked:
            questions = await service.generate_from_source(
                source_text="uv self update updates an installer-managed uv.",
                num_questions=1,
                language="English",
            )

        self.assertEqual(len(questions), 1)
        call = mocked.await_args.kwargs
        self.assertEqual(call["task"], TASK_QUIZ_GEN)
        self.assertIn("Output language: English", call["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
