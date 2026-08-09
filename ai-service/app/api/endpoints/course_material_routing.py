from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.services.course_blueprint_service import SourceDocument
from app.services.course_material_routing_service import RoutingSection

router = APIRouter(prefix="/course-material-routing", tags=["Course material routing"])
settings = get_settings()
logger = logging.getLogger(__name__)


class CreateRoutingRequest(BaseModel):
    owner_id: int
    course_id: int
    documents: list[SourceDocument] = Field(min_length=1, max_length=100)
    sections: list[RoutingSection] = Field(min_length=1, max_length=100)


def _verify(request: Request) -> None:
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(403, "Unauthorized internal call")


def _dto(row):
    decode = lambda value: json.loads(value) if isinstance(value, str) else value
    return {"id": str(row["id"]), "owner_id": row["owner_id"], "course_id": row["course_id"],
            "status": row["status"], "documents": decode(row["documents"]),
            "sections": decode(row["sections"]), "suggestions": decode(row["suggestions"]),
            "error_message": row["error_message"]}


@router.post("", status_code=202)
async def create(body: CreateRoutingRequest, request: Request):
    _verify(request)
    job_id = uuid4()
    async with get_ai_conn() as conn:
        row = await conn.fetchrow(
            """INSERT INTO course_material_routing_jobs(id,owner_id,course_id,documents,sections)
               VALUES($1,$2,$3,$4::jsonb,$5::jsonb) RETURNING *""", job_id, body.owner_id,
            body.course_id, json.dumps([d.model_dump(exclude={"text"}) for d in body.documents]),
            json.dumps([s.model_dump() for s in body.sections]))
    try:
        from app.worker.kafka_producer import get_kafka_producer
        producer = await get_kafka_producer()
        await producer.send_and_wait("lms.course-blueprint.command", value={"routing_id": str(job_id)}, key=str(job_id).encode())
    except Exception:
        logger.exception("Material routing publish failed id=%s; recovery will retry", job_id)
    return _dto(row)


@router.get("/{job_id}")
async def get(job_id: UUID, owner_id: int, request: Request):
    _verify(request)
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("SELECT * FROM course_material_routing_jobs WHERE id=$1", job_id)
    if not row: raise HTTPException(404, "Routing job not found")
    if row["owner_id"] != owner_id: raise HTTPException(403, "Routing job belongs to another teacher")
    return _dto(row)
