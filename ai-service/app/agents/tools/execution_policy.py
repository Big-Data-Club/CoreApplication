"""Server-owned tool policy; model arguments and planner hints never grant access."""
from __future__ import annotations

from app.agents.tools.base_tool import ToolResult


# These tools commit changes rather than returning an editable approval preview.
# MCP has a separate authenticated write scope. Chat must use draft/UI workflows.
DIRECT_WRITE_TOOLS = frozenset({
    "create_course_section", "trigger_auto_index", "save_to_notebook",
    "mcp_index_files", "mcp_create_course_from_files", "mcp_apply_course_blueprint",
    "mcp_create_lesson", "mcp_batch_generate_quiz", "mcp_save_course_knowledge",
})
COURSE_REQUIRED_TOOLS = frozenset({
    "list_knowledge_nodes", "search_course_materials", "explain_concept",
    "generate_quiz_draft", "analyze_student_performance", "recommend_review",
    "diagnose_knowledge_gap", "prepare_course_materials", "create_course_section",
    "trigger_auto_index", "mcp_index_files", "mcp_batch_generate_quiz",
    "mcp_create_lesson", "mcp_save_course_knowledge", "mcp_course_knowledge_read",
})
READ_ONLY_COURSE_TOOLS = frozenset({
    "list_knowledge_nodes", "search_course_materials", "explain_concept", "mcp_course_knowledge_read",
})


def deny(code: str, message: str) -> ToolResult:
    return ToolResult(status="error", data={"error": code}, message=message)


async def authorize_course(user_id: int, course_id: int, *, owner_required: bool) -> bool:
    """Recheck at execution time through LMS; UI/cache/planner IDs are hints."""
    from mcp.course_access import user_can_read_course, user_owns_course
    try:
        check = user_owns_course if owner_required else user_can_read_course
        return await check(user_id, course_id)
    except Exception:
        return False
