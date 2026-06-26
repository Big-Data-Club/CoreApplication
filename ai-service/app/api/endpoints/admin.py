from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import get_ai_conn

logger   = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/admin", tags=["Admin - Migration"])


class ReindexRequest(BaseModel):
    course_id: Optional[int] = None


@router.post("/reindex")
async def trigger_reindex(body: ReindexRequest, request: Request):
    _verify(request)
    from app.services.reindex_service import reindex_service
    return await reindex_service.enqueue_all(course_id=body.course_id)


@router.get("/reindex/status")
async def reindex_status(request: Request):
    _verify(request)
    from app.services.reindex_service import reindex_service
    progress = await reindex_service.get_progress()

    async with get_ai_conn() as conn:
        failed = await conn.fetch(
            """
            SELECT content_id, error_message, updated_at
            FROM embedding_reindex_jobs
            WHERE status = 'failed'
            ORDER BY updated_at DESC
            LIMIT 20
            """
        )

    return {
        **progress,
        "failed_jobs": [dict(r) for r in failed],
        "ready_for_cutover": (
            progress.get("pending", -1) == 0
            and progress.get("processing", -1) == 0
            and progress.get("failed", -1) == 0
            and progress.get("total_jobs", 0) > 0
        ),
    }


@router.post("/reindex/cutover-check")
async def cutover_check(request: Request):
    _verify(request)

    async with get_ai_conn() as conn:
        # 1. Chunks still missing embedding in AI DB?
        pending_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM document_chunks WHERE embedding IS NULL"
        )
        # 2. Active reindex jobs?
        active_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM embedding_reindex_jobs WHERE status IN ('pending','processing')"
        )
        # 3. HNSW index exists on embedding column?
        idx_row = await conn.fetchrow(
            """SELECT COUNT(*) AS cnt FROM pg_indexes
               WHERE tablename='document_chunks' AND indexname='idx_dc_emb_hnsw'"""
        )

    pending_chunks = int(pending_row["cnt"])
    active_jobs    = int(active_row["cnt"])
    idx_exists     = int(idx_row["cnt"]) > 0

    checks = {
        "hnsw_index_exists":              idx_exists,
        "no_pending_reindex_jobs":        active_jobs == 0,
        "no_chunks_missing_embedding":    pending_chunks == 0,
    }

    return {
        "ready_for_cutover":          all(checks.values()),
        "checks":                     checks,
        "pending_chunks":             pending_chunks,
        "active_reindex_jobs":        active_jobs,
    }


def _verify(request: Request):
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")