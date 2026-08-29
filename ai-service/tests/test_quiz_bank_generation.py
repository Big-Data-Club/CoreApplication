from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GROQ_API_KEY", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep this contract test independent of optional production SDKs.
database_stub = types.ModuleType("app.core.database")
database_stub.get_ai_conn = None
llm_stub = types.ModuleType("app.core.llm")
llm_stub.chat_complete_json = AsyncMock()
llm_stub.build_quiz_generation_prompt = lambda **kwargs: []
gateway_stub = types.ModuleType("app.core.llm_gateway")
gateway_stub.TASK_QUIZ_GEN = "quiz_gen"
rag_stub = types.ModuleType("app.services.rag_service")
rag_stub.rag_service = types.SimpleNamespace()
config_stub = types.ModuleType("app.core.config")
config_stub.get_settings = lambda: types.SimpleNamespace(quiz_model="test")

sys.modules.setdefault("app.core.database", database_stub)
sys.modules.setdefault("app.core.llm", llm_stub)
sys.modules.setdefault("app.core.llm_gateway", gateway_stub)
sys.modules.setdefault("app.services.rag_service", rag_stub)
sys.modules.setdefault("app.core.config", config_stub)

from app.services import quiz_service as quiz_module
from app.services.quiz_service import QuizGenerationService


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class QuizBankGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_nodes_are_scoped_by_course(self) -> None:
        conn = types.SimpleNamespace()
        conn.fetch = AsyncMock(return_value=[{"id": 7, "name": "Indexing"}])
        service = QuizGenerationService()
        generated = {
            "node_id": 7,
            "question_type": "SINGLE_CHOICE",
            "question_text": "What is an index?",
            "points": 10,
            "bloom_level": "remember",
            "difficulty": "EASY",
            "answer_options": [],
            "correct_answers": [],
            "settings": {},
            "explanation": "",
            "source": "AI_GENERATED",
        }

        with patch.object(quiz_module, "get_ai_conn", return_value=_ConnectionContext(conn)), patch.object(
            service, "_generate_one_for_bank", new=AsyncMock(return_value=(generated, ""))
        ):
            questions, rejected = await service.generate_for_bank(
                course_id=2, count=1, node_ids=[7, 7], bloom_levels=["remember"]
            )

        query, course_id, node_ids, _limit = conn.fetch.await_args.args
        self.assertIn("course_id = $1 AND id = ANY($2::bigint[])", query)
        self.assertEqual(course_id, 2)
        self.assertEqual(node_ids, [7])
        self.assertEqual(len(questions), 1)
        self.assertEqual(rejected, 0)

    async def test_rag_fallback_keeps_course_scope(self) -> None:
        rag = types.SimpleNamespace(
            search_by_node_ids=AsyncMock(return_value=[]),
            search_multilingual=AsyncMock(return_value=[]),
        )
        service = QuizGenerationService()

        with patch.object(quiz_module, "rag_service", rag), patch.object(
            quiz_module,
            "chat_complete_json",
            new=AsyncMock(return_value={
                "question_text": "What does this concept mean?",
                "answer_options": [
                    {"option_text": "A", "is_correct": True},
                    {"option_text": "B", "is_correct": False},
                ],
            }),
        ):
            question, error = await service._generate_one_for_bank(
                7, 2, "Indexing", "remember", "vi", []
            )

        self.assertEqual(error, "")
        self.assertIsNotNone(question)
        self.assertEqual(rag.search_multilingual.await_args.kwargs["course_id"], 2)


if __name__ == "__main__":
    unittest.main()
