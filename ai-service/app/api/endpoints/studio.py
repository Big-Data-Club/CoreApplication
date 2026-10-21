"""
ai-service/app/api/endpoints/studio.py

Content Studio endpoints (teacher authoring: slides / document / video-P1).
Auth = X-AI-Secret (frontend goes through the Next.js proxy which injects
the secret and the session user id, mirroring the notebook proxy pattern).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, PositiveInt

from app.services.studio.studio_service import studio_service
from app.services.learning_context import lms_sources

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


@router.get("/media/{asset_id}")
async def download_media(asset_id: str, user_id: int = Query(..., gt=0),
                         x_ai_secret: Optional[str] = Header(None), range: Optional[str] = Header(None), download: bool = False):
    _verify(x_ai_secret)
    from app.services.studio.temporary_media import media_response, owned_asset
    from mcp.course_access import user_can_read_course
    try:
        asset = await owned_asset(asset_id, user_id)
    except LookupError:
        raise HTTPException(404, "Media not found")
    except ValueError as exc:
        raise HTTPException(410, str(exc))
    if not await user_can_read_course(user_id, asset["course_id"]):
        raise HTTPException(403, "Course access revoked")
    return await media_response(asset_id, owner_id=user_id, range_header=range, attachment=download)


class CreateProjectRequest(BaseModel):
    course_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0)
    kind: str = "slides"
    title: str = Field(default="Bài giảng chưa đặt tên", max_length=300)
    settings: dict = Field(default_factory=dict)


class ContextSourceRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    type: str  # curriculum | text; node/document_url retained for older clients
    title: str = Field(default="", max_length=1000)
    ref: Optional[int] = None
    text: str = Field(default="", max_length=2_000_000)
    section_ids: list[PositiveInt] = Field(default_factory=list, max_length=100)
    content_ids: list[PositiveInt] = Field(default_factory=list, max_length=100)


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


class PublishProjectRequest(SimpleActionRequest):
    confirmed: bool = False
    section_id: int = Field(gt=0)
    upload_id: Optional[str] = None


class UploadProjectRequest(SimpleActionRequest):
    confirmed: bool = False
    asset_id: str
    channel_id: str
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    privacy: str
    made_for_kids: bool
    contains_synthetic_media: bool


async def _project(project_id: str, user_id: int):
    project = await studio_service.get_project(project_id, user_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from mcp.course_access import user_can_read_course
    if not await user_can_read_course(user_id, project["course_id"]):
        raise HTTPException(403, "Course access revoked")
    return project


@router.get("/projects/{project_id}/youtube")
async def youtube_status(project_id: str, user_id: int = Query(gt=0), x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    project = await _project(project_id, user_id)
    from app.services.studio.youtube_publishing import bridge
    from app.core.database import get_ai_conn
    try:
        status = await bridge("status")
    except ValueError as exc:
        raise HTTPException(503, str(exc))
    async with get_ai_conn() as conn:
        uploads = await conn.fetch("""SELECT u.id,u.status,u.title,u.privacy,u.actual_privacy,u.processing_status,u.video_id,u.error
            FROM studio_youtube_uploads u JOIN studio_temporary_media m ON m.id=u.asset_id
            WHERE m.project_id=$1::uuid AND u.owner_id=$2 AND m.generation=$3
            ORDER BY u.created_at DESC LIMIT 10""", project_id, user_id, str(project.get("current_job_id") or "draft"))
    return {**status, "uploads": [dict(row) for row in uploads]}


@router.post("/projects/{project_id}/youtube", status_code=202)
async def youtube_upload(project_id: str, body: UploadProjectRequest, x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    project = await _project(project_id, body.user_id)
    if not body.confirmed:
        raise HTTPException(422, "Upload confirmation required")
    from app.services.studio.temporary_media import owned_asset
    from app.services.studio.youtube_publishing import request_upload
    try:
        asset = await owned_asset(body.asset_id, body.user_id)
        if str(asset["project_id"]) != project["id"]:
            raise LookupError("Asset not in project")
        return await request_upload(body.user_id, body.asset_id, body.channel_id, body.title, body.description,
                                    body.privacy, body.made_for_kids, body.contains_synthetic_media)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except (ValueError, LookupError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/projects/{project_id}/uploads/{upload_id}")
async def upload_status(project_id: str, upload_id: str, user_id: int = Query(gt=0), x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    project = await _project(project_id, user_id)
    from app.services.studio.youtube_publishing import get_upload
    from app.core.database import get_ai_conn
    from uuid import UUID
    try:
        async with get_ai_conn() as conn:
            linked = await conn.fetchval("""SELECT m.project_id FROM studio_youtube_uploads u
                JOIN studio_temporary_media m ON m.id=u.asset_id WHERE u.id=$1 AND u.owner_id=$2""", UUID(upload_id), user_id)
        if str(linked) != project["id"]:
            raise LookupError("Upload not in project")
        return await get_upload(upload_id, user_id, refresh=True)
    except (ValueError, LookupError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/projects/{project_id}/publish")
async def publish(project_id: str, body: PublishProjectRequest, x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    project = await _project(project_id, body.user_id)
    if not body.confirmed:
        raise HTTPException(422, "Publish confirmation required")
    from mcp.authoring import publish_project
    try:
        return await publish_project(project, body.user_id, body.model_dump())
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except (ValueError, LookupError) as exc:
        raise HTTPException(422, str(exc))


# Worker/admin bridge only. The browser Studio proxy explicitly rejects this path.
@router.get("/youtube/connection")
async def get_shared_connection(x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    from app.core.database import get_ai_conn
    from app.core.llm_gateway.crypto import decrypt
    import json
    async with get_ai_conn() as conn:
        encrypted = await conn.fetchval("SELECT encrypted_connection FROM studio_shared_youtube_connection WHERE singleton=true")
    from fastapi.responses import JSONResponse
    return JSONResponse(json.loads(decrypt(encrypted)) if encrypted else None, headers={"Cache-Control": "no-store"})


@router.put("/youtube/connection")
async def save_shared_connection(body: dict, x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    from app.core.database import get_ai_conn
    from app.core.llm_gateway.crypto import encrypt
    import json
    if not isinstance(body.get("tokens"), dict) or not body.get("channel_id") or len(json.dumps(body)) > 20000:
        raise HTTPException(422, "Invalid shared channel connection")
    async with get_ai_conn() as conn:
        await conn.execute("""INSERT INTO studio_shared_youtube_connection(singleton,encrypted_connection) VALUES(true,$1)
            ON CONFLICT(singleton) DO UPDATE SET encrypted_connection=$1,updated_at=now()""", encrypt(json.dumps(body)))
    return {"saved": True}


@router.delete("/youtube/connection")
async def delete_shared_connection(x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    from app.core.database import get_ai_conn
    async with get_ai_conn() as conn, conn.transaction():
        await conn.execute("DELETE FROM studio_shared_youtube_connection WHERE singleton=true")
        await conn.execute("""UPDATE studio_youtube_uploads SET status='failed',lease_until=NULL,
            error='Admin đã ngắt kết nối kênh chung.',updated_at=now() WHERE status IN ('queued','running')""")
    return {"deleted": True}


@router.post("/projects")
async def create_project(body: CreateProjectRequest,
                         x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    try:
        await lms_sources(body.course_id, body.user_id, check_only=True)
        return await studio_service.create_project(
            course_id=body.course_id, created_by=body.user_id,
            kind=body.kind, title=body.title, settings_obj=body.settings,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user_id: int = Query(..., gt=0),
                      x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    return await _project(project_id, await _uid(user_id))


@router.post("/projects/{project_id}/context")
async def add_context(project_id: str, body: ContextSourceRequest,
                      x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    await _project(project_id, body.user_id)
    try:
        return await studio_service.add_context_source(
            project_id, await _uid(body.user_id), body.model_dump()
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/projects/{project_id}/plan")
async def generate_plan(project_id: str, body: PlanActionRequest,
                        x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    await _project(project_id, body.user_id)
    try:
        from app.services.studio.jobs import enqueue
        result = await enqueue(project_id, await _uid(body.user_id), "plan", {"target_sections": body.target_sections})
        return {**result, "project": await studio_service.get_project(project_id, body.user_id), "warnings": []}
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/projects/{project_id}/plan")
async def update_plan(project_id: str, body: UpdatePlanRequest,
                      x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    await _project(project_id, body.user_id)
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
    await _project(project_id, body.user_id)
    try:
        project = await studio_service.update_section(
            project_id, await _uid(body.user_id), body.index, body.patch
        )
        return {"project": project}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/projects/{project_id}/generate")
async def generate(project_id: str, body: SimpleActionRequest,
                   x_ai_secret: Optional[str] = Header(None)):
    _verify(x_ai_secret)
    await _project(project_id, body.user_id)
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
    await _project(project_id, body.user_id)
    try:
        return await studio_service.regenerate_section_preview(
            project_id, await _uid(body.user_id), index
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
