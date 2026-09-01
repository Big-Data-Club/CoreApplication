"""Internal API for the review-first course creation workflow.

Both the teacher create-course screen and chatbot call the same endpoints.
The caller uploads files through LMS first, extracts normalised text, then
sends that text + opaque file paths here.  That keeps chat and UI behaviour
identical while avoiding duplicate file pipelines.
"""
from __future__ import annotations

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


class AppliedRequest(StatusRequest):
    course_id: int = Field(gt=0)


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
        "processing_stage": row.get("processing_stage") if hasattr(row, "get") else row["processing_stage"],
        "progress_pct": row.get("progress_pct") if hasattr(row, "get") else row["progress_pct"],
    }


def _validate_external_mcp_plan(plan: object) -> dict:
    """Validate legacy MCP curriculum without requiring uploaded material IDs."""
    errors: list[dict[str, str]] = []
    if not isinstance(plan, dict):
        return {"valid": False, "errors": [{"code": "invalid_plan", "message": "Course plan must be an object."}]}
    title = str(plan.get("title") or "").strip()
    chapters = plan.get("chapters")
    if not 3 <= len(title) <= 255:
        errors.append({"code": "invalid_title", "message": "Course title must contain 3–255 characters."})
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= 50:
        errors.append({"code": "invalid_chapters", "message": "Course requires 1–50 chapters."})
        chapters = []
    lesson_count = 0
    for chapter_index, chapter in enumerate(chapters, 1):
        if not isinstance(chapter, dict) or not 3 <= len(str(chapter.get("title") or "").strip()) <= 255:
            errors.append({"code": "invalid_chapter", "message": f"Chapter {chapter_index} requires a 3–255 character title."})
            continue
        lessons = chapter.get("lessons", [])
        if not isinstance(lessons, list):
            errors.append({"code": "invalid_lessons", "message": f"Chapter {chapter_index} lessons must be an array."})
            continue
        lesson_count += len(lessons)
        for lesson_index, lesson in enumerate(lessons, 1):
            lesson_title = lesson if isinstance(lesson, str) else lesson.get("title") if isinstance(lesson, dict) else ""
            if not 3 <= len(str(lesson_title or "").strip()) <= 255:
                errors.append({"code": "invalid_lesson", "message": f"Chapter {chapter_index}, lesson {lesson_index} requires a valid title."})
    if lesson_count > 300:
        errors.append({"code": "too_many_lessons", "message": "A course supports at most 300 lessons in one blueprint."})
    return {"valid": not errors, "errors": errors, "lesson_count": lesson_count, "state": "DRAFT", "author": "external_mcp_client"}


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
                        "allowed_co_teacher_ids": body.allowed_co_teacher_ids,
                        "language": body.language}),
            json.dumps(processing_plan), json.dumps({"valid": False, "errors": [], "state": "PROCESSING"}),
        )
    # The API process must never own OCR/LLM work: a rollout would terminate
    # it.  The durable row is the source of truth; Kafka is a wake-up signal
    # and the dedicated worker also reconciles unleased rows after an outage.
    try:
        from app.worker.kafka_producer import get_kafka_producer
        producer = await get_kafka_producer()
        await producer.send_and_wait(
            "lms.course-blueprint.command",
            value={"blueprint_id": str(blueprint_id)}, key=str(blueprint_id).encode(),
        )
    except Exception:
        logger.exception("Could not publish course blueprint id=%s; worker reconciliation will retry", blueprint_id)
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
    # Approval is a state transition, but callers may retry after a dropped
    # response or a BFF/frontend race.  Returning the already-approved draft
    # makes the operation idempotent and prevents a harmless retry becoming a
    # misleading 502 during course materialisation.
    if row["status"] in {"APPROVED", "APPLIED"}:
        return _dto(row)
    if row["status"] != "DRAFT":
        raise HTTPException(409, "Blueprint is no longer awaiting approval")
    plan_payload = json.loads(row["plan"]) if isinstance(row["plan"], str) else row["plan"]
    if row["origin"] == "chatbot":
        report = _validate_external_mcp_plan(plan_payload)
    else:
        manifest = json.loads(row["source_manifest"]) if isinstance(row["source_manifest"], str) else row["source_manifest"]
        governance_manifest = json.loads(row["governance_manifest"]) if isinstance(row["governance_manifest"], str) else row["governance_manifest"]
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


@router.post("/{blueprint_id}/applied")
async def mark_applied(blueprint_id: UUID, body: AppliedRequest, request: Request):
    """Record the LMS course created from this blueprint; safe to retry."""
    _verify(request)
    row = await _row_or_404(blueprint_id)
    if row["owner_id"] != body.owner_id:
        raise HTTPException(403, "Blueprint belongs to another teacher")
    if row["status"] == "APPLIED":
        if row["applied_course_id"] != body.course_id:
            raise HTTPException(409, "Blueprint was applied to a different course")
        return _dto(row)
    if row["status"] != "APPROVED":
        raise HTTPException(409, "Blueprint must be approved before it can be marked applied")
    async with get_ai_conn() as conn:
        updated = await conn.fetchrow(
            "UPDATE course_blueprints SET status='APPLIED', applied_course_id=$2 WHERE id=$1 RETURNING *",
            blueprint_id, body.course_id,
        )
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
