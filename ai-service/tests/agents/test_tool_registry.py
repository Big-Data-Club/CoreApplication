"""
ai-service/tests/agents/test_tool_registry.py

Tests for the Phase 2 Tool Registry system.

Tests validate:
  1. Tool registration and schema generation
  2. Tool lookup by name
  3. JSON Schema format compatibility with OpenAI function calling
  4. Tool execution with mocked services (no real LLM/DB calls)

HOW TO RUN:
  cd ai-service
  python tests/agents/test_tool_registry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

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


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None

    def __repr__(self):
        s = "PASS" if self.passed else "FAIL"
        e = f" - {self.error}" if self.error else ""
        return f"  [{s}] {self.name}{e}"


async def run_all_tests():
    results: list[TestResult] = []

    print("=" * 70)
    print("  BDC Agent Tool Registry - Tests")
    print("=" * 70)

    # ── Test 1: Teacher tools registered ─────────────────────────────────────
    r = TestResult("Registry: teacher tools are registered")
    try:
        from app.agents.tools.registry import get_tools, list_all_tools

        teacher_tools = get_tools("teacher")
        assert len(teacher_tools) >= 7, f"Expected >= 7 teacher tools, got {len(teacher_tools)}"

        all_tools = list_all_tools()
        assert "teacher" in all_tools
        assert "mentor" in all_tools

        print(f"  [PASS] {r.name} - {len(teacher_tools)} tools")
        r.passed = True
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 2: Mentor tools registered ──────────────────────────────────────
    r = TestResult("Registry: mentor tools are registered")
    try:
        from app.agents.tools.registry import get_tools

        mentor_tools = get_tools("mentor")
        assert len(mentor_tools) >= 7, f"Expected >= 7 mentor tools, got {len(mentor_tools)}"

        tool_names = [t.name for t in mentor_tools]
        assert "search_course_materials" in tool_names
        assert "create_mini_challenge" in tool_names
        assert "diagnose_knowledge_gap" in tool_names
        assert "get_study_plan" in tool_names
        assert "explain_concept" in tool_names
        assert "generate_flashcard" in tool_names

        print(f"  [PASS] {r.name} - {len(mentor_tools)} tools")
        r.passed = True
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 3: Schema generation ────────────────────────────────────────────
    r = TestResult("Schema: valid OpenAI function calling format")
    try:
        from app.agents.tools.registry import get_tool_schemas

        schemas = get_tool_schemas("teacher")
        assert len(schemas) >= 7

        for schema in schemas:
            assert schema["type"] == "function", f"Expected type=function, got {schema['type']}"
            func = schema["function"]
            assert "name" in func, "Missing 'name' in function schema"
            assert "description" in func, "Missing 'description' in function schema"
            assert "parameters" in func, "Missing 'parameters' in function schema"
            params = func["parameters"]
            assert params["type"] == "object", f"Expected parameters.type=object"
            assert "properties" in params, "Missing 'properties' in parameters"

        # Print one schema for manual verification
        sample = schemas[0]
        print(f"  [PASS] {r.name} - {len(schemas)} schemas")
        print(f"         Sample: {sample['function']['name']}")
        r.passed = True
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 4: Tool lookup by name ──────────────────────────────────────────
    r = TestResult("Registry: tool lookup by name works")
    try:
        from app.agents.tools.registry import get_tool_by_name

        tool = get_tool_by_name("generate_quiz_draft")
        assert tool is not None, "generate_quiz_draft not found"
        assert tool.name == "generate_quiz_draft"

        tool = get_tool_by_name("search_course_materials")
        assert tool is not None, "search_course_materials not found"

        tool = get_tool_by_name("nonexistent_tool")
        assert tool is None, "Should return None for nonexistent tool"

        print(f"  [PASS] {r.name}")
        r.passed = True
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 5: Execute nonexistent tool ─────────────────────────────────────
    r = TestResult("Execute: nonexistent tool returns error")
    try:
        from app.agents.tools.registry import execute_tool

        result = await execute_tool("nonexistent", {})
        assert result.status == "error"
        assert "not found" in result.message.lower()

        print(f"  [PASS] {r.name}")
        r.passed = True
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 6: Schema is valid JSON ─────────────────────────────────────────
    r = TestResult("Schema: all schemas serialise to valid JSON")
    try:
        from app.agents.tools.registry import get_tool_schemas

        for agent_type in ["teacher", "mentor"]:
            schemas = get_tool_schemas(agent_type)
            json_str = json.dumps(schemas, ensure_ascii=False)
            parsed = json.loads(json_str)
            assert len(parsed) == len(schemas)

        print(f"  [PASS] {r.name}")
        r.passed = True
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 7: Shared tools appear in both agents ───────────────────────────
    r = TestResult("Registry: shared tools appear in both agents")
    try:
        from app.agents.tools.registry import get_tools

        teacher_names = {t.name for t in get_tools("teacher")}
        mentor_names = {t.name for t in get_tools("mentor")}

        # list_knowledge_nodes and search_course_materials are shared
        assert "list_knowledge_nodes" in teacher_names
        assert "list_knowledge_nodes" in mentor_names
        assert "search_course_materials" in teacher_names
        assert "search_course_materials" in mentor_names

        # Teacher-only tools
        assert "generate_quiz_draft" in teacher_names
        assert "generate_quiz_draft" not in mentor_names

        # Mentor-only tools
        assert "create_mini_challenge" in mentor_names
        assert "create_mini_challenge" not in teacher_names

        print(f"  [PASS] {r.name}")
        r.passed = True
    except Exception as e:
        r.error = str(e)
        print(f"  [FAIL] {r.name} - {e}")
    results.append(r)

    # ── Test 8: Print all tool schemas (informational) ───────────────────────
    r = TestResult("Info: print all tool schemas for manual review")
    try:
        from app.agents.tools.registry import list_all_tools

        all_t = list_all_tools()
        print(f"  [PASS] {r.name}")
        for agent_type, names in all_t.items():
            print(f"         {agent_type}: {', '.join(names)}")
        r.passed = True
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
        for r2 in results:
            if not r2.passed:
                print(f"    - {r2.name}: {r2.error}")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
