from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from mcp import authoring
from mcp.authoring_docs import read as read_guide
from mcp.tool_adapter import call_mcp_tool, get_mcp_tool_list
from app.services.studio import temporary_media as media, youtube_publishing as youtube


def connection(conn):
    @asynccontextmanager
    async def get():
        yield conn
    return get


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["mcp_studio_write", "mcp_flashcards_write"])
async def test_read_only_keys_cannot_start_paid_or_persistent_writes(name):
    with patch("mcp.auth.get_current_scopes", return_value=frozenset({"read"})), patch("mcp.authoring.call", new=AsyncMock()) as invoke:
        result = await call_mcp_tool(name, {"action": "render", "course_id": 8, "confirmed": True}, 10)
    assert result["isError"] and "write_scope_required" in result["content"][0]["text"]
    invoke.assert_not_awaited()


def test_discovery_classifies_new_tools_and_publishes_contracts():
    tools = {t["name"]: t for t in get_mcp_tool_list()}
    for name in authoring.MODELS:
        assert tools[name]["annotations"]["readOnlyHint"] == name.endswith("_read")
    assert "600 seconds" in read_guide("bdc://studio/guide")
    schema = json.loads(read_guide("bdc://studio/schema"))
    assert "visual_spec" in schema["scene"]["properties"]


def test_small_context_profiles_restrict_tools_and_resource_pages():
    from mcp.tool_adapter import current_profile
    from mcp.resources import _parse_char_limit
    token = current_profile.set("flashcards")
    try:
        assert {tool["name"] for tool in get_mcp_tool_list()} == {"list_accessible_courses", "mcp_flashcards_read", "mcp_flashcards_write"}
        assert _parse_char_limit({}) == 4000
        with pytest.raises(ValueError): _parse_char_limit({"limit_chars": ["200000"]})
    finally:
        current_profile.reset(token)


@pytest.mark.asyncio
async def test_confirmation_and_access_fail_before_any_write():
    with patch.object(authoring, "user_can_read_course", new=AsyncMock(return_value=True)), patch.object(authoring, "studio_write", new=AsyncMock()) as write:
        result = await authoring.call("mcp_studio_write", {"course_id": 8, "action": "create", "confirmed": False}, 10)
        assert result.status == "error"
        write.assert_not_awaited()
    with patch.object(authoring, "user_can_read_course", new=AsyncMock(return_value=False)):
        result = await authoring.call("mcp_flashcards_read", {"course_id": 8, "action": "list"}, 10)
        assert result.data["error"] == "forbidden"


@pytest.mark.asyncio
async def test_one_scene_edit_never_calls_a_text_model():
    project_id = str(uuid4())
    project = {"id": project_id, "course_id": 8, "plan": {"sections": [{"title": "A"}]}}
    scene = {"title": "A", "source_refs": ["S1"], "narration": "Một khái niệm.", "learning_goal": "Hiểu A", "animation_steps": ["reveal"]}
    with patch.object(authoring, "user_can_read_course", new=AsyncMock(return_value=True)), \
         patch.object(authoring, "scoped_project", new=AsyncMock(return_value=project)), \
         patch.object(authoring.studio_service, "update_section", new=AsyncMock(return_value=project)) as update, \
         patch("app.core.llm_gateway.get_gateway", side_effect=AssertionError("No BDC LLM")):
        result = await authoring.call("mcp_studio_write", {"course_id": 8, "project_id": project_id,
            "action": "scene", "confirmed": True, "data": {"index": 0, "scene": scene}}, 10)
    assert result.status == "success"
    update.assert_awaited_once()


@pytest.mark.asyncio
async def test_project_cannot_be_rebound_to_another_course():
    request = authoring.StudioRead(course_id=99, project_id=uuid4(), action="get")
    with patch.object(authoring.studio_service, "get_project", new=AsyncMock(return_value={"course_id": 8})):
        with pytest.raises(LookupError):
            await authoring.scoped_project(request, 10)


@pytest.mark.asyncio
async def test_idempotency_does_not_repeat_paid_or_persistent_effects():
    request = authoring.FlashcardWrite(course_id=8, action="create_deck", confirmed=True, request_id=uuid4(), data={"name": "HPC"})
    conn = AsyncMock(); conn.fetchrow.return_value = None
    operation = AsyncMock(return_value={"id": 12})
    result = await authoring._idempotent(conn, 10, request, "deck", operation)
    _, _, _, _, digest, serialized = conn.execute.call_args.args
    conn.fetchrow.return_value = {"operation": "deck", "input_hash": digest, "result": serialized}
    assert await authoring._idempotent(conn, 10, request, "deck", operation) == result
    operation.assert_awaited_once()
    changed = request.model_copy(update={"data": {"name": "Different"}})
    with pytest.raises(ValueError, match="different content"):
        await authoring._idempotent(conn, 10, changed, "deck", operation)


