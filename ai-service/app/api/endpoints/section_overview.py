"""
ai-service/app/api/endpoints/section_overview.py

POST /ai/section-overview/generate

Kick off section-level overview generation (lesson + quiz) for a section.
The LMS owns the canonical job rows; this service spawns a background task
that consolidates all indexed nodes for the section, generates a coherent
overview lesson and a comprehensive MCQ quiz, then POSTs results back to
the LMS via internal callbacks.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/section-overview", tags=["Section-Overview"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ContentInfo(BaseModel):
    """Metadata for a single indexed content item belonging to the section."""
    content_id: int
    title: str = ""
    content_type: str = ""
    description: str = ""


class GenerateSectionOverviewRequest(BaseModel):
    job_id: int
    section_id: int
    course_id: int
    question_count: int = 10
    language: str = "vi"
    contents_info: List[ContentInfo]


class GenerateResponse(BaseModel):
    job_id: int
    status: str = "processing"


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate_section_overview(
    body: GenerateSectionOverviewRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Accepts a generation job and immediately returns ``{job_id, status: "processing"}``.
    The actual generation runs in a FastAPI background task, posting progress
    and results back to the LMS via HTTP callbacks.
    """
    _verify(request)

    contents_info_dicts = [
        {
            "content_id": c.content_id,
            "title": c.title,
            "content_type": c.content_type,
            "description": c.description,
        }
        for c in body.contents_info
    ]

    async def _run():
        try:
            from app.services.section_overview_service import section_overview_service
            await section_overview_service.generate(
                job_id=body.job_id,
                section_id=body.section_id,
                course_id=body.course_id,
                question_count=body.question_count,
                language=body.language,
                contents_info=contents_info_dicts,
            )
        except Exception as exc:
            logger.error(
                "Section overview job %d failed: %s", body.job_id, exc, exc_info=True
            )
            try:
                from app.services.section_overview_service import section_overview_service
                await section_overview_service._post_status(
                    body.job_id, "failed", 0, "exception", str(exc)[:300],
                )
            except Exception as inner_exc:
                logger.error(
                    "Failed to post error status for job %d: %s",
                    body.job_id, inner_exc,
                )

    background_tasks.add_task(_run)
    return GenerateResponse(job_id=body.job_id, status="processing")


# ── Auth helper ───────────────────────────────────────────────────────────────

def _verify(request: Request) -> None:
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
