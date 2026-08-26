"""
ai-service/app/api/endpoints/studio.py

Content Studio endpoints (teacher authoring: slides / document / video-P1).
Auth = X-AI-Secret (frontend goes through the Next.js proxy which injects
the secret and the session user id, mirroring the notebook proxy pattern).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.studio.studio_service import studio_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/studio", tags=["Content Studio"])


def _verify(x_ai_secret: Optional[str]) -> None:
    from app.core.config import get_settings
    if not x_ai_secret or x_ai_secret != get_settings().ai_service_secret:
        raise HTTPException(status_code=401, detail="Invalid AI service secret")


async def _uid(user_id: int) -> int:
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id required")
    return user_id


class CreateProjectRequest(BaseModel):
    course_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0)
    kind: str = "slides"
    title: str = Field(default="Bài giảng chưa đặt tên", max_length=300)
    settings: dict = Field(default_factory=dict)


class ContextSourceRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    type: str  # node | text | document_url
    title: str = ""
    ref: Optional[int] = None
    text: str = ""


class PlanActionRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    target_sections: Optional[int] = Field(default=None, ge=2, le=30)


class UpdatePlanRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    plan: dict


class UpdateSectionRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    index: int = Field(..., ge=0, le=60)
    patch: dict


class SimpleActionRequest(BaseModel):
    user_id: int = Field(..., gt=0)


@router.post("/projects")
async def create_project(body: CreateProjectRequest,
                         x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        return await studio_service.create_project(
            course_id=body.course_id, created_by=body.user_id,
            kind=body.kind, title=body.title, settings_obj=body.settings,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user_id: int,
                      x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    project = await studio_service.get_project(project_id, await _uid(user_id))
    if not project:
        raise HTTPException(404, "not found")
    return project


@router.post("/projects/{project_id}/context")
async def add_context(project_id: str, body: ContextSourceRequest,
                      x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        return await studio_service.add_context_source(
            project_id, await _uid(body.user_id), body.model_dump()
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/projects/{project_id}/plan")
async def generate_plan(project_id: str, body: PlanActionRequest,
                        x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        return await studio_service.generate_plan(
            project_id, await _uid(body.user_id), body.target_sections
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/projects/{project_id}/plan")
async def update_plan(project_id: str, body: UpdatePlanRequest,
                      x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        return await studio_service.update_plan(
            project_id, await _uid(body.user_id), body.plan
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/projects/{project_id}/sections")
async def update_section(project_id: str, body: UpdateSectionRequest,
                         x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        return await studio_service.update_section(
            project_id, await _uid(body.user_id), body.index, body.patch
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/projects/{project_id}/generate")
async def generate(project_id: str, body: SimpleActionRequest,
                   x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        return await studio_service.start_generate(
            project_id, await _uid(body.user_id)
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/projects/{project_id}/sections/{index}/render-preview")
async def render_section_preview(project_id: str, index: int,
                                 body: SimpleActionRequest,
                                 x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        return await studio_service.regenerate_section_preview(
            project_id, await _uid(body.user_id), index
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
