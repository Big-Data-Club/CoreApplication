"""
ai-service/app/schemas/__init__.py
Shared Pydantic models for request/response validation.
Centralizes all data contracts between ai-service and lms-service.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ── Document Processing ───────────────────────────────────────────────────────

class ProcessDocumentIn(BaseModel):
    content_id: int
    course_id: int
    node_id: Optional[int] = None
    file_url: str
    content_type: str = "application/pdf"


class JobStatusOut(BaseModel):
    id: int
    content_id: int
    course_id: int
    status: str
    chunks_created: int = 0
    error_message: Optional[str] = None
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None


# ── Knowledge Nodes ───────────────────────────────────────────────────────────

class KnowledgeNodeOut(BaseModel):
    id: int
    course_id: int
    parent_id: Optional[int]
    name: str
    name_vi: Optional[str]
    name_en: Optional[str]
    description: Optional[str]
    level: int
    order_index: int
    chunk_count: int = 0


# ── Diagnosis ─────────────────────────────────────────────────────────────────

class DiagnoseIn(BaseModel):
    student_id: int
    attempt_id: int
    question_id: int
    wrong_answer: str
    course_id: int


class DeepLink(BaseModel):
    content_id: Optional[int]
    source_type: str               # 'document' | 'video'
    page_number: Optional[int]
    start_time_sec: Optional[int]
    end_time_sec: Optional[int]
    url_fragment: Optional[str]    # '#page=5' or '#t=120'


class DiagnoseOut(BaseModel):
    explanation: str
    gap_type: str                  # 'misconception' | 'missing_prerequisite' | ...
    knowledge_gap: str
    study_suggestion: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_chunk_id: Optional[int]
    deep_link: Optional[DeepLink]
    language: str = "vi"


class HeatmapNodeOut(BaseModel):
    node_id: int
    node_name: str
    name_vi: Optional[str]
    student_count: int
    avg_mastery: float
    total_wrong: int
    total_attempts: int
    wrong_rate: float              # 0-100 %


# ── Quiz Generation ───────────────────────────────────────────────────────────

class AnswerOptionOut(BaseModel):
    text: str
    is_correct: bool
    explanation: str


class QuizGenerationOut(BaseModel):
    id: int
    node_id: int
    node_name: Optional[str]
    course_id: int
    bloom_level: str
    question_text: str
    question_type: str
    answer_options: List[AnswerOptionOut]
    explanation: str
    source_quote: str
    source_chunk_id: Optional[int]
    language: str
    status: str                    # 'DRAFT' | 'APPROVED' | 'REJECTED' | 'PUBLISHED'
    review_note: Optional[str]
    reviewed_by: Optional[int]


class GenerateQuizIn(BaseModel):
    node_id: int
    course_id: int
    created_by: int
    bloom_levels: Optional[List[str]] = None
    language: str = "vi"
    questions_per_level: int = Field(default=1, ge=1, le=3)


class ApproveIn(BaseModel):
    reviewer_id: int
    quiz_id: int
    review_note: str = ""


class RejectIn(BaseModel):
    reviewer_id: int
    review_note: str


# ── Spaced Repetition ─────────────────────────────────────────────────────────

class RecordResponseIn(BaseModel):
    student_id: int
    question_id: int
    course_id: int
    node_id: Optional[int] = None
    quality: int = Field(..., ge=0, le=5)


class ScheduleOut(BaseModel):
    next_review_date: str          # ISO date string
    interval_days: int
    easiness_factor: float
    repetitions: int


class DueReviewOut(BaseModel):
    question_id: int
    node_id: Optional[int]
    next_review_date: date
    interval_days: int
    repetitions: int
    question_text: str
    question_type: str
    node_name: Optional[str]


class ReviewStatsOut(BaseModel):
    due_today: int = 0
    upcoming: int = 0
    total_tracked: int = 0
    avg_easiness: Optional[float]
    avg_repetitions: Optional[float]


# ── Video Generation ──────────────────────────────────────────────────────────

from app.schemas.video_schemas import (
    VideoGenerationPayload,
    VideoPlan,
    SlideContent,
    VideoScript,
)

