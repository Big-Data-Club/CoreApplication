"""Persist a reviewable course blueprint authored by the caller's model."""
from __future__ import annotations

import json
from uuid import uuid4

from app.agents.tools.base_tool import BaseTool, ToolResult


class McpCreateCourseFromFilesTool(BaseTool):
    name = "mcp_create_course_from_files"
    description = (
        "Save a reviewable DRAFT course blueprint authored by your external AI model. "
        "No raw storage paths are accepted and no BDC LLM is called. The teacher must "
        "review and approve the draft in LMS before a course can be created."
    )
    parameters = {
        "type": "object",
        "properties": {
            "plan": {
                "type": "object",
                "description": "Externally authored course plan with title, description and chapters.",
                "properties": {
                    "title": {"type": "string", "maxLength": 200},
                    "description": {"type": "string", "maxLength": 4000},
                    "language": {"type": "string", "enum": ["vi", "en"]},
                    "chapters": {"type": "array", "minItems": 1, "maxItems": 50},
                },
                "required": ["title", "chapters"],
            },
            "source_names": {
                "type": "array", "maxItems": 50,
                "items": {"type": "string", "maxLength": 255},
                "description": "Display names only; never pass bucket paths, tokens, or object keys.",
            },
            "allowed_organization_ids": {"type": "array", "maxItems": 20, "items": {"type": "integer"}},
        },
        "required": ["plan"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        owner_id = int(kwargs.get("_user_id") or 0)
        plan = kwargs.get("plan")
        if not owner_id or not isinstance(plan, dict):
            return ToolResult(status="error", data={"error": "invalid_blueprint"}, message="A valid plan is required.")
        title = str(plan.get("title") or "").strip()[:200]
        chapters = plan.get("chapters") or []
        if not title or not isinstance(chapters, list) or not 1 <= len(chapters) <= 50:
            return ToolResult(status="error", data={"error": "invalid_blueprint"}, message="Plan requires a title and 1–50 chapters.")
        encoded = json.dumps(plan, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 200_000:
            return ToolResult(status="error", data={"error": "blueprint_too_large"}, message="The course blueprint is too large.")

        source_names = [str(v).split("/")[-1][:255] for v in (kwargs.get("source_names") or [])][:50]
        org_ids = sorted({int(v) for v in (kwargs.get("allowed_organization_ids") or []) if int(v) > 0})[:20]
        blueprint_id = uuid4()
        from app.core.database import get_ai_conn
        try:
            async with get_ai_conn() as conn:
                await conn.execute(
                    """INSERT INTO course_blueprints
                       (id, owner_id, origin, status, source_manifest, governance_manifest, plan, validation_report)
                       VALUES ($1, $2, 'chatbot', 'DRAFT', $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb)""",
                    blueprint_id, owner_id,
                    json.dumps({"display_names": source_names}),
                    json.dumps({"allowed_organization_ids": org_ids}),
                    encoded,
                    json.dumps({"valid": True, "state": "DRAFT", "author": "external_mcp_client"}),
                )
        except Exception:
            return ToolResult(status="error", data={"error": "blueprint_save_failed"}, message="The blueprint could not be saved.")

        return ToolResult(
            status="success",
            data={"blueprint_id": str(blueprint_id), "title": title, "status": "DRAFT", "requires_human_approval": True},
            message="Saved the externally authored blueprint as a draft. Review it in LMS before approval.",
        )
