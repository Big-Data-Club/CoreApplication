"""
Tests for robust MCQ option parsing and dynamic retrieval depth in the Mentor tools.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

# Setup dummy env vars before importing anything
os.environ.setdefault("AI_DB_HOST", "localhost")
os.environ.setdefault("AI_DB_PORT", "5435")
os.environ.setdefault("AI_DB_USER", "ai_user")
os.environ.setdefault("AI_DB_PASSWORD", "ai_password")
os.environ.setdefault("AI_DB_NAME", "ai_db")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "redis_password")
os.environ.setdefault("REDIS_DB", "1")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")
os.environ.setdefault("QDRANT_GRPC_PORT", "6334")
os.environ.setdefault("QDRANT_PREFER_GRPC", "false")
os.environ.setdefault("NEO4J_ENABLED", "false")
os.environ.setdefault("USE_QDRANT", "true")
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("USE_RERANKER", "false")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.tools.mentor.create_mini_challenge import CreateMiniChallengeTool
from app.agents.tools.mentor.explain_concept import ExplainConceptTool
from app.agents.tools.base_tool import ToolResult

class TestMentorEnhancements(unittest.IsolatedAsyncioTestCase):

    async def test_mcq_robust_parsing_standard_strings_with_prefixes(self):
        """Test parsing standard list of strings with diverse prefix structures."""
        tool = CreateMiniChallengeTool()
        
        # 1. Standard A. B. C. D. prefixes
        result_mock = {
            "question": "What is MapReduce?",
            "options": [
                "A. A distributed processing model",
                "B. A database system",
                "C. A virtualization tool",
                "D. A frontend framework"
            ],
            "correct_answer": "A",
            "explanation": "MapReduce divides and processes data in parallel."
        }
        
        # We temporarily mock the chat_complete_json internally
        from app.core import llm
        original_chat_complete_json = llm.chat_complete_json
        llm.chat_complete_json = AsyncMock(return_value=result_mock)

        try:
            res: ToolResult = await tool.execute(concept="MapReduce", course_id=1)
            self.assertEqual(res.status, "success")
            opts = res.ui_instruction["props"]["options"]
            self.assertEqual(len(opts), 4)
            self.assertEqual(opts[0]["text"], "A distributed processing model")
            self.assertTrue(opts[0]["is_correct"])
            self.assertEqual(opts[1]["text"], "A database system")
            self.assertFalse(opts[1]["is_correct"])
        finally:
            llm.chat_complete_json = original_chat_complete_json

    async def test_mcq_robust_parsing_lowercase_and_varied_separators(self):
        """Test parsing case-insensitive and varied prefixes like a), A:, a."""
        tool = CreateMiniChallengeTool()
        
        result_mock = {
            "question": "What is HDFS?",
            "options": [
                "a) Distributed storage",
                "B: Relational database",
                "c Graphic UI",
                "D. Web server"
            ],
            "correct_answer": "a",
            "explanation": "HDFS stands for Hadoop Distributed File System."
        }
        
        from app.core import llm
        original_chat_complete_json = llm.chat_complete_json
        llm.chat_complete_json = AsyncMock(return_value=result_mock)

        try:
            res: ToolResult = await tool.execute(concept="HDFS", course_id=1)
            self.assertEqual(res.status, "success")
            opts = res.ui_instruction["props"]["options"]
            self.assertEqual(opts[0]["text"], "Distributed storage")
            self.assertTrue(opts[0]["is_correct"])
            self.assertEqual(opts[1]["text"], "Relational database")
            self.assertFalse(opts[1]["is_correct"])
            self.assertEqual(opts[2]["text"], "Graphic UI")
            self.assertEqual(opts[3]["text"], "Web server")
        finally:
            llm.chat_complete_json = original_chat_complete_json

    async def test_mcq_robust_parsing_nested_dictionaries(self):
        """Test parsing nested dictionaries inside the options list."""
        tool = CreateMiniChallengeTool()
        
        result_mock = {
            "question": "Which of these is correct?",
            "options": [
                {"text": "A. Map is correct", "is_correct": True},
                {"option_text": "B. Reduce is correct", "is_correct": False},
                {"value": "C. Both are incorrect", "is_correct": False},
                {"content": "D. None", "is_correct": False}
            ],
            "correct_answer": "A",
            "explanation": "Map divides, Reduce combines."
        }
        
        from app.core import llm
        original_chat_complete_json = llm.chat_complete_json
        llm.chat_complete_json = AsyncMock(return_value=result_mock)

        try:
            res: ToolResult = await tool.execute(concept="MapReduce", course_id=1)
            opts = res.ui_instruction["props"]["options"]
            self.assertEqual(opts[0]["text"], "Map is correct")
            self.assertTrue(opts[0]["is_correct"])
            self.assertEqual(opts[1]["text"], "Reduce is correct")
            self.assertEqual(opts[2]["text"], "Both are incorrect")
            self.assertEqual(opts[3]["text"], "None")
        finally:
            llm.chat_complete_json = original_chat_complete_json

    async def test_mcq_robust_parsing_dictionary_keys_fallback(self):
        """Test parsing options representing a dict mapping or weird keys like {'A': 'text'}."""
        tool = CreateMiniChallengeTool()
        
        result_mock = {
            "question": "What is the answer?",
            "options": [
                {"A": "Alpha"},
                {"B": "Beta"},
                {"C": "Gamma"},
                {"D": "Delta"}
            ],
            "correct_answer": "A",
            "explanation": "Alpha is first."
        }
        
        from app.core import llm
        original_chat_complete_json = llm.chat_complete_json
        llm.chat_complete_json = AsyncMock(return_value=result_mock)

        try:
            res: ToolResult = await tool.execute(concept="Alpha", course_id=1)
            opts = res.ui_instruction["props"]["options"]
            self.assertEqual(opts[0]["text"], "Alpha")
            self.assertTrue(opts[0]["is_correct"])
            self.assertEqual(opts[1]["text"], "Beta")
        finally:
            llm.chat_complete_json = original_chat_complete_json

    async def test_mcq_robust_parsing_prevent_blank_options_and_ellipsis(self):
        """Test that if LLM returns pure placeholders like '...' or stripping leaves nothing, we fall back gracefully."""
        tool = CreateMiniChallengeTool()
        
        result_mock = {
            "question": "Placeholder question",
            "options": [
                "A. ...",
                "B. ",
                "C. ___",
                "D. Valid option"
            ],
            "correct_answer": "D",
            "explanation": "None."
        }
        
        from app.core import llm
        original_chat_complete_json = llm.chat_complete_json
        llm.chat_complete_json = AsyncMock(return_value=result_mock)

        try:
            res: ToolResult = await tool.execute(concept="Placeholder", course_id=1)
            opts = res.ui_instruction["props"]["options"]
            self.assertEqual(opts[0]["text"], "A. ...")  # Preserved or fell back to raw
            self.assertEqual(opts[1]["text"], "Option B") # Graceful text placeholder
            self.assertEqual(opts[2]["text"], "C. ___")  # Preserved or fell back to raw
            self.assertEqual(opts[3]["text"], "Valid option")
        finally:
            llm.chat_complete_json = original_chat_complete_json

    async def test_dynamic_retrieval_depth_in_explain_concept(self):
        """Verify explain_concept tool adapts top_k depending on depth."""
        tool = ExplainConceptTool()

        from app.services.rag_service import rag_service
        from app.core import llm
        original_search = rag_service.search_multilingual
        original_chat_complete = llm.chat_complete
        
        rag_service.search_multilingual = AsyncMock(return_value=[])
        llm.chat_complete = AsyncMock(return_value="Detailed Explanation")

        try:
            # 1. Advanced depth
            await tool.execute(concept="MapReduce", course_id=1, depth="advanced")
            rag_service.search_multilingual.assert_called_with(
                query="MapReduce", course_id=1, top_k=8
            )

            # 2. Beginner depth
            await tool.execute(concept="MapReduce", course_id=1, depth="beginner")
            rag_service.search_multilingual.assert_called_with(
                query="MapReduce", course_id=1, top_k=3
            )

            # 3. Intermediate depth
            await tool.execute(concept="MapReduce", course_id=1, depth="intermediate")
            rag_service.search_multilingual.assert_called_with(
                query="MapReduce", course_id=1, top_k=5
            )
        finally:
            rag_service.search_multilingual = original_search
            llm.chat_complete = original_chat_complete

if __name__ == "__main__":
    unittest.main()
