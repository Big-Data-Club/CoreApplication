"""
ai-service/tests/agents/test_memory_layers.py

Integration tests for the Agent Memory System.

HOW TO RUN:
───────────
These tests require the Docker services to be running (PostgreSQL, Redis, Qdrant).

  # From the project root:
  docker compose up -d postgres-ai redis-lms qdrant

  # Then run from ai-service/ directory:
  cd ai-service
  python -m pytest tests/agents/test_memory_layers.py -v --tb=short

  # Or run the standalone test script (no pytest needed):
  cd ai-service
  python tests/agents/test_memory_layers.py

ENVIRONMENT:
───────────
Make sure these env vars are set (matching your .env):
  AI_POSTGRES_DB=ai_db
  AI_POSTGRES_USER=ai_user
  AI_POSTGRES_PASSWORD=ai_password
  AI_DB_HOST=localhost
  AI_DB_PORT=5435
  REDIS_HOST=localhost
  REDIS_PORT=6379
  REDIS_PASSWORD=redis_password
  QDRANT_HOST=localhost
  QDRANT_PORT=6333
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

# ── Ensure environment is set for local testing ──────────────────────────────
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
os.environ.setdefault("NEO4J_ENABLED", "false")  # Skip Neo4j for basic tests
os.environ.setdefault("USE_QDRANT", "true")
os.environ.setdefault("GROQ_API_KEY", "test")  # Placeholder for config
os.environ.setdefault("USE_RERANKER", "false")

# Ensure we can import the app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ═══════════════════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        err = f" - {self.error}" if self.error else ""
        return f"  [{status}] {self.name}{err}"


async def run_all_tests():
    """Run all memory layer tests and print a summary."""
    results: list[TestResult] = []

    print("=" * 70)
    print("  BDC Agent Memory System - Integration Tests")
    print("=" * 70)

    # ── Test 1: STM (Redis) ──────────────────────────────────────────────────
    r = TestResult("STM: append and retrieve messages")
    try:
        from app.agents.memory.stm import stm

        session_id = str(uuid.uuid4())

        # Append messages
        await stm.append(session_id, "user", "Hello, I need help with OOP")
        await stm.append(session_id, "assistant", "Sure! What specifically?")
        await stm.append(session_id, "user", "What is polymorphism?")

        # Retrieve
        messages = await stm.get_window(session_id, n_turns=10)
        assert len(messages) == 3, f"Expected 3, got {len(messages)}"
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello, I need help with OOP"
        assert messages[2]["content"] == "What is polymorphism?"

        # Token count
        tokens = await stm.count_tokens(session_id)
        assert tokens > 0, f"Token count should be > 0, got {tokens}"

        # Should not be in overflow (too few tokens)
        overflow = await stm.check_token_overflow(session_id)
        assert not overflow, "Should not overflow with only 3 short messages"

        # Length
        length = await stm.length(session_id)
        assert length == 3, f"Expected length 3, got {length}"

        # Cleanup
        await stm.clear(session_id)
        length_after = await stm.length(session_id)
        assert length_after == 0, "STM should be empty after clear"

        r.passed = True
        print(f"  [PASS] {r.name}")
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 2: STM summarize and replace ─────────────────────────────────
    r = TestResult("STM: summarize and replace")
    try:
        from app.agents.memory.stm import stm

        session_id = str(uuid.uuid4())

        for i in range(10):
            await stm.append(session_id, "user", f"Message {i}")

        length_before = await stm.length(session_id)
        assert length_before == 10

        await stm.summarize_and_replace(
            session_id, "Summary of old messages", keep_last=2
        )

        length_after = await stm.length(session_id)
        assert length_after == 3, f"Expected 3 (1 summary + 2 kept), got {length_after}"

        messages = await stm.get_window(session_id, n_turns=10)
        assert "Tóm tắt" in messages[0]["content"]  # Summary message
        assert messages[-1]["content"] == "Message 9"  # newest kept

        await stm.clear(session_id)
        r.passed = True
        print(f"  [PASS] {r.name}")
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 3: MTM (PostgreSQL) ─────────────────────────────────────────────
    r = TestResult("MTM: create session and save compressed context")
    try:
        from app.agents.memory.mtm import mtm
        from app.core.database import init_ai_pool, close_ai_pool

        await init_ai_pool()

        test_user_id = 99999  # Test user

        # Create session
        session_data = await mtm.get_or_create_session(
            user_id=test_user_id,
            agent_type="mentor",
            course_id=1,
        )
        assert session_data["session_id"], "Should get a session_id"
        assert session_data["context"] == {} or isinstance(session_data["context"], dict)

        session_id = session_data["session_id"]

        # Save compressed context
        test_ctx = {
            "decisions_made": ["Use Vietnamese for explanations"],
            "content_created": [],
            "identified_gaps": ["Polymorphism", "Inheritance"],
            "student_progress": {"avg_mastery": 0.45},
            "pending_actions": ["Review OOP chapter"],
            "key_facts": {"preferred_language": "vi"},
        }
        await mtm.save_compressed(session_id, test_ctx, turn_count=5)

        # Retrieve
        retrieved = await mtm.get_context(session_id)
        assert retrieved.get("identified_gaps") == ["Polymorphism", "Inheritance"]
        assert retrieved.get("key_facts", {}).get("preferred_language") == "vi"

        # Get or create should return existing session
        session_data2 = await mtm.get_or_create_session(
            user_id=test_user_id,
            agent_type="mentor",
            course_id=1,
        )
        assert session_data2["session_id"] == session_id
        assert session_data2["turn_count"] == 5

        # Increment turn count
        new_count = await mtm.increment_turn_count(session_id)
        assert new_count == 6

        # List sessions
        sessions = await mtm.list_sessions(test_user_id, agent_type="mentor")
        assert len(sessions) >= 1
        assert any(s["session_id"] == session_id for s in sessions)

        # Cleanup
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            await conn.execute(
                "DELETE FROM agent_sessions WHERE user_id = $1", test_user_id
            )

        r.passed = True
        print(f"  [PASS] {r.name}")
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 4: LTM Qdrant collection ────────────────────────────────────────
    r = TestResult("LTM: ensure Qdrant collection exists")
    try:
        from app.agents.memory.ltm import ltm

        await ltm.ensure_collection()
        r.passed = True
        print(f"  [PASS] {r.name}")
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 5: (Removed - System Memory deleted) ────────────────────────

    # ── Test 6: Mastery Service ───────────────────────────────────────────
    r = TestResult("Mastery Service: get user struggles and strengths")
    try:
        from app.services.mastery_service import mastery_service

        struggles = await mastery_service.get_user_struggles(user_id=1, course_id=1)
        strengths = await mastery_service.get_user_strengths(user_id=1, course_id=1)
        assert isinstance(struggles, list)
        assert isinstance(strengths, list)
        r.passed = True
        print(f"  [PASS] {r.name} - struggles: {len(struggles)}, strengths: {len(strengths)}")
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 7: ContextBuilder ───────────────────────────────────────────────
    r = TestResult("ContextBuilder: build context for knowledge_question")
    try:
        from app.agents.memory.stm import stm
        from app.agents.memory.context_builder import context_builder

        # Prepare STM
        session_id = str(uuid.uuid4())
        await stm.append(session_id, "user", "Giải thích OOP cho tôi")
        await stm.append(session_id, "assistant", "OOP là lập trình hướng đối tượng...")

        context = await context_builder.build(
            user_id=1,
            session_id=session_id,
            agent_type="mentor",
            query="Đa hình là gì?",
            course_id=1,
            intent_type="knowledge_question",
        )

        assert isinstance(context, dict)
        assert "prompt_section" in context
        assert "stm_messages" in context
        assert "raw" in context
        assert "weights_used" in context
        assert "token_estimate" in context

        # Check STM was loaded
        assert len(context["stm_messages"]) == 2

        # Check weights match profile
        assert context["weights_used"]["stm"] == 0.9
        assert "system" not in context["weights_used"]

        await stm.clear(session_id)
        r.passed = True
        print(
            f"  [PASS] {r.name} - "
            f"tokens~{context['token_estimate']}, "
            f"prompt_len={len(context['prompt_section'])}"
        )
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 8: ContextBuilder with general_chat intent ──────────────────────
    r = TestResult("ContextBuilder: general_chat skips heavy retrieval")
    try:
        from app.agents.memory.context_builder import context_builder

        session_id = str(uuid.uuid4())
        await stm.append(session_id, "user", "Xin chào!")

        context = await context_builder.build(
            user_id=1,
            session_id=session_id,
            agent_type="mentor",
            query="Xin chào!",
            course_id=1,
            intent_type="general_chat",
        )

        # General chat should have low ltm_facts weight
        assert context["weights_used"]["ltm_facts"] <= 0.3
        assert "system" not in context["weights_used"]

        # System tier was removed entirely
        assert "system" not in context["raw"]

        await stm.clear(session_id)
        r.passed = True
        print(f"  [PASS] {r.name}")
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 9: Events schema ────────────────────────────────────────────────
    r = TestResult("Events: AgentEvent serialisation")
    try:
        from app.agents.events import AgentEvent, AgentEventType

        event = AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"delta": "Hello "},
            session_id="test-session",
            turn_id="turn-1",
        )

        sse = event.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")

        parsed = json.loads(sse.replace("data: ", "").strip())
        assert parsed["type"] == "text_delta"
        assert parsed["data"]["delta"] == "Hello "
        assert parsed["session_id"] == "test-session"

        r.passed = True
        print(f"  [PASS] {r.name}")
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"  Results: {passed}/{total} passed")
    print("=" * 70)

    if passed < total:
        print("\n  Failed tests:")
        for r in results:
            if not r.passed:
                print(f"    - {r.name}: {r.error}")

    # Cleanup
    try:
        from app.core.database import close_ai_pool
        await close_ai_pool()
    except Exception:
        pass

    try:
        from app.core.cache import close_cache
        await close_cache()
    except Exception:
        pass

    return passed == total


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
