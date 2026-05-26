"""
ai-service/app/api/endpoints/quiz_gen.py
Phase 2 endpoints:
POST /ai/quiz/generate   — generate Bloom's Taxonomy quiz for a node
GET  /ai/quiz/drafts/{course_id}   — list DRAFT questions for review
POST /ai/quiz/{gen_id}/approve     — approve + publish to quiz
POST /ai/quiz/{gen_id}/reject
POST /ai/spaced-repetition/record  — record review response (SM-2)
GET  /ai/spaced-repetition/due     — get due reviews for student
GET  /ai/spaced-repetition/stats   — review stats
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.quiz_service import quiz_gen_service, sr_service, BLOOM_LEVELS

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/quiz", tags=["Phase 2 — Quiz Generation"])
sr_router = APIRouter(prefix="/spaced-repetition", tags=["Phase 2 — Spaced Repetition"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class GenerateQuizRequest(BaseModel):
    node_id: int
    course_id: int
    created_by: int
    bloom_levels: Optional[list[str]] = None   # default: all 6 levels
    language: str = "vi"
    questions_per_level: int = Field(default=1, ge=1, le=3)


class ApproveRequest(BaseModel):
    reviewer_id: int
    quiz_id: int
    review_note: str = ""


class RejectRequest(BaseModel):
    reviewer_id: int
    review_note: str


class RecordResponseRequest(BaseModel):
    student_id: int
    question_id: int
    course_id: int
    node_id: Optional[int] = None
    quality: int = Field(..., ge=0, le=5, description="SM-2 quality rating 0–5")


# ── Quiz Generation Endpoints ─────────────────────────────────────────────────

@router.post("/generate")
async def generate_quiz(body: GenerateQuizRequest, request: Request):
    """
    Phase 2: Auto Quiz Generator using Bloom's Taxonomy.
    Generates DRAFT questions — require instructor review before publishing.
    """
    _verify_internal(request)

    # Validate bloom levels
    if body.bloom_levels:
        invalid = [l for l in body.bloom_levels if l not in BLOOM_LEVELS]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid bloom levels: {invalid}. Valid: {BLOOM_LEVELS}",
            )

    try:
        gen_ids = await quiz_gen_service.generate_for_node(
            node_id=body.node_id,
            course_id=body.course_id,
            created_by=body.created_by,
            bloom_levels=body.bloom_levels,
            language=body.language,
            questions_per_level=body.questions_per_level,
        )
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "generated": len(gen_ids),
        "gen_ids": gen_ids,
        "status": "DRAFT",
        "message": f"Generated {len(gen_ids)} questions. Awaiting instructor review.",
    }


@router.get("/drafts/{course_id}")
async def list_drafts(
    course_id: int,
    request: Request,
    node_id: Optional[int] = None,
):
    """List AI-generated DRAFT questions for instructor review."""
    _verify_internal(request)
    return await quiz_gen_service.list_drafts(course_id=course_id, node_id=node_id)


@router.post("/{gen_id}/approve")
async def approve_question(gen_id: int, body: ApproveRequest, request: Request):
    """
    Instructor approves a DRAFT question → publishes to actual quiz.
    The question becomes visible to students.
    """
    _verify_internal(request)
    try:
        q_data = await quiz_gen_service.approve_question(
            gen_id=gen_id,
            reviewer_id=body.reviewer_id,
            quiz_id=body.quiz_id,
            review_note=body.review_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Approve failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return q_data


class UpdateQuestionIdRequest(BaseModel):
    quiz_question_id: int

@router.post("/{gen_id}/publish")
async def publish_question(gen_id: int, body: UpdateQuestionIdRequest, request: Request):
    """Callback for LMS to confirm successful insertion."""
    _verify_internal(request)
    await quiz_gen_service.update_quiz_question_id(gen_id, body.quiz_question_id)
    return {"status": "PUBLISHED"}


@router.post("/{gen_id}/reject")
async def reject_question(gen_id: int, body: RejectRequest, request: Request):
    """Instructor rejects a DRAFT question."""
    _verify_internal(request)
    await quiz_gen_service.reject_question(
        gen_id=gen_id,
        reviewer_id=body.reviewer_id,
        review_note=body.review_note,
    )
    return {"status": "REJECTED"}


# ── Spaced Repetition Endpoints ────────────────────────────────────────────────

@sr_router.post("/record")
async def record_review_response(body: RecordResponseRequest, request: Request):
    """
    Record student's review response and update SM-2 schedule.
    Call this after student answers a spaced repetition question.
    """
    _verify_internal(request)
    result = await sr_service.record_response(
        student_id=body.student_id,
        question_id=body.question_id,
        course_id=body.course_id,
        node_id=body.node_id,
        quality=body.quality,
    )
    return result


@sr_router.get("/due/student/{student_id}/course/{course_id}")
async def get_due_reviews(
    student_id: int,
    course_id: int,
    request: Request,
    limit: int = 20,
):
    """
    Get questions due for review today.
    Used by the 5-minute warm-up session on login.
    """
    _verify_internal(request)
    return await sr_service.get_due_reviews(
        student_id=student_id,
        course_id=course_id,
        limit=limit,
    )


@sr_router.get("/stats/student/{student_id}/course/{course_id}")
async def get_review_stats(student_id: int, course_id: int, request: Request):
    """Review progress stats for student dashboard."""
    _verify_internal(request)
    return await sr_service.get_review_stats(student_id, course_id)


@sr_router.get("/stats/student/{student_id}/due-today")
async def get_total_due_reviews(student_id: int, request: Request):
    """Get total reviews due today across all courses for student."""
    _verify_internal(request)
    count = await sr_service.get_total_due_reviews(student_id)
    return {"due_today": count}



def _verify_internal(request: Request):
    secret = request.headers.get("X-AI-Secret", "")
    if secret != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
