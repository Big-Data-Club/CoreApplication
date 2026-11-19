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
from app.agents.tools.execution_policy import (
    COURSE_REQUIRED_TOOLS, DIRECT_WRITE_TOOLS, READ_ONLY_COURSE_TOOLS, authorize_course, deny,
)

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
from app.agents.tools.teacher.mcp_apply_course_blueprint import McpApplyCourseBlueprintTool
from app.agents.tools.teacher.mcp_batch_generate_quiz import McpBatchGenerateQuizTool
from app.agents.tools.teacher.mcp_generate_slide_deck import McpGenerateSlideDeckTool
from app.agents.tools.teacher.mcp_generate_report import McpGenerateReportTool
from app.agents.tools.teacher.mcp_index_files import McpIndexFilesTool
from app.agents.tools.teacher.mcp_create_lesson import McpCreateLessonTool
from app.agents.tools.teacher.mcp_course_knowledge import (
    McpCourseKnowledgeReadTool,
    McpSaveCourseKnowledgeTool,
)
from app.agents.tools.shared.list_accessible_courses import ListAccessibleCoursesTool
from app.agents.tools.shared.recall_conversation import RecallConversationTool

# ── Mentor Tools ──────────────────────────────────────────────────────────────

from app.agents.tools.mentor.search_materials import SearchMaterialsTool
from app.agents.tools.mentor.diagnose_knowledge_gap import DiagnoseKnowledgeGapTool
from app.agents.tools.mentor.create_mini_challenge import CreateMiniChallengeTool
from app.agents.tools.mentor.get_study_plan import GetStudyPlanTool
from app.agents.tools.mentor.get_recommendations import GetRecommendationsTool
from app.agents.tools.mentor.explain_concept import ExplainConceptTool
from app.agents.tools.mentor.search_web import SearchWebTool
from app.agents.tools.mentor.fetch_page import FetchPageTool
from app.agents.tools.mentor.save_to_notebook import SaveToNotebookTool

# ── Shared tools (available to both agents) ───────────────────────────────────

from app.agents.tools.teacher.list_my_courses import ListMyCoursesTool

_SHARED_TOOLS: list[BaseTool] = [
    RecallConversationTool(),
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
    McpApplyCourseBlueprintTool(),
    McpBatchGenerateQuizTool(),
    McpGenerateSlideDeckTool(),
    McpGenerateReportTool(),
    McpIndexFilesTool(),
    McpCreateLessonTool(),
    McpCourseKnowledgeReadTool(),
    McpSaveCourseKnowledgeTool(),
]

_MENTOR_ONLY_TOOLS: list[BaseTool] = [
    DiagnoseKnowledgeGapTool(),
    CreateMiniChallengeTool(),
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
    return [tool.to_function_schema() for tool in get_tools(agent_type)
            if tool.name not in DIRECT_WRITE_TOOLS]


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
    course_name: str | None = None,
    agent_type: str = "mentor",
    allowed_tools: frozenset[str] | None = None,
    mcp_write_authorized: bool = False,
    source_evidence: tuple[str, ...] | None = None,
) -> ToolResult:
    """
    Execute a tool by name with the given arguments.

    Injects _user_id, _course_id, _course_name, and _session_id into kwargs so
    tools can access the calling user's context without requiring them as
    explicit LLM parameters.
    """
    tool = get_tool_by_name(name)
    if not tool:
        return ToolResult(
            status="error",
            data={"error": f"Tool '{name}' not found"},
            message=f"Tool '{name}' not found in registry.",
        )

    if type(user_id) is not int or user_id <= 0:
        return deny("missing_identity", "A verified user identity is required.")
    if tool not in get_tools(agent_type):
        return deny("tool_forbidden", "This tool is not available to this agent role.")
    if allowed_tools is not None and name not in allowed_tools:
        return deny("tool_not_disclosed", "This tool was not available in the current request.")
    if not isinstance(arguments, dict) or any(
        not isinstance(key, str) or key.startswith("_") or key == "execution_plan"
        for key in arguments
    ):
        return deny("reserved_argument", "Internal execution context cannot be supplied as tool arguments.")
    properties = tool.parameters.get("properties", {})
    arguments = dict(arguments)
    if course_id is not None and "course_id" in properties:
        arguments.setdefault("course_id", course_id)
    if set(arguments) - properties.keys():
        return deny("invalid_arguments", "Tool arguments contain unsupported fields.")
    if any(key not in arguments for key in tool.parameters.get("required", [])):
        return deny("missing_arguments", "Required tool arguments are missing; do not invent their values.")
    if name in DIRECT_WRITE_TOOLS and not mcp_write_authorized:
        return deny("human_review_required", "Use the editable draft or the application's review/save controls. Chat cannot commit this change.")
    if execution_plan is not None and (
        execution_plan.is_ambiguous or getattr(execution_plan, "data_issues", [])
    ):
        return deny("unresolved_data", "Resolve decisive missing or conflicting data before running tools.")
    if source_evidence is not None and name in {
        "generate_content_draft", "generate_quiz_from_source", "parse_quiz_questions",
    }:
        for field in ("source_text", "raw_text"):
            source = arguments.get(field)
            if source and (not isinstance(source, str) or not any(source in text for text in source_evidence)):
                return deny("source_mismatch", "Use an exact excerpt of the supplied source or retrieved evidence; do not reconstruct or invent problem data.")

    supplied_course = arguments.get("course_id")
    if supplied_course is not None and (type(supplied_course) is not int or supplied_course <= 0):
        return deny("invalid_course_id", "A positive integer course_id is required.")
    if course_id is not None and supplied_course is not None and course_id != supplied_course:
        result = deny("course_scope_mismatch", "Use the verified course for the current lesson; do not search another course.")
        result.data["verified_course_id"] = course_id
        return result
    resolved_course = course_id if course_id is not None else supplied_course
    requires_course = name in COURSE_REQUIRED_TOOLS or (
        name == "generate_content_draft" and not arguments.get("source_text")
    )
    if requires_course and resolved_course is None:
        return deny("course_id_required", "Select a readable course before retrieving its data; unscoped course search is not permitted.")
    if resolved_course is not None:
        if type(resolved_course) is not int or resolved_course <= 0:
            return deny("invalid_course_id", "A positive integer course_id is required.")
        owner_required = tool in _TEACHER_ONLY_TOOLS and name not in READ_ONLY_COURSE_TOOLS
        if not await authorize_course(user_id, resolved_course, owner_required=owner_required):
            return deny("course_forbidden", "Course access could not be verified for this operation.")

    # Inject every internal field, including absent context, into the private copy.
    arguments["_user_id"] = user_id
    arguments["_course_id"] = resolved_course
    arguments["_course_name"] = course_name
    arguments["_session_id"] = session_id
    arguments["_content_id"] = content_id
    arguments["_node_id"] = node_id
    arguments["execution_plan"] = execution_plan

    try:
        return await tool.execute(**arguments)
    except Exception as exc:
        logger.warning("Tool execution failed tool=%s error_type=%s", name, type(exc).__name__)
        return deny("tool_execution_failed", "The tool could not complete. Do not claim success; verify status before retrying a change.")


def list_all_tools() -> dict[str, list[str]]:
    """List all registered tools grouped by agent type. For debugging."""
    return {
        agent_type: [t.name for t in tools]
        for agent_type, tools in _TOOL_REGISTRY.items()
    }
