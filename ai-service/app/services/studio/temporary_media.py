"""Private media with a hard ten-minute access deadline and retryable deletion.

The separate bucket has no public policy or versioning. Neither the LMS file
proxy nor permanent bundles can expose it. A manifest is committed BEFORE PUT,
so interrupted renders/uploads still have a cleanup record.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import logging
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.services.minio_storage import _client

logger = logging.getLogger(__name__)
TTL_SECONDS = 600


def bucket_name() -> str:
    settings = get_settings()
    bucket = settings.studio_temporary_bucket or f"{settings.minio_bucket}-studio-temporary"
    if bucket == settings.minio_bucket:
        raise ValueError("Temporary media must use a separate private bucket")
    return bucket


def _private_client():
    from minio.error import S3Error
    client = _client()
    bucket = bucket_name()
    if not client.bucket_exists(bucket):
        try:
            client.make_bucket(bucket)
        except S3Error as exc:
            if exc.code != "BucketAlreadyOwnedByYou":
                raise
    try:
        client.get_bucket_policy(bucket)
    except S3Error as exc:
        if exc.code != "NoSuchBucketPolicy":
            raise
    else:
        raise ValueError("Temporary bucket must have no anonymous access policy")
    if client.get_bucket_versioning(bucket).status:
        raise ValueError("Temporary bucket must have versioning disabled to guarantee deletion")
    return client


async def store(project: dict, generation: str, name: str, data: bytes, media_type: str, *, persistent: bool = False) -> dict:
    asset_id = uuid4()
    key = f"{'source' if persistent else 'temporary'}/{project['id']}/{generation}/{asset_id}/{name}"
    async with get_ai_conn() as conn:
        await conn.execute("""INSERT INTO studio_temporary_media
            (id,project_id,generation,owner_id,course_id,object_key,media_type,size_bytes,storage_bucket)
            VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9)""", asset_id, project["id"], generation,
                           project["created_by"], project["course_id"], key, media_type, len(data), bucket_name())
    def put():
        _private_client().put_object(bucket_name(), key, io.BytesIO(data), len(data), content_type=media_type)
    await asyncio.to_thread(put)
    if persistent:
        async with get_ai_conn() as conn:
            await conn.execute("UPDATE studio_temporary_media SET ready_at=now(),expires_at=NULL WHERE id=$1", asset_id)
    return {"asset_id": str(asset_id), "url": f"/api/ai/studio/media/{asset_id}"}


async def activate(project_id: str, generation: str) -> str:
    """All downloadable bytes in a completed render share one deadline."""
    async with get_ai_conn() as conn:
        expiry = await conn.fetchval("""UPDATE studio_temporary_media SET ready_at=now(),
            expires_at=now()+interval '10 minutes' WHERE project_id=$1::uuid AND generation=$2
            AND ready_at IS NULL AND deleted_at IS NULL RETURNING expires_at""", project_id, generation)
    if not expiry:
        raise ValueError("Missing temporary media manifest")
    return expiry.isoformat()


async def owned_asset(asset_id: str, owner_id: int | None = None, *, ready: bool = True) -> dict:
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("SELECT * FROM studio_temporary_media WHERE id=$1", UUID(asset_id))
    if not row or (owner_id is not None and row["owner_id"] != owner_id):
        raise LookupError("Media not found")
    if row["deleted_at"] or (row["expires_at"] and row["expires_at"] <= datetime.now(timezone.utc)) or (ready and not row["ready_at"]):
        raise ValueError("Video đã hết hạn. Hãy dựng lại từ storyboard đã lưu.")
    return dict(row)


async def read_checkpoint(asset_id: str, owner_id: int) -> bytes | None:
    try:
        asset = await owned_asset(asset_id, owner_id, ready=False)
    except (LookupError, ValueError):
        return None
    def read():
        response = _client().get_object(asset["storage_bucket"], asset["object_key"])
        try:
            data = response.read(32 * 1024 * 1024 + 1)
            return data if len(data) <= 32 * 1024 * 1024 else None
        finally:
            response.close(); response.release_conn()
    return await asyncio.to_thread(read)


def capability(asset: dict, until: int | None = None) -> str:
    secret = get_settings().ai_service_secret
    if not secret:
        raise ValueError("Media signing secret is not configured")
    material = f"studio-download-v1:{asset['id']}:{asset['owner_id']}:{asset['expires_at'].isoformat() if asset['expires_at'] else 'source'}:{until or ''}"
    return hmac.new(secret.encode(), material.encode(), hashlib.sha256).hexdigest()


async def media_response(asset_id: str, *, owner_id: int | None = None, token: str | None = None,
                         range_header: str | None = None, attachment: bool = False, until: int | None = None):
    try:
        asset = await owned_asset(asset_id, owner_id)
    except LookupError:
        raise HTTPException(404, "Media not found")
    except ValueError as exc:
        raise HTTPException(410, str(exc))
    deadline = asset["expires_at"]
    if owner_id is None:
        if not token or not hmac.compare_digest(capability(asset, until), token):
            raise HTTPException(403, "Invalid download link")
        if until is not None:
            try:
                deadline = datetime.fromtimestamp(until, timezone.utc)
            except (ValueError, OverflowError, OSError):
                raise HTTPException(403, "Invalid download link")
            if deadline <= datetime.now(timezone.utc) or (asset["expires_at"] and deadline > asset["expires_at"]):
                raise HTTPException(410, "Download link expired")
        if not deadline:
            raise HTTPException(403, "Invalid download link")
    start, end, size = 0, asset["size_bytes"] - 1, asset["size_bytes"]
    status = 200
    if range_header:
        if len(range_header) > 100:
            raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"})
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or not any(match.groups()):
            raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"})
        first, last = match.groups()
        if first:
            start = int(first); end = min(int(last), end) if last else end
        else:
            start = max(0, size - int(last))
        if start > end or start >= size:
            raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"})
        status = 206
    response = await asyncio.to_thread(_client().get_object, asset["storage_bucket"], asset["object_key"], offset=start, length=end-start+1)
    async def chunks():
        try:
            while deadline is None or datetime.now(timezone.utc) < deadline:
                chunk = await asyncio.to_thread(response.read, 1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            response.close(); response.release_conn()
    headers = {"Cache-Control": "private, no-store", "Accept-Ranges": "bytes", "Content-Length": str(end-start+1),
               "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
    if asset["media_type"].startswith("text/html"):
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if attachment or asset["media_type"] not in {"video/mp4", "application/pdf"}:
        filename = asset["object_key"].rsplit("/", 1)[-1]
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return StreamingResponse(chunks(), status_code=status, media_type=asset["media_type"], headers=headers)


async def cleanup_once() -> int:
    # Claim with a retry deadline; deletion itself is idempotent across replicas.
    async with get_ai_conn() as conn:
        rows = await conn.fetch("""UPDATE studio_temporary_media SET cleanup_after=now()+interval '1 minute',
            cleanup_attempts=cleanup_attempts+1 WHERE id IN (SELECT id FROM studio_temporary_media
            WHERE expires_at<=now() AND deleted_at IS NULL AND cleanup_after<=now()
            ORDER BY expires_at FOR UPDATE SKIP LOCKED LIMIT 100) RETURNING id,object_key,storage_bucket,generation""")
    for row in rows:
        try:
            if row["generation"] == "legacy":
                def purge_versions():
                    client = _client()
                    for version in client.list_objects(row["storage_bucket"], prefix=row["object_key"], recursive=True, include_version=True):
                        if version.object_name == row["object_key"]:
                            client.remove_object(row["storage_bucket"], version.object_name, version_id=version.version_id)
                await asyncio.to_thread(purge_versions)
            await asyncio.to_thread(_client().remove_object, row["storage_bucket"], row["object_key"])
            async with get_ai_conn() as conn:
                await conn.execute("UPDATE studio_temporary_media SET deleted_at=now() WHERE id=$1", row["id"])
        except Exception:
            logger.exception("Temporary media deletion failed asset=%s", row["id"])
    return len(rows)


async def register_legacy_media():
    """Forward cleanup for old public-prefix video/audio/bundles. Keep HTML/JSON.

    Public legacy URLs cannot enforce a deadline, so retire these bytes on rollout.
    Project narratives remain available for rendering into the private bucket.
    """
    from uuid import uuid5, NAMESPACE_URL
    settings = get_settings()
    async with get_ai_conn() as conn:
        projects = await conn.fetch("""SELECT p.id,p.created_by,p.course_id FROM studio_projects p
            WHERE p.kind='video' AND p.status NOT IN ('planning','generating') AND NOT EXISTS
            (SELECT 1 FROM studio_legacy_media_swept s WHERE s.project_id=p.id) ORDER BY p.created_at LIMIT 10""")
    for project in projects:
        prefix = f"studio/{project['id']}/"
        def list_objects():
            return [item for item in _client().list_objects(settings.minio_bucket, prefix=prefix, recursive=True)
                    if item.object_name.endswith((".mp4", ".mp3", ".zip", ".wav", ".input"))]
        objects = await asyncio.to_thread(list_objects)
        async with get_ai_conn() as conn, conn.transaction():
            for item in objects:
                await conn.execute("""INSERT INTO studio_temporary_media
                    (id,project_id,generation,owner_id,course_id,object_key,media_type,size_bytes,storage_bucket,ready_at,expires_at)
                    VALUES($1,$2,'legacy',$3,$4,$5,'application/octet-stream',$6,$7,now(),now()) ON CONFLICT DO NOTHING""",
                    uuid5(NAMESPACE_URL, f"studio-legacy:{settings.minio_bucket}/{item.object_name}"), project["id"],
                    project["created_by"], project["course_id"], item.object_name, item.size, settings.minio_bucket)
            await conn.execute("INSERT INTO studio_legacy_media_swept(project_id) VALUES($1) ON CONFLICT DO NOTHING", project["id"])


async def serve_cleanup():
    while True:
        try:
            await cleanup_once()
            await register_legacy_media()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Temporary media cleanup failed")
        await asyncio.sleep(15)
