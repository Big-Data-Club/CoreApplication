"""
ai-service/tests/agents/test_react_core.py

Tests for Phase 3: ReAct Orchestrator Core.

Tests cover:
  1. Intent Router classification
  2. Clarification Gate logic
  3. System prompt building
  4. Tool schema injection format
  5. Full ReAct loop (requires Docker + Groq API key)

HOW TO RUN:
  # Schema/format tests (no Docker needed):
  cd ai-service
  python tests/agents/test_react_core.py --unit

  # Full integration test (Docker + live Groq API):
  cd ai-service
  python tests/agents/test_react_core.py

  # Single test:
  python tests/agents/test_react_core.py --test=intent_router
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

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
os.environ.setdefault("USE_RERANKER", "false")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None
        self.skipped = False

    def __repr__(self):
        if self.skipped:
            return f"  [SKIP] {self.name}"
        s = "PASS" if self.passed else "FAIL"
        e = f" - {self.error}" if self.error else ""
        return f"  [{s}] {self.name}{e}"


async def run_all_tests(unit_only: bool = False, single_test: str = None):
    results: list[TestResult] = []

    print("=" * 70)
    print("  BDC ReAct Orchestrator Core - Phase 3 Tests")
    print(f"  Mode: {'unit-only' if unit_only else 'full integration'}")
    print("=" * 70)

    # ── Test 1: System prompt building ───────────────────────────────────────
    if not single_test or single_test == "prompts":
        r = TestResult("Prompts: build_system_prompt for both agents")
        try:
            from app.agents.core.prompts import build_system_prompt

            # Teacher prompt
            teacher_prompt = build_system_prompt(
                agent_type="teacher",
                memory_context="STUDENT GAPS: Recursion, Inheritance",
            )
            assert "Virtual Teaching Assistant" in teacher_prompt
            assert "STUDENT GAPS: Recursion" in teacher_prompt
            assert "DRAFT" in teacher_prompt  # HITL reminder
            assert "{memory_context}" not in teacher_prompt  # placeholder replaced

            # Mentor prompt
            mentor_prompt = build_system_prompt(
                agent_type="mentor",
                memory_context="",
            )
            assert "Virtual Mentor" in mentor_prompt
            assert "Guided Discovery" in mentor_prompt
            assert "No additional context" in mentor_prompt  # empty fallback

            print(f"  [PASS] {r.name}")
            print(f"         Teacher prompt: {len(teacher_prompt)} chars")
            print(f"         Mentor prompt:  {len(mentor_prompt)} chars")
            r.passed = True
        except Exception as e:
            r.error = str(e)
            print(f"  [FAIL] {r.name} - {e}")
        results.append(r)

    # ── Test 2: Tool schema injection format ─────────────────────────────────
    if not single_test or single_test == "schema_format":
        r = TestResult("Schema: tool schemas match Groq format requirements")
        try:
            from app.agents.tools.registry import get_tool_schemas

            for agent_type in ["teacher", "mentor"]:
                schemas = get_tool_schemas(agent_type)
                assert len(schemas) >= 7

                for schema in schemas:
                    # Groq requires this exact structure
                    assert schema["type"] == "function"
                    assert "function" in schema
                    func = schema["function"]
                    assert isinstance(func["name"], str) and len(func["name"]) > 0
                    assert isinstance(func["description"], str)
                    assert isinstance(func["parameters"], dict)
                    assert func["parameters"]["type"] == "object"
                    assert "properties" in func["parameters"]

                    # Verify JSON serialisable
                    json.dumps(schema, ensure_ascii=False)

            print(f"  [PASS] {r.name}")
            r.passed = True
        except Exception as e:
            r.error = str(e)
            print(f"  [FAIL] {r.name} - {e}")
        results.append(r)

    # ── Test 3: Intent Router (requires Groq API) ───────────────────────────
    if not single_test or single_test == "intent_router":
        r = TestResult("Router: intent classification")

        if unit_only:
            r.skipped = True
            print(f"  [SKIP] {r.name} (requires Groq API)")
        else:
            try:
                from app.agents.core.router import classify_intent

                test_cases = [
                    ("Xin chào!", "general_chat"),
                    ("hi", "general_chat"),
                    ("ok", "general_chat"),
                ]

                for msg, expected in test_cases:
                    result = await classify_intent(msg)
                    assert result.intent == expected, (
                        f"'{msg}' -> got '{result.intent}', expected '{expected}'"
                    )

                # These require LLM - just check they return valid intents
                from app.agents.core.router import VALID_INTENTS

                complex_cases = [
                    "Đa hình trong OOP là gì?",
                    "Tạo 5 câu hỏi trắc nghiệm về vòng lặp",
                    "Tôi nên học gì tiếp theo?",
                ]
                for msg in complex_cases:
                    result = await classify_intent(msg)
                    assert result.intent in VALID_INTENTS, (
                        f"'{msg}' -> got '{result.intent}', not in VALID_INTENTS"
                    )
                    print(f"         '{msg[:30]}...' -> {result.intent}")

                print(f"  [PASS] {r.name}")
                r.passed = True
            except Exception as e:
                r.error = str(e)
                print(f"  [FAIL] {r.name} - {e}")
        results.append(r)

    # ── Test 4: Clarification Gate (requires Groq API) ──────────────────────
    if not single_test or single_test == "clarification":
        r = TestResult("Clarification: gate logic with tool schemas")

        if unit_only:
            r.skipped = True
            print(f"  [SKIP] {r.name} (requires Groq API)")
        else:
            try:
                from app.agents.core.clarification import should_clarify
                from app.agents.tools.registry import get_tool_schemas

                tool_schemas = get_tool_schemas("teacher")

                # Clear request - should NOT need clarification
                result = await should_clarify(
                    "Tạo 5 câu hỏi về OOP cho khóa học 1",
                    tool_schemas, {},
                )
                assert not result["needs_clarification"], (
                    f"Clear request should not trigger clarification: {result}"
                )
                print(f"         Clear request: no clarification ✓")

                # Short message - should skip
                result = await should_clarify("ok", tool_schemas, {})
                assert not result["needs_clarification"]
                print(f"         Short message: skipped ✓")

                print(f"  [PASS] {r.name}")
                r.passed = True
            except Exception as e:
                r.error = str(e)
                print(f"  [FAIL] {r.name} - {e}")
        results.append(r)

    # ── Test 5: Full ReAct loop (requires Docker + Groq) ────────────────────
    if not single_test or single_test == "react_loop":
        r = TestResult("ReAct: full loop with simple greeting")

        if unit_only:
            r.skipped = True
            print(f"  [SKIP] {r.name} (requires Docker + Groq API)")
        else:
            try:
                from app.core.database import init_ai_pool
                from app.agents.core.orchestrator import handle_chat_message
                from app.agents.events import AgentEventType

                await init_ai_pool()

                events = []
                start = time.monotonic()

                async for event in handle_chat_message(
                    user_id=99999,
                    agent_type="mentor",
                    message="Xin chào! Tôi muốn học OOP.",
                    course_id=1,
                ):
                    events.append(event)
                    print(f"         Event: {event.type.value}", end="")
                    if event.type == AgentEventType.TEXT_DELTA:
                        print(f" -> '{event.data.get('delta', '')[:30]}'", end="")
                    print()

                elapsed = (time.monotonic() - start) * 1000

                # Verify event sequence
                event_types = [e.type for e in events]
                assert AgentEventType.SESSION in event_types, "Missing SESSION event"
                assert AgentEventType.DONE in event_types, "Missing DONE event"

                # Should have a session_id in all events
                session_ids = set(e.session_id for e in events)
                assert len(session_ids) == 1, f"Multiple session IDs: {session_ids}"
                assert session_ids.pop() != "error"

                # Cleanup test session
                from app.core.database import get_ai_conn
                async with get_ai_conn() as conn:
                    await conn.execute(
                        "DELETE FROM agent_sessions WHERE user_id = $1", 99999,
                    )
                from app.agents.memory.stm import stm
                for e in events:
                    if e.type == AgentEventType.SESSION:
                        await stm.clear(e.data.get("session_id", ""))

                print(f"  [PASS] {r.name} - {len(events)} events, {elapsed:.0f}ms")
                r.passed = True
            except Exception as e:
                r.error = str(e)
                print(f"  [FAIL] {r.name} - {e}")
        results.append(r)

    # ── Test 6: API endpoint format ──────────────────────────────────────────
    if not single_test or single_test == "api_format":
        r = TestResult("API: ChatRequest model validation")
        try:
            from app.api.agent_router import ChatRequest

            # Valid request
            req = ChatRequest(
                message="Hello",
                agent_type="mentor",
                course_id=1,
                user_id=1,
            )
            assert req.message == "Hello"
            assert req.agent_type == "mentor"

            # Invalid agent_type
            try:
                ChatRequest(message="Hi", agent_type="hacker", user_id=1)
                assert False, "Should reject invalid agent_type"
            except Exception:
                pass  # Expected

            # Empty message
            try:
                ChatRequest(message="", agent_type="mentor", user_id=1)
                assert False, "Should reject empty message"
            except Exception:
                pass  # Expected

            print(f"  [PASS] {r.name}")
            r.passed = True
        except Exception as e:
            r.error = str(e)
            print(f"  [FAIL] {r.name} - {e}")
        results.append(r)

    # ── Test 7: Multi-agent Spawning score calculation ───────────────────────
    if not single_test or single_test == "spawning_score":
        r = TestResult("Multi-Agent: spawning score calculation and threshold validation")
        try:
            from app.agents.core.multi_agent_orchestrator import MultiAgentOrchestrator
            
            orchestrator = MultiAgentOrchestrator(session_id="test_session", turn_id="test_turn")
            
            # Case A: general_chat, low context pressure -> score should be low (< 0.5)
            score_a, breakdown_a = orchestrator.calculate_spawning_score(
                user_message="Hello, how are you?",
                intent_type="general_chat",
                parent_context_length=100,
                max_context_limit=32768
            )
            assert score_a < 0.5, f"General chat should have low score, got {score_a}"
            assert breakdown_a["d_intent"] == 0.1
            
            # Case B: content_creation intent -> score should be high (>= 0.5)
            score_b, breakdown_b = orchestrator.calculate_spawning_score(
                user_message="Tạo 5 câu hỏi trắc nghiệm về cấu trúc dữ liệu giải thuật",
                intent_type="content_creation",
                parent_context_length=5000,
                max_context_limit=32768
            )
            assert score_b >= 0.5, f"Content creation should trigger spawning, got {score_b}"
            assert breakdown_b["d_intent"] == 1.0
            assert breakdown_b["v_need"] == 1.0 # contains verification keyword 'trắc nghiệm'
            
            print(f"  [PASS] {r.name}")
            r.passed = True
        except Exception as e:
            r.error = str(e)
            print(f"  [FAIL] {r.name} - {e}")
        results.append(r)

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r.passed)
    skipped = sum(1 for r in results if r.skipped)
    total = len(results)
    print(f"  Results: {passed}/{total} passed, {skipped} skipped")
    print("=" * 70)

    if any(not r.passed and not r.skipped for r in results):
        print("\n  Failed tests:")
        for r in results:
            if not r.passed and not r.skipped:
                print(f"    - {r.name}: {r.error}")

    # Cleanup
    try:
        from app.core.database import close_ai_pool
        await close_ai_pool()
    except Exception:
        pass

    return all(r.passed or r.skipped for r in results)


if __name__ == "__main__":
    unit_only = "--unit" in sys.argv
    single_test = None
    for arg in sys.argv[1:]:
        if arg.startswith("--test="):
            single_test = arg.split("=", 1)[1]

    success = asyncio.run(run_all_tests(unit_only=unit_only, single_test=single_test))
    sys.exit(0 if success else 1)
