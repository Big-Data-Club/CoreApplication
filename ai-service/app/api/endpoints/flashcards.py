"""
ai-service/app/api/endpoints/flashcards.py
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.llm import chat_complete_json, build_flashcard_generation_prompt
from app.core.llm_gateway import TASK_FLASHCARD_GEN
from app.services.rag_service import rag_service
from app.services.flashcard_service import flashcard_srv

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/flashcards", tags=["Flashcards"])


def _verify_internal(request: Request):
    secret = request.headers.get("X-AI-Secret", "")
    if secret != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")


class GenerateFlashcardsRequest(BaseModel):
    student_id: int
    course_id: int
    node_id: Optional[int] = None
    lesson_id: Optional[int] = None
    content_id: Optional[int] = None
    text_chunk: Optional[str] = None
    count: int = Field(default=3, ge=1, le=10)
    language: str = "vi"
    existing_fronts: Optional[list[str]] = None


class BulkSaveFlashcardsRequest(BaseModel):
    student_id: int
    course_id: int
    node_id: Optional[int] = None
    lesson_id: Optional[int] = None
    content_id: Optional[int] = None
    flashcards: list[dict] = Field(..., description="List of dicts with 'front_text' and 'back_text'")


class ReviewRequest(BaseModel):
    student_id: int
    flashcard_id: int
    quality: int = Field(..., ge=0, le=5)


@router.get("/due/student/{student_id}/course/{course_id}")
async def get_due_flashcards(student_id: int, course_id: int, request: Request):
    _verify_internal(request)
    try:
        return await flashcard_srv.list_due_flashcards(student_id, course_id)
    except Exception as e:
        logger.error(f"Failed to get due flashcards: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_flashcards(
    student_id: int, 
    course_id: int, 
    request: Request,
    node_id: Optional[int] = None, 
    lesson_id: Optional[int] = None,
    content_id: Optional[int] = None
):
    _verify_internal(request)
    try:
        flashcards = await flashcard_srv.list_flashcards_by_target(
            student_id=student_id, 
            course_id=course_id, 
            node_id=node_id, 
            lesson_id=lesson_id,
            content_id=content_id
        )
        return {"flashcards": flashcards}
    except Exception as e:
        logger.error(f"Failed to list flashcards: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review")
async def review_flashcard(body: ReviewRequest, request: Request):
    _verify_internal(request)
    try:
        return await flashcard_srv.review_flashcard(body.student_id, body.flashcard_id, body.quality)
    except Exception as e:
        logger.error(f"Failed to review flashcard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_flashcards(body: GenerateFlashcardsRequest, request: Request):
    _verify_internal(request)

    if body.node_id is None and body.lesson_id is None and body.content_id is None:
        raise HTTPException(status_code=400, detail="Must provide node_id, lesson_id, or content_id")

    try:
        persisted_flashcards = await flashcard_srv.generate_flashcards_with_llm(
            student_id=body.student_id,
            course_id=body.course_id,
            node_id=body.node_id,
            lesson_id=body.lesson_id,
            content_id=body.content_id,
            text_chunk=body.text_chunk,
            count=body.count,
            language=body.language,
            existing_fronts=body.existing_fronts,
        )
        return {"flashcards": persisted_flashcards}
    except Exception as e:
        logger.error(f"Failed to generate flashcards: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-save")
async def bulk_save_flashcards(body: BulkSaveFlashcardsRequest, request: Request):
    _verify_internal(request)

    if body.node_id is None and body.lesson_id is None and body.content_id is None:
        raise HTTPException(status_code=400, detail="Must provide node_id, lesson_id, or content_id")

    try:
        persisted = await flashcard_srv.create_flashcards(
            flashcards_data=body.flashcards,
            student_id=body.student_id,
            course_id=body.course_id,
            node_id=body.node_id,
            lesson_id=body.lesson_id,
            content_id=body.content_id,
        )
        return {"flashcards": persisted}
    except Exception as e:
        logger.error(f"Failed to bulk save flashcards: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
