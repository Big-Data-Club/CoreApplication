"""Read-only MCP/agent tool for an optional structured question assessment."""

from __future__ import annotations

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.jev_decider import decide_decomposition


class AssessQuestionTool(BaseTool):
    name = "assess_question"
    description = (
        "Get Jev's advisory probability that a learning question needs separate "
        "evidence retrieval, drafting and critique. This does not authorize actions "
        "or replace factual verification. Available through MCP when enabled."
    )
    parameters = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "minLength": 1, "maxLength": 900},
        },
        "required": ["question"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        question = kwargs.get("question")
        if not isinstance(question, str) or not question.strip() or len(question) > 900:
            return ToolResult(status="error", data={"error": "invalid_question"},
                              message="Provide a question of at most 900 characters.")
        decision = await decide_decomposition(question)
        if decision is None:
            return ToolResult(status="error", data={"error": "decision_unavailable"},
                              message="Jev decision service is not configured or available.")
        return ToolResult(
            status="success",
            data={"decomposition_score": decision["score"], "model": decision["model"],
                  "advisory_only": True},
            message="Jev assessed whether this question benefits from a decomposed workflow.",
        )
