"""
ai-service/app/api/endpoints/process.py

POST /ai/process-document - trigger document processing via Kafka.
GET  /ai/process-document/{job_id} - poll job status from AI DB.

The job is queued by publishing to the lms.document.uploaded Kafka topic.
The ai-worker consumer picks it up and calls auto_index_service.
Status updates come back via ai.document.processed.status topic to LMS DB.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import get_ai_conn

logger   = logging.getLogger(__name__)
settings = get_settings()
router   = APIRouter(prefix="/process-document", tags=["Document Processing"])


class ProcessDocumentRequest(BaseModel):
    content_id: int
    course_id: int
    node_id: int | None = None
    file_url: str
    content_type: str = "application/pdf"


class ProcessDocumentResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post("", response_model=ProcessDocumentResponse)
async def trigger_processing(body: ProcessDocumentRequest, request: Request):
    _verify(request)

    # Clear existing chunks so re-index starts fresh
    from app.services.rag_service import rag_service
    await rag_service.delete_chunks_for_content(body.content_id)

    # Track status in AI DB
    async with get_ai_conn() as conn:
        await conn.execute(
            """
            INSERT INTO content_index_status (content_id, course_id, status, updated_at)
            VALUES ($1, $2, 'pending', NOW())
            ON CONFLICT (content_id) DO UPDATE
                SET status = 'pending', updated_at = NOW()
            """,
            body.content_id, body.course_id,
        )

    # Publish to Kafka - ai-worker will pick this up
    from app.worker.kafka_producer import get_kafka_producer
    producer = await get_kafka_producer()
    payload = {
        "content_id":   body.content_id,
        "course_id":    body.course_id,
        "node_id":      body.node_id,
        "file_url":     body.file_url,
        "content_type": body.content_type,
    }
    await producer.send_and_wait("lms.document.uploaded", value=payload)

    logger.info(
        "Queued document processing via Kafka: content_id=%d course_id=%d",
        body.content_id, body.course_id,
    )

    return ProcessDocumentResponse(
        job_id=f"content-{body.content_id}",
        status="pending",
        message=f"Document queued for processing (content_id={body.content_id})",
    )


@router.get("/{content_id}")
async def get_job_status(content_id: int, request: Request):
    _verify(request)
    async with get_ai_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT content_id, course_id, status, error, updated_at
            FROM content_index_status
            WHERE content_id = $1
            """,
            content_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"No status found for content_id={content_id}")
    return dict(row)


def _verify(request: Request):
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized internal call")
