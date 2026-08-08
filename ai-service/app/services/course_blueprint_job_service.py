"""Durable execution of course-blueprint jobs, owned by worker processes."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from app.core.database import get_ai_conn
from app.services.course_blueprint_service import (
    CourseGovernance, SourceDocument, course_blueprint_service, validate_plan,
)

logger = logging.getLogger(__name__)
LEASE_SECONDS = 180


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


async def _heartbeat(blueprint_id: UUID, worker_id: str, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
            break
        except TimeoutError:
            async with get_ai_conn() as conn:
                await conn.execute(
                    """UPDATE course_blueprints SET lease_until=NOW() + ($1 * INTERVAL '1 second'),
                       processing_stage='ANALYSING', progress_pct=25
                       WHERE id=$2 AND status='PROCESSING' AND lease_owner=$3""",
                    LEASE_SECONDS, blueprint_id, worker_id,
                )


async def run_course_blueprint_job(blueprint_id: UUID, worker_id: str) -> bool:
    """Claim and execute one job. Safe to call more than once (at-least-once Kafka)."""
    async with get_ai_conn() as conn:
        row = await conn.fetchrow(
            """UPDATE course_blueprints
               SET lease_owner=$2, lease_until=NOW() + ($3 * INTERVAL '1 second'),
                   processing_stage='ANALYSING', progress_pct=5, attempts=attempts+1,
                   error_message=NULL
               WHERE id=$1 AND status='PROCESSING'
                 AND (lease_until IS NULL OR lease_until < NOW())
               RETURNING *""",
            blueprint_id, worker_id, LEASE_SECONDS,
        )
    if not row:
        return False

    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat(blueprint_id, worker_id, stop))
    try:
        documents = [SourceDocument.model_validate(item) for item in _json(row["source_manifest"])]
        manifest = _json(row["governance_manifest"])
        current_plan = _json(row["plan"])
        governance = CourseGovernance.model_validate(current_plan.get("governance", {}))
        language = manifest.get("language", "vi")
        plan, report = await course_blueprint_service.draft(documents, language)
        plan.governance = governance
        allowed_orgs = set(manifest.get("allowed_organization_ids", []))
        if plan.governance.organization_id is None and len(allowed_orgs) == 1:
            plan.governance.organization_id = next(iter(allowed_orgs))
        report = validate_plan(plan, {doc.id for doc in documents}, allowed_orgs,
                               set(manifest.get("allowed_co_teacher_ids", [])))
        if not report["valid"] and any(item["code"] != "organization_required" for item in report["errors"]):
            raise ValueError("Generated blueprint violates curriculum invariants")
        async with get_ai_conn() as conn:
            await conn.execute(
                """UPDATE course_blueprints
                   SET status='DRAFT', plan=$1::jsonb, validation_report=$2::jsonb,
                       processing_stage='READY', progress_pct=100, lease_owner=NULL, lease_until=NULL,
                       error_message=NULL
                   WHERE id=$3 AND status='PROCESSING' AND lease_owner=$4""",
                plan.model_dump_json(), json.dumps(report), blueprint_id, worker_id,
            )
        return True
    except Exception:
        logger.exception("Course blueprint generation failed id=%s", blueprint_id)
        async with get_ai_conn() as conn:
            await conn.execute(
                """UPDATE course_blueprints
                   SET status='FAILED', validation_report=$1::jsonb, processing_stage='FAILED',
                       lease_owner=NULL, lease_until=NULL, error_message=$2
                   WHERE id=$3 AND status='PROCESSING' AND lease_owner=$4""",
                json.dumps({"valid": False, "errors": [{"code": "generation_failed", "message": "Không thể tạo đề xuất AI."}]}),
                "AI không thể hoàn tất phân tích tài liệu. Hãy thử lại hoặc giảm số lượng tài liệu trong một lần.",
                blueprint_id, worker_id,
            )
        return True
    finally:
        stop.set()
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def recoverable_blueprint_ids(limit: int = 8) -> list[UUID]:
    """Find jobs not yet leased or abandoned by a dead worker."""
    async with get_ai_conn() as conn:
        rows = await conn.fetch(
            """SELECT id FROM course_blueprints WHERE status='PROCESSING'
               AND (lease_until IS NULL OR lease_until < NOW())
               ORDER BY updated_at ASC LIMIT $1""", limit,
        )
    return [row["id"] for row in rows]
