"""Internal API for the review-first course creation workflow.

Both the teacher create-course screen and chatbot call the same endpoints.
The caller uploads files through LMS first, extracts normalised text, then
sends that text + opaque file paths here.  That keeps chat and UI behaviour
identical while avoiding duplicate file pipelines.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.services.course_blueprint_service import (
    CourseGovernance, CoursePlan, SourceDocument, course_blueprint_service, validate_plan,
)

router = APIRouter(prefix="/course-blueprints", tags=["Course blueprints"])
settings = get_settings()
logger = logging.getLogger(__name__)
# One blueprint run can perform OCR plus many map/reduce completions.  The
# deployed AI pod is deliberately small; queue runs instead of allowing a
# burst of teachers to starve every request and exhaust the key pool.
_generation_slots = asyncio.Semaphore(1)


class CreateDraftRequest(BaseModel):
    owner_id: int
    origin: str = Field(default="course_create", pattern="^(course_create|chatbot)$")
    language: str = Field(default="vi", max_length=10)
    documents: list[SourceDocument] = Field(min_length=1, max_length=100)
    # LMS supplies these only after checking membership/permissions. AI keeps
    # them as a validation allow-list; it never discovers organizations itself.
    allowed_organization_ids: list[int] = Field(min_length=1, max_length=100)
    allowed_co_teacher_ids: list[int] = Field(default_factory=list, max_length=1000)
    governance: CourseGovernance = Field(default_factory=CourseGovernance)


class UpdateDraftRequest(BaseModel):
    owner_id: int
    version: int = Field(ge=1)
    plan: CoursePlan


class StatusRequest(BaseModel):
    owner_id: int


def _verify(request: Request) -> None:
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized internal call")


async def _row_or_404(blueprint_id: UUID):
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("SELECT * FROM course_blueprints WHERE id=$1", blueprint_id)
    if not row:
        raise HTTPException(404, "Blueprint not found")
    return row


def _dto(row) -> dict:
    def decoded(value):
        return json.loads(value) if isinstance(value, str) else value
    return {
        "id": str(row["id"]), "owner_id": row["owner_id"], "origin": row["origin"],
        "status": row["status"], "documents": decoded(row["source_manifest"]), "plan": decoded(row["plan"]),
        "governance_options": decoded(row["governance_manifest"]),
        "validation": decoded(row["validation_report"]), "version": row["version"],
        "applied_course_id": row["applied_course_id"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], "error_message": row.get("error_message") if hasattr(row, "get") else row["error_message"],
    }


async def _generate_draft_in_background(blueprint_id: UUID, body: CreateDraftRequest) -> None:
    """Build a draft independently of the browser/proxy connection."""
    async with _generation_slots:
        try:
            plan, report = await course_blueprint_service.draft(body.documents, body.language)
            plan.governance = body.governance
            if plan.governance.organization_id is None and len(body.allowed_organization_ids) == 1:
                plan.governance.organization_id = body.allowed_organization_ids[0]
            report = validate_plan(
                plan, {doc.id for doc in body.documents}, set(body.allowed_organization_ids),
                set(body.allowed_co_teacher_ids),
            )
            if not report["valid"] and any(error["code"] != "organization_required" for error in report["errors"]):
                raise ValueError("Generated blueprint violates curriculum invariants")
            async with get_ai_conn() as conn:
                # Do not resurrect a draft that the teacher cancelled while
                # the model was working.
                await conn.execute(
                    """UPDATE course_blueprints
                       SET status='DRAFT', plan=$1::jsonb, validation_report=$2::jsonb,
                           error_message=NULL
                       WHERE id=$3 AND status='PROCESSING'""",
                    plan.model_dump_json(), json.dumps(report), blueprint_id,
                )
        except Exception:
            logger.exception("Course blueprint generation failed id=%s", blueprint_id)
            async with get_ai_conn() as conn:
                await conn.execute(
                    """UPDATE course_blueprints
                       SET status='FAILED', validation_report=$1::jsonb, error_message=$2
                       WHERE id=$3 AND status='PROCESSING'""",
                    json.dumps({"valid": False, "errors": [{"code": "generation_failed", "message": "Không thể tạo đề xuất AI."}]}),
                    "AI không thể hoàn tất phân tích tài liệu. Hãy thử lại hoặc giảm số lượng tài liệu trong một lần.", blueprint_id,
                )


@router.post("", status_code=202)
async def create_draft(body: CreateDraftRequest, request: Request):
    _verify(request)
    if len({document.id for document in body.documents}) != len(body.documents):
        raise HTTPException(422, "Each uploaded document requires a unique id")
    blueprint_id = uuid4()
    manifest = [document.model_dump(exclude={"text"}) for document in body.documents]
    # Keep the response backward-compatible with an older frontend during a
    # rolling deployment.  New clients branch on PROCESSING; old clients can
    # still render this harmless empty plan instead of dereferencing an empty
    # JSON object and crashing.
    processing_plan = {
        "title": "Đang phân tích tài liệu…", "description": "", "category": "",
        "level": "ALL_LEVELS", "tags": [], "chapters": [],
        "governance": body.governance.model_dump(), "evidence_ledger": [],
    }
    async with get_ai_conn() as conn:
        row = await conn.fetchrow(
            """INSERT INTO course_blueprints
               (id, owner_id, origin, status, source_manifest, governance_manifest, plan, validation_report)
               VALUES ($1,$2,$3,'PROCESSING',$4::jsonb,$5::jsonb,$6::jsonb,$7::jsonb) RETURNING *""",
            blueprint_id, body.owner_id, body.origin, json.dumps(manifest),
            json.dumps({"allowed_organization_ids": body.allowed_organization_ids,
                        "allowed_co_teacher_ids": body.allowed_co_teacher_ids}),
            json.dumps(processing_plan), json.dumps({"valid": False, "errors": [], "state": "PROCESSING"}),
        )
    asyncio.create_task(_generate_draft_in_background(blueprint_id, body), name=f"course-blueprint:{blueprint_id}")
    return _dto(row)


@router.get("/{blueprint_id}")
async def get_draft(blueprint_id: UUID, owner_id: int, request: Request):
    _verify(request)
    row = await _row_or_404(blueprint_id)
    if row["owner_id"] != owner_id:
        raise HTTPException(403, "Blueprint belongs to another teacher")
    return _dto(row)


@router.put("/{blueprint_id}")
async def update_draft(blueprint_id: UUID, body: UpdateDraftRequest, request: Request):
    _verify(request)
    row = await _row_or_404(blueprint_id)
    if row["owner_id"] != body.owner_id:
        raise HTTPException(403, "Blueprint belongs to another teacher")
    if row["status"] != "DRAFT":
        raise HTTPException(409, "Only a draft can be edited")
    if row["version"] != body.version:
        raise HTTPException(409, "Blueprint changed; reload before saving")
    manifest = json.loads(row["source_manifest"]) if isinstance(row["source_manifest"], str) else row["source_manifest"]
    governance_manifest = json.loads(row["governance_manifest"]) if isinstance(row["governance_manifest"], str) else row["governance_manifest"]
    report = validate_plan(
        body.plan, {item["id"] for item in manifest},
        set(governance_manifest.get("allowed_organization_ids", [])),
        set(governance_manifest.get("allowed_co_teacher_ids", [])),
    )
    if not report["valid"]:
        raise HTTPException(422, {"message": "Plan violates curriculum invariants", "validation": report})
    order = {chapter_id: index for index, chapter_id in enumerate(report["topological_order"])}
    body.plan.chapters.sort(key=lambda chapter: order[chapter.id])
    async with get_ai_conn() as conn:
        updated = await conn.fetchrow(
            """UPDATE course_blueprints SET plan=$1::jsonb, validation_report=$2::jsonb,
               version=version+1 WHERE id=$3 RETURNING *""",
            body.plan.model_dump_json(), json.dumps(report), blueprint_id,
        )
    return _dto(updated)


@router.post("/{blueprint_id}/approve")
async def approve_draft(blueprint_id: UUID, body: StatusRequest, request: Request):
    _verify(request)
    row = await _row_or_404(blueprint_id)
    if row["owner_id"] != body.owner_id:
        raise HTTPException(403, "Blueprint belongs to another teacher")
    if row["status"] != "DRAFT":
        raise HTTPException(409, "Blueprint is no longer awaiting approval")
    manifest = json.loads(row["source_manifest"]) if isinstance(row["source_manifest"], str) else row["source_manifest"]
    governance_manifest = json.loads(row["governance_manifest"]) if isinstance(row["governance_manifest"], str) else row["governance_manifest"]
    plan_payload = json.loads(row["plan"]) if isinstance(row["plan"], str) else row["plan"]
    report = validate_plan(
        CoursePlan.model_validate(plan_payload), {item["id"] for item in manifest},
        set(governance_manifest.get("allowed_organization_ids", [])),
        set(governance_manifest.get("allowed_co_teacher_ids", [])),
    )
    if not report["valid"]:
        raise HTTPException(422, {"message": "Complete valid ownership settings before approval", "validation": report})
    async with get_ai_conn() as conn:
        updated = await conn.fetchrow(
            "UPDATE course_blueprints SET status='APPROVED' WHERE id=$1 RETURNING *", blueprint_id)
    return _dto(updated)


@router.post("/{blueprint_id}/cancel")
async def cancel_draft(blueprint_id: UUID, body: StatusRequest, request: Request):
    _verify(request)
    row = await _row_or_404(blueprint_id)
    if row["owner_id"] != body.owner_id:
        raise HTTPException(403, "Blueprint belongs to another teacher")
    if row["status"] not in {"PROCESSING", "DRAFT"}:
        raise HTTPException(409, "Only a processing or draft blueprint can be cancelled")
    async with get_ai_conn() as conn:
        updated = await conn.fetchrow(
            "UPDATE course_blueprints SET status='CANCELLED' WHERE id=$1 RETURNING *", blueprint_id)
    return _dto(updated)
