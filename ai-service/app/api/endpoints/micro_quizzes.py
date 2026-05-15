"""
ai-service/app/api/endpoints/micro_quizzes.py

POST /ai/micro-quizzes/generate        — kick off micro-quiz generation (file)
POST /ai/micro-quizzes/generate-youtube — same, but from a YouTube URL

The LMS owns the canonical job + quiz rows; this service just spawns
a background task that downloads the source, generates questions, and
POSTs the results back to the LMS via internal callback.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/micro-quizzes", tags=["Micro-Quizzes"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Schemas ──────────────────────────────────────────────────────────────────

class GenerateFromFileRequest(BaseModel):
    job_id: int
    course_id: int
    section_id: Optional[int] = None
    source_content_id: Optional[int] = None
    source_file_path: str
    source_file_type: str = ""
    language: str = "vi"


class GenerateFromYouTubeRequest(BaseModel):
    job_id: int
    course_id: int
    section_id: Optional[int] = None
    source_content_id: Optional[int] = None
    youtube_url: str
    language: str = "vi"


class GenerateResponse(BaseModel):
    job_id: int
    status: str = "queued"


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate_from_file(
    body: GenerateFromFileRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    _verify(request)

    async def _run():
        try:
            from app.services.micro_quiz_service import micro_quiz_service
            await micro_quiz_service.generate_from_file(
                job_id=body.job_id,
                course_id=body.course_id,
                section_id=body.section_id,
                source_content_id=body.source_content_id,
                source_file_path=body.source_file_path,
                source_file_type=body.source_file_type,
                language=body.language,
            )
        except Exception as exc:
            logger.error("Micro-quiz job %d failed: %s", body.job_id, exc, exc_info=True)
            from app.services.micro_quiz_service import micro_quiz_service
            await micro_quiz_service._post_status(
                body.job_id, "failed", 0, "exception", 0, str(exc)[:300],
            )

    background_tasks.add_task(_run)
    return GenerateResponse(job_id=body.job_id, status="queued")


@router.post("/generate-youtube", response_model=GenerateResponse)
async def generate_from_youtube(
    body: GenerateFromYouTubeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    _verify(request)

    async def _run():
        try:
            from app.services.micro_quiz_service import micro_quiz_service
            await micro_quiz_service.generate_from_youtube(
                job_id=body.job_id,
                course_id=body.course_id,
                section_id=body.section_id,
                source_content_id=body.source_content_id,
                youtube_url=body.youtube_url,
                language=body.language,
            )
        except Exception as exc:
            logger.error("Micro-quiz job %d (YT) failed: %s", body.job_id, exc, exc_info=True)
            from app.services.micro_quiz_service import micro_quiz_service
            await micro_quiz_service._post_status(
                body.job_id, "failed", 0, "exception", 0, str(exc)[:300],
            )

    background_tasks.add_task(_run)
    return GenerateResponse(job_id=body.job_id, status="queued")


def _verify(request: Request):
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