def test_private_bucket_cannot_be_the_public_file_bucket():
    with patch.object(media, "get_settings", return_value=SimpleNamespace(minio_bucket="files", studio_temporary_bucket="files")):
        with pytest.raises(ValueError, match="separate private bucket"):
            media.bucket_name()


@pytest.mark.parametrize("policy,version", [(True,None),(False,"Enabled"),(False,"Suspended")])
def test_public_or_versioned_bucket_fails_closed(policy,version):
    from minio.error import S3Error
    storage = MagicMock(); storage.bucket_exists.return_value = True
    if not policy:
        storage.get_bucket_policy.side_effect = S3Error("NoSuchBucketPolicy","none","bucket","request","host",None)
    storage.get_bucket_versioning.return_value.status = version
    with patch.object(media,"_client",return_value=storage), patch.object(media,"bucket_name",return_value="private"):
        with pytest.raises(ValueError): media._private_client()
    storage.put_object.assert_not_called()


@pytest.mark.asyncio
async def test_revoked_course_access_blocks_browser_render_before_enqueue():
    from app.api.endpoints import studio
    from app.core.config import get_settings
    with patch.object(studio.studio_service,"get_project",new=AsyncMock(return_value={"course_id":8})), \
         patch("mcp.course_access.user_can_read_course",new=AsyncMock(return_value=False)), \
         patch.object(studio.studio_service,"start_generate",new=AsyncMock()) as enqueue:
        with pytest.raises(HTTPException) as error:
            await studio.generate(str(uuid4()),studio.SimpleActionRequest(user_id=10),get_settings().ai_service_secret)
    assert error.value.status_code == 403
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_disconnect_fences_queued_and_running_uploads():
    from app.api.endpoints import studio
    from app.core.config import get_settings
    conn = AsyncMock(); conn.transaction = MagicMock(return_value=AsyncMock())
    with patch("app.core.database.get_ai_conn",connection(conn)):
        assert (await studio.delete_shared_connection(get_settings().ai_service_secret))["deleted"]
    assert conn.execute.await_count == 2
    assert "lease_until=NULL" in conn.execute.call_args.args[0]
    assert "('queued','running')" in conn.execute.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("expired,deleted,ready", [(True,False,True),(False,True,True),(False,False,False)])
async def test_expired_deleted_and_staging_assets_are_never_downloadable(expired, deleted, ready):
    row = {"id": uuid4(), "owner_id": 10, "deleted_at": datetime.now(timezone.utc) if deleted else None,
           "ready_at": datetime.now(timezone.utc) if ready else None,
           "expires_at": datetime.now(timezone.utc)+timedelta(seconds=-1 if expired else 20)}
    conn = AsyncMock(); conn.fetchrow.return_value = row
    with patch.object(media, "get_ai_conn", connection(conn)), patch.object(media, "_client") as storage:
        with pytest.raises(HTTPException) as error:
            await media.media_response(str(row["id"]), owner_id=10)
    assert error.value.status_code == 410
    storage.assert_not_called()


@pytest.mark.asyncio
async def test_other_owner_cannot_access_or_sign_an_asset():
    conn = AsyncMock(); conn.fetchrow.return_value = {"owner_id": 99}
    with patch.object(media, "get_ai_conn", connection(conn)):
        with pytest.raises(LookupError): await media.owned_asset(str(uuid4()), 10)


@pytest.mark.asyncio
async def test_range_download_and_capability_validation():
    asset = {"id": uuid4(), "owner_id": 10, "size_bytes": 8, "media_type": "video/mp4", "object_key": "video.mp4", "storage_bucket": "private",
             "expires_at": datetime.now(timezone.utc)+timedelta(minutes=1)}
    storage = MagicMock(); storage.get_object.return_value.read.side_effect = [b"cdef", b""]
    with patch.object(media, "owned_asset", new=AsyncMock(return_value=asset)), \
         patch.object(media, "get_settings", return_value=SimpleNamespace(ai_service_secret="test")), \
         patch.object(media, "bucket_name", return_value="private"), patch.object(media, "_client", return_value=storage):
        with pytest.raises(HTTPException) as error:
            await media.media_response(str(asset["id"]), token="invalid")
        assert error.value.status_code == 403
        response = await media.media_response(str(asset["id"]), token=media.capability(asset), range_header="bytes=2-5")
        assert response.status_code == 206 and response.headers["content-range"] == "bytes 2-5/8"
        assert b"".join([chunk async for chunk in response.body_iterator]) == b"cdef"
        assert response.headers["cache-control"] == "private, no-store"
        storage.get_object.assert_called_once_with("private", "video.mp4", offset=2, length=4)
        storage.get_object.return_value.close.assert_called_once()


