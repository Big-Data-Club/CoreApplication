"""Leased uploads to the admin-managed SHARED channel; no user OAuth tokens.

The authenticated frontend bridge owns the existing channel connection. Only
workers receive an encrypted resumable session; external models receive IDs,
metadata and status. Resume the SAME session after interruption to avoid
duplicate videos. Never extend media expiry to finish an upload.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.llm_gateway.crypto import encrypt, decrypt
from app.services.minio_storage import _client
from app.services.studio.temporary_media import owned_asset

logger = logging.getLogger(__name__)
CHUNK_SIZE = 8 * 1024 * 1024


async def bridge(action: str, **data) -> dict:
    settings = get_settings()
    if not settings.ai_service_secret:
        raise ValueError("YouTube bridge secret is not configured")
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        response = await client.post(settings.studio_youtube_bridge_url,
            headers={"X-AI-Secret": settings.ai_service_secret}, json={"action": action, **data})
    if response.status_code != 200:
        # Never echo OAuth responses/session URLs/secrets into logs or MCP output.
        raise ValueError("Kênh YouTube chung chưa sẵn sàng. Nhờ admin kiểm tra kết nối và quota.")
    return response.json()


def validate_session_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "www.googleapis.com" or parsed.path != "/upload/youtube/v3/videos":
        raise ValueError("Invalid YouTube resumable session URL")
    return url


async def request_upload(owner_id: int, asset_id: str, channel_id: str, title: str, description: str,
                         privacy: str, made_for_kids: bool, contains_synthetic_media: bool) -> dict:
    asset = await owned_asset(asset_id, owner_id)
    if asset["media_type"] != "video/mp4":
        raise ValueError("Choose an MP4 asset")
    from mcp.course_access import user_owns_course
    if not await user_owns_course(owner_id, asset["course_id"]):
        raise PermissionError("Chỉ chủ khóa học hoặc đồng giảng viên được đăng lên kênh chung.")
    if not 1 <= len(title.strip()) <= 100 or len(description) > 5000 or privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Invalid YouTube title, description or privacy")
    status = await bridge("status")
    if not status.get("connected") or status.get("channel_id") != channel_id:
        raise ValueError("Kênh chung đã thay đổi. Đọc trạng thái và xác nhận lại kênh đích.")
    async with get_ai_conn() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", owner_id)
        previous = await conn.fetchrow("SELECT * FROM studio_youtube_uploads WHERE asset_id=$1", UUID(asset_id))
        if previous:
            if (previous["channel_id"], previous["title"], previous["description"], previous["privacy"], previous["made_for_kids"], previous["contains_synthetic_media"]) != (channel_id, title.strip(), description, privacy, made_for_kids, contains_synthetic_media):
                raise ValueError("This asset already has an upload with different metadata")
            if previous["status"] == "failed":
                await conn.execute("UPDATE studio_youtube_uploads SET status='queued',attempts=0,error=NULL WHERE id=$1", previous["id"])
            return {"upload_id": str(previous["id"]), "status": "queued" if previous["status"] == "failed" else previous["status"]}
        count = await conn.fetchval("SELECT count(*) FROM studio_youtube_uploads WHERE owner_id=$1 AND created_at>now()-interval '1 day'", owner_id)
        if count >= 5:
            raise ValueError("Đã đạt giới hạn 5 video/ngày trên kênh chung.")
        upload_id = uuid4()
        await conn.execute("""INSERT INTO studio_youtube_uploads
            (id,asset_id,owner_id,channel_id,title,description,privacy,made_for_kids,contains_synthetic_media)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)""", upload_id, UUID(asset_id), owner_id,
            channel_id, title.strip(), description, privacy, made_for_kids, contains_synthetic_media)
    return {"upload_id": str(upload_id), "status": "queued", "expires_at": asset["expires_at"].isoformat()}


async def get_upload(upload_id: str, owner_id: int, *, refresh: bool = False) -> dict:
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("SELECT * FROM studio_youtube_uploads WHERE id=$1 AND owner_id=$2", UUID(upload_id), owner_id)
    if not row:
        raise LookupError("Upload not found")
    result = {key: row[key] for key in ("id", "asset_id", "channel_id", "title", "privacy", "actual_privacy", "processing_status", "status", "error", "video_id")}
    result["id"] = str(result["id"]); result["asset_id"] = str(result["asset_id"])
    if row["video_id"]:
        result["url"] = f"https://www.youtube.com/watch?v={row['video_id']}"
        if refresh:
            actual = await bridge("video", video_id=row["video_id"])
            if actual.get("channel_id") != row["channel_id"]:
                raise ValueError("Video is not on the confirmed shared channel")
            result.update(actual_privacy=actual["privacy"], processing_status=actual["upload_status"])
            async with get_ai_conn() as conn:
                await conn.execute("UPDATE studio_youtube_uploads SET actual_privacy=$2,processing_status=$3 WHERE id=$1",
                                   row["id"], actual["privacy"], actual["upload_status"])
    return result


async def _lease(upload_id, token):
    async with get_ai_conn() as conn:
        result = await conn.fetchval("""UPDATE studio_youtube_uploads SET lease_until=now()+interval '2 minutes',updated_at=now()
            WHERE id=$1 AND lease_token=$2 AND lease_until>now() AND status='running' RETURNING id""", upload_id, token)
    if not result:
        raise ValueError("YouTube upload lease lost")


async def run_next_upload() -> bool:
    token = uuid4()
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("""UPDATE studio_youtube_uploads SET status='running',lease_token=$1,
            lease_until=now()+interval '2 minutes',attempts=attempts+1,updated_at=now() WHERE id=(SELECT id
            FROM studio_youtube_uploads WHERE status='queued' OR (status='running' AND lease_until<now())
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""", token)
    if not row:
        return False
    try:
        if row["attempts"] > 3:
            raise ValueError("Upload retry limit reached")
        asset = await owned_asset(str(row["asset_id"]), row["owner_id"])
        from mcp.course_access import user_owns_course
        if not await user_owns_course(row["owner_id"], asset["course_id"]):
            raise PermissionError("Course publishing access was revoked")
        # Token refresh stays with the existing shared-channel manager.
        auth = await bridge("token", channel_id=row["channel_id"])
        bearer = {"Authorization": f"Bearer {auth['access_token']}"}
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
            if row["encrypted_session"]:
                session_url = validate_session_url(decrypt(row["encrypted_session"]))
            else:
                await _lease(row["id"], token)
                initiated = await client.post("https://www.googleapis.com/upload/youtube/v3/videos",
                    params={"uploadType": "resumable", "part": "snippet,status", "notifySubscribers": "false"},
                    headers={**bearer, "X-Upload-Content-Length": str(asset["size_bytes"]), "X-Upload-Content-Type": "video/mp4"},
                    json={"snippet": {"title": row["title"], "description": row["description"], "categoryId": "27"},
                          "status": {"privacyStatus": row["privacy"], "selfDeclaredMadeForKids": row["made_for_kids"],
                                     "containsSyntheticMedia": row["contains_synthetic_media"], "embeddable": True}})
                if initiated.status_code not in {200, 201}:
                    raise ValueError("YouTube rejected the upload session")
                session_url = validate_session_url(initiated.headers.get("location", ""))
                async with get_ai_conn() as conn:
                    await conn.execute("""UPDATE studio_youtube_uploads SET encrypted_session=$3
                        WHERE id=$1 AND lease_token=$2 AND lease_until>now()""", row["id"], token, encrypt(session_url))
            await _lease(row["id"], token)
            response = await client.put(session_url, headers={**bearer, "Content-Length": "0", "Content-Range": f"bytes */{asset['size_bytes']}"}, content=b"")
            while response.status_code == 308:
                await owned_asset(str(row["asset_id"]), row["owner_id"])
                await _lease(row["id"], token)
                received = response.headers.get("range", "")
                if received and not re.fullmatch(r"bytes=0-\d+", received):
                    raise ValueError("Invalid YouTube upload offset")
                start = int(received.split("-")[-1]) + 1 if received else 0
                length = min(CHUNK_SIZE, asset["size_bytes"] - start)
                if length <= 0:
                    raise ValueError("Invalid completed YouTube range")
                def read_chunk():
                    media = _client().get_object(asset["storage_bucket"], asset["object_key"], offset=start, length=length)
                    try:
                        return media.read(length)
                    finally:
                        media.close(); media.release_conn()
                data = await asyncio.to_thread(read_chunk)
                if len(data) != length:
                    raise ValueError("Incomplete temporary media read")
                response = await client.put(session_url, headers={**bearer, "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {start}-{start+length-1}/{asset['size_bytes']}"}, content=data)
            if response.status_code not in {200, 201}:
                raise ValueError("YouTube upload failed; retry before media expires")
            video = response.json()
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(video.get("id", ""))):
                raise ValueError("YouTube did not return a valid video ID")
            async with get_ai_conn() as conn:
                await conn.execute("""UPDATE studio_youtube_uploads SET status='ready',video_id=$3,
                    actual_privacy=$4,processing_status=$5,error=NULL,lease_until=NULL,updated_at=now()
                    WHERE id=$1 AND lease_token=$2 AND lease_until>now()""", row["id"], token, video["id"],
                    video.get("status", {}).get("privacyStatus", "private"), video.get("status", {}).get("uploadStatus", "uploaded"))
    except asyncio.CancelledError:
        raise
    except Exception:
        # HTTP exception strings may contain resumable credentials. Do not log them.
        logger.warning("YouTube upload interrupted id=%s attempt=%s", row["id"], row["attempts"])
        async with get_ai_conn() as conn:
            await conn.execute("""UPDATE studio_youtube_uploads SET status=$3,lease_until=NULL,
                error='Chưa đăng được YouTube. Kiểm tra hạn video, quyền khóa học, kết nối và quota kênh chung.',updated_at=now()
                WHERE id=$1 AND lease_token=$2 AND lease_until>now()""", row["id"], token, "queued" if row["attempts"] < 3 else "failed")
        await asyncio.sleep(2)
    return True


async def serve_uploads():
    while True:
        try:
            if await run_next_upload():
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("YouTube queue unavailable")
        await asyncio.sleep(3)
