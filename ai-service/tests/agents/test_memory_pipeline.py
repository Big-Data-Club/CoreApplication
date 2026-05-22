"""
ai-service/tests/agents/test_memory_pipeline.py

Unit tests for Phase 1 Router Enhancements and prompt structures.

HOW TO RUN:
  cd ai-service
  python tests/agents/test_memory_pipeline.py --unit
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

# Proactively mock database libraries to allow tests to run without DB dependencies
sys.modules['asyncpg'] = MagicMock()
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.extras'] = MagicMock()

# Ensure environment is set to prevent crashes on DB imports
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
os.environ.setdefault("NEO4J_ENABLED", "false")
os.environ.setdefault("USE_QDRANT", "true")
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("USE_RERANKER", "false")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        err = f" — {self.error}" if self.error else ""
        return f"  [{status}] {self.name}{err}"


async def test_page_context_at_prompt_bottom() -> TestResult:
    r = TestResult("Prompts: page_context position at bottom")
    try:
        from app.agents.core.prompts import build_system_prompt

        # Build prompt
        prompt = build_system_prompt(
            agent_type="mentor",
            memory_context="[MEMORY CONTEXT HERE]",
            page_context={"type": "lesson", "course_id": 1, "body": "[PAGE CONTEXT HERE]"},
            system_context={"lesson_title": "Intro", "lesson_text": "[SYSTEM CONTEXT HERE]"}
        )

        # Check all are present
        assert "[MEMORY CONTEXT HERE]" in prompt
        assert "[PAGE CONTEXT HERE]" in prompt
        assert "[SYSTEM CONTEXT HERE]" in prompt

        # Verify page_context and system_context are at the bottom of the prompt (after memory_context)
        idx_memory = prompt.index("[MEMORY CONTEXT HERE]")
        idx_system = prompt.index("[SYSTEM CONTEXT HERE]")
        idx_page = prompt.index("[PAGE CONTEXT HERE]")

        assert idx_memory < idx_system, "memory_context should come before system_context"
        assert idx_system < idx_page, "system_context should come before page_context"
        assert idx_page > len(prompt) * 0.7, "page_context should be near the bottom of the prompt"

        r.passed = True
    except Exception as e:
        r.error = str(e)
    return r


async def test_router_ambiguity_detection() -> TestResult:
    r = TestResult("Router: ambiguity detection and structured output")
    try:
        from app.agents.core.router import classify_intent, RouterOutput

        active_courses = {
            "courses": [
                {"id": 1, "title": "Big Data"},
                {"id": 2, "title": "OOP"}
            ]
        }

        # Mock the structured LLM completion
        mock_output = RouterOutput(
            intent="content_creation",
            is_ambiguous=True,
            ambiguity_reason="unspecified_course",
            missing_context="Which course do you want to create a quiz for?",
            matched_course_id=None
        )

        with patch("app.agents.core.router.chat_complete_structured", new_callable=AsyncMock) as mock_structured:
            mock_structured.return_value = mock_output

            result = await classify_intent(
                user_message="Tạo 5 câu hỏi trắc nghiệm",
                active_courses=active_courses,
                agent_type="mentor"
            )

            assert result.intent == "content_creation"
            assert result.is_ambiguous is True
            assert result.ambiguity_reason == "unspecified_course"
            assert result.matched_course_id is None
            assert "Which course" in result.missing_context

            # Verify mock called with correct prompt parameters
            mock_structured.assert_called_once()
            called_messages = mock_structured.call_args[1]["messages"]
            system_prompt = called_messages[0]["content"]
            assert "Big Data" in system_prompt
            assert "OOP" in system_prompt

        r.passed = True
    except Exception as e:
        r.error = str(e)
    return r


async def test_router_matched_course_extraction() -> TestResult:
    r = TestResult("Router: course match extraction")
    try:
        from app.agents.core.router import classify_intent, RouterOutput

        active_courses = {
            "courses": [
                {"id": 10, "title": "Big Data"},
                {"id": 20, "title": "OOP"}
            ]
        }

        mock_output = RouterOutput(
            intent="knowledge_question",
            is_ambiguous=False,
            ambiguity_reason=None,
            missing_context=None,
            matched_course_id=10
        )

        with patch("app.agents.core.router.chat_complete_structured", new_callable=AsyncMock) as mock_structured:
            mock_structured.return_value = mock_output

            result = await classify_intent(
                user_message="ôn tập map reduce trong môn big data",
                active_courses=active_courses,
                agent_type="mentor"
            )

            assert result.intent == "knowledge_question"
            assert result.is_ambiguous is False
            assert result.matched_course_id == 10

        r.passed = True
    except Exception as e:
        r.error = str(e)
    return r


async def run_all_tests():
    print("=" * 70)
    print("  BDC Agent Memory Pipeline — Unit Tests")
    print("=" * 70)

    tests = [
        test_page_context_at_prompt_bottom,
        test_router_ambiguity_detection,
        test_router_matched_course_extraction,
    ]

    passed = 0
    for test in tests:
        res = await test()
        print(res)
        if res.passed:
            passed += 1

    print("=" * 70)
    print(f"  Results: {passed}/{len(tests)} passed")
    print("=" * 70)

    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
