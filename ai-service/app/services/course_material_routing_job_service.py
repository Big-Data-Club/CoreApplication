from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID
from app.core.database import get_ai_conn
from app.services.course_blueprint_service import SourceDocument
from app.services.course_material_routing_service import RoutingSection, suggest_material_routes

logger = logging.getLogger(__name__)


async def _heartbeat(job_id: UUID, worker_id: str, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            async with get_ai_conn() as conn:
                await conn.execute("""UPDATE course_material_routing_jobs
                    SET lease_until=NOW()+INTERVAL '3 minutes', updated_at=NOW()
                    WHERE id=$1 AND status='PROCESSING' AND lease_owner=$2""", job_id, worker_id)


async def run_material_routing_job(job_id: UUID, worker_id: str) -> bool:
    async with get_ai_conn() as conn:
        row = await conn.fetchrow(
            """UPDATE course_material_routing_jobs SET lease_owner=$2,
               lease_until=NOW()+INTERVAL '3 minutes', attempts=attempts+1, error_message=NULL,
               updated_at=NOW()
               WHERE id=$1 AND status='PROCESSING' AND (lease_until IS NULL OR lease_until<NOW()) RETURNING *""",
            job_id, worker_id)
    if not row: return False
    decode = lambda value: json.loads(value) if isinstance(value, str) else value
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat(job_id, worker_id, stop))
    try:
        suggestions = await suggest_material_routes(
            [SourceDocument.model_validate(item) for item in decode(row["documents"])],
            [RoutingSection.model_validate(item) for item in decode(row["sections"])])
        async with get_ai_conn() as conn:
            await conn.execute(
                """UPDATE course_material_routing_jobs SET status='READY', suggestions=$1::jsonb,
                   lease_owner=NULL,lease_until=NULL WHERE id=$2 AND lease_owner=$3""",
                json.dumps([item.model_dump() for item in suggestions]), job_id, worker_id)
        return True
    except Exception:
        logger.exception("Course material routing failed id=%s", job_id)
        async with get_ai_conn() as conn:
            await conn.execute(
                """UPDATE course_material_routing_jobs SET status='FAILED',error_message=$1,
                   lease_owner=NULL,lease_until=NULL WHERE id=$2 AND lease_owner=$3""",
                "AI không thể phân loại tài liệu. Bạn vẫn có thể chọn chương thủ công.", job_id, worker_id)
        return True
    finally:
        stop.set()
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def recoverable_material_routing_ids(limit: int = 8) -> list[UUID]:
    async with get_ai_conn() as conn:
        rows = await conn.fetch("""SELECT id FROM course_material_routing_jobs WHERE status='PROCESSING'
            AND (lease_until IS NULL OR lease_until<NOW()) ORDER BY updated_at LIMIT $1""", limit)
    return [row["id"] for row in rows]
