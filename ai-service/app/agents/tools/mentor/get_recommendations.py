"""Mentor tool backed by the online recommendation service.

The tool deliberately returns structured recommendation facts and a UI widget;
the LLM may explain them but must not manufacture an item or a reason.
"""
from __future__ import annotations

import logging

import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GetRecommendationsTool(BaseTool):
    name = "get_recommendations"
    description = (
        "Retrieve safe, personalized next learning actions from the recommendation "
        "service. Use for what-to-study-next, learning roadmap suggestions, "
        "preference feedback, and why a learning action is recommended. The returned "
        "widget asks for human confirmation before opening an action."
    )
    parameters = {
        "type": "object",
        "properties": {
            "time_budget_minutes": {
                "type": ["integer", "null"],
                "description": "Available study time, only if the student stated it (5-240 minutes).",
            },
            "prefer_format": {
                "type": ["string", "null"],
                "enum": ["practice", "theory", "mixed", None],
                "description": "Student's explicit preferred format, if known.",
            },
        },
        "required": [],
    }

    async def execute(self, **kwargs) -> ToolResult:
        user_id = int(kwargs.get("_user_id") or 0)
        course_id = kwargs.get("_course_id") or kwargs.get("course_id")
        if not user_id:
            return ToolResult(status="error", data={}, message="Không xác định được người dùng để tạo gợi ý.")

        settings = get_settings()
        payload = {
            "user_id": user_id,
            "surface": "chat",
            "candidate_types": ["next_action", "roadmap_step"],
            "limit": 3,
            "context": {
                "role": "student",
                "course_id": course_id,
                "time_budget_minutes": kwargs.get("time_budget_minutes"),
            },
            "conversation": {
                "intent": "request_recommendation",
                "constraints": {
                    **({"prefer_format": kwargs["prefer_format"]} if kwargs.get("prefer_format") else {}),
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.post(
                    f"{settings.recommender_service_url}/v1/recommendations",
                    json=payload,
                    headers={"X-AI-Secret": settings.ai_service_secret},
                )
                response.raise_for_status()
                recommendation_set = response.json()
        except Exception as exc:
            logger.warning("recommender service unavailable: %s", exc)
            return ToolResult(
                status="error",
                data={"error": "recommender_unavailable"},
                message="Chưa thể tải gợi ý cá nhân hóa. Bạn có thể thử lại trong ít phút.",
            )

        if recommendation_set.get("clarification_needed"):
            return ToolResult(
                status="success",
                data=recommendation_set,
                message=recommendation_set.get("clarification_message") or "Cần thêm ngữ cảnh khóa học.",
            )

        items = recommendation_set.get("items") or []
        return ToolResult(
            status="success",
            data=recommendation_set,
            message=f"Đã tìm thấy {len(items)} hành động học tập phù hợp.",
            ui_instruction={
                "component": "RecommendationWidget",
                "props": {"recommendation_set": recommendation_set},
            },
        )
