"""Durable AI-owned queue consumed by the existing AI Kafka worker workload."""
from __future__ import annotations

import asyncio
import json
import hashlib
import logging
from contextvars import ContextVar
from uuid import uuid4

from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)
active_lease: ContextVar[tuple | None] = ContextVar("studio_lease", default=None)


async def enqueue(project_id: str, owner_id: int, operation: str, request: dict | None = None) -> dict:
    from app.core.config import get_settings
    settings = get_settings()
    async with get_ai_conn() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", owner_id)
        project = await conn.fetchrow("SELECT * FROM studio_projects WHERE id=$1::uuid AND created_by=$2 FOR UPDATE", project_id, owner_id)
        if not project:
            raise ValueError("project not found")
        current = await conn.fetchrow("SELECT id FROM studio_jobs WHERE project_id=$1::uuid AND status IN ('queued','running')", project_id)
        if current:
            return {"already_running": True, "job_id": str(current["id"])}
        active = await conn.fetchval("SELECT count(*) FROM studio_jobs WHERE owner_id=$1 AND status IN ('queued','running')", owner_id)
        if active >= settings.studio_max_active_jobs_per_user:
            raise ValueError("Đang có nhiều job Studio. Chờ job hiện tại hoàn tất rồi thử lại.")
        if operation == "render":
            recent = await conn.fetchval("SELECT count(*) FROM studio_jobs WHERE owner_id=$1 AND operation='render' AND created_at>now()-interval '1 hour'", owner_id)
            if recent >= settings.studio_max_render_jobs_per_hour:
                raise ValueError("Đã đạt giới hạn render Studio trong một giờ. Hãy thử lại sau.")
        if operation == "render" and not project["plan"]:
            raise ValueError("plan required before generating")
        job_id = uuid4()
        request = dict(request or {})
        material = [project["context_pack"], project["settings"], project["plan"] if operation == "render" else None, request]
        request["input_hash"] = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()
        previous = await conn.fetchval("""SELECT checkpoint FROM studio_jobs WHERE project_id=$1::uuid AND owner_id=$2
            AND operation=$3 AND status='failed' AND request->>'input_hash'=$4 ORDER BY created_at DESC LIMIT 1""",
                                       project_id, owner_id, operation, request["input_hash"])
        previous = previous if isinstance(previous, str) else json.dumps(previous or {})
        await conn.execute("INSERT INTO studio_jobs(id, project_id, owner_id, operation, request, checkpoint) VALUES($1,$2::uuid,$3,$4,$5::jsonb,$6::jsonb)",
                           job_id, project_id, owner_id, operation, json.dumps(request), previous)
        await conn.execute("UPDATE studio_projects SET current_job_id=$1, status=$2, error_detail=NULL, updated_at=now() WHERE id=$3::uuid",
                           job_id, "planning" if operation == "plan" else "generating", project_id)
    return {"started": True, "job_id": str(job_id)}


async def checkpoint(name: str, value: dict | None = None) -> dict | None:
    lease = active_lease.get()
    if not lease:
        return None
    job_id, token = lease
    async with get_ai_conn() as conn:
        if value is not None:
            await conn.execute("""UPDATE studio_jobs SET checkpoint=jsonb_set(checkpoint,ARRAY[$3::text],$4::jsonb),updated_at=now()
                WHERE id=$1 AND lease_token=$2 AND status='running' AND lease_until>now()""", job_id, token, name, json.dumps(value))
            return value
        data = await conn.fetchval("SELECT checkpoint->$3::text FROM studio_jobs WHERE id=$1 AND lease_token=$2", job_id, token, name)
        return json.loads(data) if isinstance(data, str) else data


async def run_next() -> bool:
    token = uuid4()
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("""UPDATE studio_jobs SET status='running',lease_token=$1,
            lease_until=now()+interval '3 minutes',attempts=attempts+1,updated_at=now()
            WHERE id=(SELECT id FROM studio_jobs WHERE status='queued' OR (status='running' AND lease_until<now())
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""", token)
    if not row:
        return False
    lease_context = active_lease.set((row["id"], token))
    work = asyncio.current_task()
    lost_lease = False

    async def heartbeat():
        nonlocal lost_lease
        while True:
            await asyncio.sleep(30)
            async with get_ai_conn() as conn:
                updated = await conn.fetchval("""UPDATE studio_jobs SET lease_until=now()+interval '3 minutes'
                    WHERE id=$1 AND lease_token=$2 AND status='running' AND lease_until>now() RETURNING id""", row["id"], token)
            if not updated:
                lost_lease = True
                work.cancel()
                return

    beat = asyncio.create_task(heartbeat())
    from app.services.studio.studio_service import studio_service
    try:
        if row["attempts"] > 3:
            raise ValueError("Studio worker retry limit reached; retry from Studio")
        from mcp.course_access import user_can_read_course
        project = await studio_service.get_project(str(row["project_id"]), row["owner_id"])
        if not project or not await user_can_read_course(row["owner_id"], project["course_id"]):
            raise ValueError("Course access was revoked before this job could start")
        async with asyncio.timeout(7200):
            if row["operation"] == "plan":
                request = json.loads(row["request"]) if isinstance(row["request"], str) else row["request"]
                result = await studio_service.generate_plan(str(row["project_id"]), row["owner_id"], request.get("target_sections"))
                await checkpoint("warnings", {"values": result.get("warnings", [])})
            else:
                await studio_service._generate_and_store(str(row["project_id"]), row["owner_id"])
        project = await studio_service.get_project(str(row["project_id"]), row["owner_id"])
        final_status = "failed" if project["status"] == "failed" else "ready"
    except asyncio.CancelledError:
        if lost_lease:
            work.uncancel()
            return True
        raise  # leave the durable lease recoverable
    except Exception as exc:
        logger.exception("Studio job failed id=%s", row["id"])
        await studio_service._update(str(row["project_id"]), row["owner_id"], status="failed", error_detail=str(exc)[:800])
        final_status = "failed"
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)
        active_lease.reset(lease_context)
    async with get_ai_conn() as conn:
        await conn.execute("""UPDATE studio_jobs SET status=$3,lease_until=NULL,updated_at=now()
            WHERE id=$1 AND lease_token=$2 AND status='running'""", row["id"], token, final_status)
    return True


async def serve() -> None:
    while True:
        try:
            if await run_next():
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Studio worker sweep failed")
        await asyncio.sleep(5)
