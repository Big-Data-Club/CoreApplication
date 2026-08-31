"""
ai-service/app/agents/tools/registry.py

Tool Registry - maps agent types to their available tools.

This is the ONLY place where new tools need to be registered.
The ReAct loop calls `get_tools()` and `get_tool_schemas()` to
discover and invoke tools.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)

from app.agents.tools.teacher.recommend_review import RecommendReviewTool
from app.agents.tools.teacher.generate_content_draft import GenerateContentDraftTool
from app.agents.tools.teacher.trigger_auto_index import TriggerAutoIndexTool
from app.agents.tools.teacher.analyze_performance import AnalyzePerformanceTool
from app.agents.tools.teacher.generate_quiz_draft import GenerateQuizDraftTool
from app.agents.tools.teacher.generate_quiz_from_source import GenerateQuizFromSourceTool
from app.agents.tools.teacher.list_knowledge_nodes import ListKnowledgeNodesTool
from app.agents.tools.teacher.create_section import CreateSectionTool
from app.agents.tools.teacher.parse_quiz_questions import ParseQuizQuestionsTool
from app.agents.tools.teacher.prepare_course_materials import PrepareCourseMaterialsTool
from app.agents.tools.teacher.create_course_from_materials import CreateCourseFromMaterialsTool
from app.agents.tools.teacher.mcp_create_course_from_files import McpCreateCourseFromFilesTool
from app.agents.tools.teacher.mcp_batch_generate_quiz import McpBatchGenerateQuizTool
from app.agents.tools.teacher.mcp_generate_slide_deck import McpGenerateSlideDeckTool
from app.agents.tools.teacher.mcp_generate_report import McpGenerateReportTool
from app.agents.tools.teacher.mcp_index_files import McpIndexFilesTool
from app.agents.tools.teacher.mcp_create_lesson import McpCreateLessonTool
from app.agents.tools.shared.list_accessible_courses import ListAccessibleCoursesTool

# ── Mentor Tools ──────────────────────────────────────────────────────────────

from app.agents.tools.mentor.search_materials import SearchMaterialsTool
from app.agents.tools.mentor.diagnose_knowledge_gap import DiagnoseKnowledgeGapTool
from app.agents.tools.mentor.create_mini_challenge import CreateMiniChallengeTool
from app.agents.tools.mentor.generate_flashcard import GenerateFlashcardTool
from app.agents.tools.mentor.get_study_plan import GetStudyPlanTool
from app.agents.tools.mentor.get_recommendations import GetRecommendationsTool
from app.agents.tools.mentor.explain_concept import ExplainConceptTool
from app.agents.tools.mentor.search_web import SearchWebTool
from app.agents.tools.mentor.fetch_page import FetchPageTool
from app.agents.tools.mentor.save_to_notebook import SaveToNotebookTool

# ── Shared tools (available to both agents) ───────────────────────────────────

from app.agents.tools.teacher.list_my_courses import ListMyCoursesTool

_SHARED_TOOLS: list[BaseTool] = [
    ListAccessibleCoursesTool(),
    ListKnowledgeNodesTool(),
    SearchMaterialsTool(),
    SearchWebTool(),
    FetchPageTool(),
]

_TEACHER_ONLY_TOOLS: list[BaseTool] = [
    ListMyCoursesTool(),
    GenerateQuizDraftTool(),
    GenerateQuizFromSourceTool(),
    ParseQuizQuestionsTool(),
    AnalyzePerformanceTool(),
    TriggerAutoIndexTool(),
    GenerateContentDraftTool(),
    RecommendReviewTool(),
    CreateSectionTool(),
    PrepareCourseMaterialsTool(),
    CreateCourseFromMaterialsTool(),
    McpCreateCourseFromFilesTool(),
    McpBatchGenerateQuizTool(),
    McpGenerateSlideDeckTool(),
    McpGenerateReportTool(),
    McpIndexFilesTool(),
    McpCreateLessonTool(),
]

_MENTOR_ONLY_TOOLS: list[BaseTool] = [
    DiagnoseKnowledgeGapTool(),
    CreateMiniChallengeTool(),
    GenerateFlashcardTool(),
    GetStudyPlanTool(),
    GetRecommendationsTool(),
    ExplainConceptTool(),
    SaveToNotebookTool(),
]

# ── Public API ────────────────────────────────────────────────────────────────

_TOOL_REGISTRY: dict[str, list[BaseTool]] = {
    "teacher": _SHARED_TOOLS + _TEACHER_ONLY_TOOLS,
    "mentor":  _SHARED_TOOLS + _MENTOR_ONLY_TOOLS,
}

# Name-to-instance lookup (built lazily)
_NAME_LOOKUP: dict[str, BaseTool] = {}


def _ensure_lookup():
    if not _NAME_LOOKUP:
        for tools in _TOOL_REGISTRY.values():
            for tool in tools:
                _NAME_LOOKUP[tool.name] = tool


def get_tools(agent_type: str) -> list[BaseTool]:
    """Get all tool instances for an agent type."""
    return _TOOL_REGISTRY.get(agent_type, [])


def get_tool_schemas(agent_type: str) -> list[dict]:
    """
    Get OpenAI-compatible function calling schemas for an agent type.

    This is passed directly to the LLM in the `tools` parameter.
    """
    return [tool.to_function_schema() for tool in get_tools(agent_type)]


def get_tool_by_name(name: str) -> Optional[BaseTool]:
    """Look up a tool instance by name. Used by the ReAct executor."""
    _ensure_lookup()
    return _NAME_LOOKUP.get(name)


async def execute_tool(
    name: str,
    arguments: dict,
    user_id: int = 0,
    course_id: int | None = None,
    session_id: str | None = None,
    content_id: int | None = None,
    node_id: int | None = None,
    execution_plan: Any | None = None,
) -> ToolResult:
    """
    Execute a tool by name with the given arguments.

    Injects _user_id, _course_id, and _session_id into kwargs so tools can access
    the calling user's context without requiring them as explicit LLM parameters.
    """
    tool = get_tool_by_name(name)
    if not tool:
        return ToolResult(
            status="error",
            data={"error": f"Tool '{name}' not found"},
            message=f"Tool '{name}' not found in registry.",
        )

    # Inject user and course context
    arguments["_user_id"] = user_id
    if course_id is not None:
        arguments["_course_id"] = course_id
    if session_id is not None:
        arguments["_session_id"] = session_id
    if content_id is not None:
        arguments["_content_id"] = content_id
    if node_id is not None:
        arguments["_node_id"] = node_id
    if execution_plan is not None:
        arguments["execution_plan"] = execution_plan

    try:
        return await tool.execute(**arguments)
    except Exception as exc:
        logger.error("Tool '%s' execution failed: %s", name, exc)
        return ToolResult(
            status="error",
            data={"error": str(exc)},
            message=f"Tool execution error: {exc}",
        )


def list_all_tools() -> dict[str, list[str]]:
    """List all registered tools grouped by agent type. For debugging."""
    return {
        agent_type: [t.name for t in tools]
        for agent_type, tools in _TOOL_REGISTRY.items()
    }
