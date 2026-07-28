from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class RecommendationContext(BaseModel):
    role: str = "student"
    course_id: int | None = None
    lesson_id: int | None = None
    content_id: int | None = None
    locale: str = "vi-VN"
    session_id: str | None = None
    time_budget_minutes: int | None = Field(default=None, ge=5, le=240)
    goal: str | None = Field(default=None, max_length=80)


class ConversationContext(BaseModel):
    turn_id: str | None = None
    intent: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class RecommendationRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"rr_{uuid4().hex}")
    user_id: int = Field(gt=0)
    surface: Literal["chat", "lesson_sidebar", "dashboard", "course_discovery"] = "chat"
    candidate_types: list[str] = Field(default_factory=lambda: ["next_action"])
    limit: int = Field(default=3, ge=1, le=5)
    context: RecommendationContext = Field(default_factory=RecommendationContext)
    conversation: ConversationContext = Field(default_factory=ConversationContext)


class ReasonFact(BaseModel):
    code: str
    value: Any | None = None
    node_id: int | None = None


class RecommendationItem(BaseModel):
    recommendation_id: str
    entity: dict[str, Any]
    action: str
    title: str
    description: str
    href: str | None = None
    rank: int
    score: float = Field(ge=0, le=1)
    estimated_minutes: int | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
    why_facts: list[ReasonFact] = Field(default_factory=list)
    expected_outcome: str
    tracking_token: str


class RecommendationResponse(BaseModel):
    request_id: str
    recommendation_set_id: str
    policy_version: str = "heuristic-v1"
    model_version: str = "rules-2026-07"
    fallback: bool = False
    clarification_needed: bool = False
    clarification_message: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    items: list[RecommendationItem] = Field(default_factory=list)


class RecommendationInteraction(BaseModel):
    event_id: str = Field(default_factory=lambda: f"re_{uuid4().hex}")
    event_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: Literal["impression", "click", "accept", "reject", "dismiss", "started", "completed"]
    user_id: int = Field(gt=0)
    recommendation_id: str
    recommendation_set_id: str | None = None
    tracking_token: str
    surface: str = "chat"
    course_id: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    rank: int | None = Field(default=None, ge=1, le=20)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_time", mode="before")
    @classmethod
    def normalize_event_time(cls, value: Any) -> Any:
        if isinstance(value, str) and value.endswith("Z"):
            return value[:-1] + "+00:00"
        return value
