"""
ai-service/app/services/minio_storage.py

Minimal MinIO upload/download helpers used by the micro-lesson generator
and the smarter document -> Markdown pipeline (Phase A).

The Go lms-service is the canonical owner of the bucket layout — files
uploaded by users live under prefixes like "image/", "document/", "video/".
We add a new prefix for AI-generated assets:

    micro-lesson/<course_id>/<job_id>/img-<n>.png
    document-images/<content_id>/p<page>-<n>.png

So the MinIO key remains compatible with the Go file_handler's serve and
presigned-URL routes (the same clients can fetch them).
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _client():
    """Build a fresh MinIO client. Cheap; reuse via thread-local if needed."""
    from minio import Minio

    endpoint = settings.minio_endpoint.replace("https://", "").replace("http://", "")
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
    )


async def upload_bytes(
    object_key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> Optional[str]:
    """
    Upload `data` to MinIO under the given key. Returns the relative URL
    that LMS frontend uses to serve files (e.g. "/files/<key>") or None
    on failure.
    """
    loop = asyncio.get_event_loop()

    def _sync_upload() -> Optional[str]:
        try:
            client = _client()
            client.put_object(
                settings.minio_bucket,
                object_key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return f"/files/{object_key}"
        except Exception as exc:
            logger.error("MinIO upload failed key=%s: %s", object_key, exc, exc_info=True)
            return None

    return await loop.run_in_executor(None, _sync_upload)


async def get_presigned_url(object_key: str, expires_in_sec: int = 3600) -> Optional[str]:
    """Generate a presigned GET URL straight from MinIO (bypasses LMS proxy)."""
    loop = asyncio.get_event_loop()

    def _sync_presign() -> Optional[str]:
        try:
            from datetime import timedelta

            client = _client()
            return client.presigned_get_object(
                settings.minio_bucket,
                object_key,
                expires=timedelta(seconds=expires_in_sec),
            )
        except Exception as exc:
            logger.warning("MinIO presign failed key=%s: %s", object_key, exc)
            return None

    return await loop.run_in_executor(None, _sync_presign)