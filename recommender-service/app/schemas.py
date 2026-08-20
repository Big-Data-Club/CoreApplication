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
    interested_categories: list[str] = Field(default_factory=list, max_length=20)
    experience_level: str | None = Field(default=None, max_length=40)
    profile_resolved: bool = False


class RecommendationCandidate(BaseModel):
    """An eligibility-safe candidate supplied by the surface owner.

    LMS remains responsible for visibility and enrollment authorization. The
    recommender only ranks the candidates the authenticated surface can show.
    """

    entity_type: Literal["course"] = "course"
    entity_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str | None = None
    level: str | None = None
    href: str | None = None
    enrolled: bool = False
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    enrollment_count: int = Field(default=0, ge=0)
    published_at: datetime | None = None
    updated_at: datetime | None = None
    last_activity_at: datetime | None = None
    new_content_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationContext(BaseModel):
    turn_id: str | None = None
    intent: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class RecommendationRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"rr_{uuid4().hex}")
    user_id: int = Field(gt=0)
    surface: Literal["chat", "lesson_sidebar", "dashboard", "course_discovery"] = "chat"
    candidate_types: list[str] = Field(default_factory=lambda: ["next_action"])
    limit: int = Field(default=3, ge=1, le=50)
    context: RecommendationContext = Field(default_factory=RecommendationContext)
    conversation: ConversationContext = Field(default_factory=ConversationContext)
    candidates: list[RecommendationCandidate] = Field(default_factory=list, max_length=500)


class ReasonFact(BaseModel):
    code: str
    value: Any | None = None
    node_id: int | None = None


class RecommendationBadge(BaseModel):
    type: Literal["new_content", "goal_match", "continue_learning", "almost_done", "popular", "new_course"]
    text: str
    value: Any | None = None


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
    badges: list[RecommendationBadge] = Field(default_factory=list)
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
    rank: int | None = Field(default=None, ge=1, le=50)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_time", mode="before")
    @classmethod
    def normalize_event_time(cls, value: Any) -> Any:
        if isinstance(value, str) and value.endswith("Z"):
            return value[:-1] + "+00:00"
        return value


# ══════════════════════════════════════════════════════════════════════════════
# SKILL-BASED RECOMMENDATION SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════


class NextBestLessonRequest(BaseModel):
    """Request for skill-based next best lesson recommendation."""
    student_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    time_budget_minutes: int = Field(default=20, ge=5, le=120)


class SkillRecommendationItem(BaseModel):
    """Individual skill-based recommendation."""
    content_id: int
    skill_id: int
    skill_name: str
    difficulty: float = Field(ge=0, le=1)
    reason: str
    score: float = Field(ge=0, le=1)
    action: Literal["review", "practice", "advance", "learn_new"]
    estimated_minutes: int = Field(default=20)


class NextBestLessonResponse(BaseModel):
    """Response with skill-based recommendations."""
    student_id: int
    course_id: int
    recommendations: list[SkillRecommendationItem] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    policy_version: str = "skill-based-v1"
