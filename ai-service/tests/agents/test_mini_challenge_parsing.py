"""
Tests for robust MCQ option parsing and dynamic retrieval depth in the Mentor tools.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

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

from app.agents.core.sub_agents import RetrievalSpecialist
from app.agents.events import AgentEvent
from app.agents.tools.mentor.create_mini_challenge import CreateMiniChallengeTool
from app.agents.tools.mentor.explain_concept import ExplainConceptTool
from app.agents.tools.base_tool import ToolResult

class TestMentorEnhancements(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        from app.services.rag_service import rag_service
        self.original_search_multilingual = rag_service.search_multilingual
        self.original_search_hierarchical = rag_service.search_hierarchical
        rag_service.search_multilingual = AsyncMock(return_value=[])
        rag_service.search_hierarchical = AsyncMock(return_value=([], "course"))

    def tearDown(self):
        from app.services.rag_service import rag_service
        rag_service.search_multilingual = self.original_search_multilingual
        rag_service.search_hierarchical = self.original_search_hierarchical

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
        from app.core.config import get_settings
        settings = get_settings()
        
        original_graphrag_enabled = settings.graphrag_enabled
        original_search = rag_service.search_hierarchical
        original_chat_complete = llm.chat_complete
        
        settings.graphrag_enabled = False
        rag_service.search_hierarchical = AsyncMock(return_value=([], "course"))
        llm.chat_complete = AsyncMock(return_value="Detailed Explanation")

        try:
            # 1. Advanced depth
            await tool.execute(concept="MapReduce", course_id=1, depth="advanced")
            rag_service.search_hierarchical.assert_called_with(
                query="MapReduce",
                course_id=1,
                section_id=None,
                content_id=None,
                top_k=8,
                min_similarity=0.25,
                expansion_enabled=True,
                max_expansion_level="global",
            )

            # 2. Beginner depth
            await tool.execute(concept="MapReduce", course_id=1, depth="beginner")
            rag_service.search_hierarchical.assert_called_with(
                query="MapReduce",
                course_id=1,
                section_id=None,
                content_id=None,
                top_k=3,
                min_similarity=0.25,
                expansion_enabled=True,
                max_expansion_level="global",
            )

            # 3. Intermediate depth
            await tool.execute(concept="MapReduce", course_id=1, depth="intermediate")
            rag_service.search_hierarchical.assert_called_with(
                query="MapReduce",
                course_id=1,
                section_id=None,
                content_id=None,
                top_k=5,
                min_similarity=0.25,
                expansion_enabled=True,
                max_expansion_level="global",
            )
        finally:
            settings.graphrag_enabled = original_graphrag_enabled
            rag_service.search_hierarchical = original_search
            llm.chat_complete = original_chat_complete

    async def test_retrieval_specialist_stops_when_content_is_not_indexed(self):
        """RetrievalSpecialist should surface a non-fabricated message when the lesson is not indexed."""
        specialist = RetrievalSpecialist(session_id="session-1", turn_id="turn-1")
        page_context = {"nodeId": 42, "courseId": 7, "contentTitle": "Giới thiệu về AI"}

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"status": "pending"})
        conn_manager = MagicMock()
        conn_manager.__aenter__.return_value = conn
        conn_manager.__aexit__.return_value = None

        import app.agents.core.sub_agents as sub_agents_module

        with patch.object(sub_agents_module, "get_ai_conn", return_value=conn_manager), \
             patch.object(sub_agents_module.rag_service, "search_multilingual", AsyncMock(return_value=[])), \
             patch.object(sub_agents_module.SearchWebTool, "execute", AsyncMock(return_value=MagicMock(status="success", data={"results": []}))):
            items = []
            async for item in specialist.execute(query="Explain this lesson", page_context=page_context):
                items.append(item)

        self.assertTrue(any(isinstance(item, AgentEvent) and item.data.get("status") == "not_indexed" for item in items))
        self.assertTrue(any(isinstance(item, str) and "has not been indexed yet" in item for item in items))

if __name__ == "__main__":
    unittest.main()