@pytest.mark.asyncio
async def test_failed_object_delete_is_retried_without_marking_deleted():
    conn = AsyncMock(); conn.fetch.return_value = [{"id": uuid4(), "object_key": "video.mp4", "storage_bucket": "private", "generation": "job"}]
    storage = MagicMock(); storage.remove_object.side_effect = RuntimeError("offline")
    with patch.object(media, "get_ai_conn", connection(conn)), patch.object(media, "_client", return_value=storage), patch.object(media, "bucket_name", return_value="private"):
        assert await media.cleanup_once() == 1
        conn.execute.assert_not_awaited()
        storage.remove_object.side_effect = None
        assert await media.cleanup_once() == 1
        assert "deleted_at=now()" in conn.execute.call_args.args[0]


@pytest.mark.asyncio
async def test_cleanup_manifest_is_saved_before_object_upload():
    conn = AsyncMock()
    storage = MagicMock()
    def put(*args, **kwargs):
        assert conn.execute.await_count == 1
        raise RuntimeError("upload interrupted")
    storage.put_object.side_effect = put
    project = {"id": str(uuid4()), "created_by": 10, "course_id": 8}
    with patch.object(media, "get_ai_conn", connection(conn)), patch.object(media, "_private_client", return_value=storage), patch.object(media, "bucket_name", return_value="private"):
        with pytest.raises(RuntimeError): await media.store(project, "job", "video.mp4", b"video", "video/mp4")
    assert "INSERT INTO studio_temporary_media" in conn.execute.call_args.args[0]


@pytest.mark.parametrize("url", ["http://www.googleapis.com/upload/youtube/v3/videos", "https://evil.test/upload/youtube/v3/videos", "https://www.googleapis.com@evil.test/upload/youtube/v3/videos", "https://www.googleapis.com/other"])
def test_upload_redirect_cannot_leak_tokens_or_access_internal_hosts(url):
    with pytest.raises(ValueError): youtube.validate_session_url(url)


@pytest.mark.asyncio
async def test_resume_finalized_session_recovers_video_without_reuploading():
    row = {"id": uuid4(), "owner_id": 10, "asset_id": uuid4(), "attempts": 2, "encrypted_session": "cipher", "channel_id": "shared"}
    conn = AsyncMock(); conn.fetchrow.return_value = row
    client = AsyncMock(); client.put.return_value = httpx.Response(200, json={"id": "abcdefghijk", "status": {"privacyStatus": "unlisted", "uploadStatus": "processed"}})
    with patch.object(youtube,"get_ai_conn",connection(conn)), patch.object(youtube,"owned_asset",new=AsyncMock(return_value={"course_id":8,"size_bytes":8})), \
         patch("mcp.course_access.user_owns_course",new=AsyncMock(return_value=True)), patch.object(youtube,"bridge",new=AsyncMock(return_value={"access_token":"secret"})), \
         patch.object(youtube,"decrypt",return_value="https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test"), \
         patch.object(youtube,"_lease",new=AsyncMock()), patch.object(youtube.httpx,"AsyncClient") as context:
        context.return_value.__aenter__.return_value = client
        assert await youtube.run_next_upload()
    client.post.assert_not_awaited()
    assert client.put.await_count == 1
    assert "video_id=$3" in conn.execute.call_args.args[0]
    assert conn.execute.call_args.args[3] == "abcdefghijk"


@pytest.mark.asyncio
async def test_students_cannot_publish_to_shared_channel():
    with patch.object(youtube,"owned_asset",new=AsyncMock(return_value={"media_type":"video/mp4","course_id":8})), \
         patch("mcp.course_access.user_owns_course",new=AsyncMock(return_value=False)), patch.object(youtube,"bridge",new=AsyncMock()) as bridge:
        with pytest.raises(PermissionError):
            await youtube.request_upload(10,str(uuid4()),"shared","Title","","unlisted",False,True)
    bridge.assert_not_awaited()


@pytest.mark.asyncio
async def test_course_video_never_publishes_an_expiring_mp4_or_unprocessed_link():
    project = {"id":str(uuid4()),"course_id":8,"kind":"video","plan":{"title":"Lesson","sections":[]}}
    conn = AsyncMock(); conn.fetchval.return_value = project["id"]
    with patch.object(authoring,"user_owns_course",new=AsyncMock(return_value=True)), \
         patch("mcp.resources._fetch_course_contents",new=AsyncMock(return_value=[{"id":20}])), \
         patch.object(authoring,"get_ai_conn",connection(conn)), \
         patch.object(youtube,"get_upload",new=AsyncMock(return_value={"asset_id":str(uuid4()),"status":"ready","processing_status":"uploaded","actual_privacy":"unlisted"})), \
         patch("app.agents.tools.teacher.mcp_create_lesson._create_lesson_content",new=AsyncMock()) as create:
        with pytest.raises(ValueError,match="processed"):
            await authoring.publish_project(project,10,{"section_id":20,"upload_id":str(uuid4())})
    create.assert_not_awaited()
