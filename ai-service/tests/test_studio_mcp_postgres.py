"""Opt-in disposable PostgreSQL: actual migrations, receipts, jobs and expiry."""
import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import asyncpg
import pytest


def test_studio_mcp_postgres(monkeypatch):
    endpoint = os.getenv("BDC_STUDIO_SQL_TEST_URL")
    if not endpoint:
        pytest.skip("requires disposable PostgreSQL")
    if os.getenv("BDC_STUDIO_SQL_ISOLATED") != "1":
        # Older agent tests replace asyncpg in sys.modules during collection.
        # A clean process ensures this integration test always uses the real driver.
        result = subprocess.run([sys.executable,"-m","pytest",__file__,"-q"],
            env={**os.environ,"BDC_STUDIO_SQL_ISOLATED":"1"},capture_output=True,text=True,timeout=60)
        assert result.returncode == 0, result.stdout+result.stderr
        return
    async def run():
        from mcp import authoring
        from app.services.studio import studio_service as studio, jobs, temporary_media as media
        conn = await asyncpg.connect(endpoint)
        schema = "studio_test_" + uuid4().hex
        await conn.execute(f"CREATE SCHEMA {schema}; SET search_path TO {schema}")
        @asynccontextmanager
        async def connection():
            yield conn
        for module in (authoring, studio, jobs, media):
            monkeypatch.setattr(module,"get_ai_conn",connection)
        monkeypatch.setattr(authoring,"user_can_read_course",AsyncMock(return_value=True))
        directory = Path(__file__).parent.parent/"migrations"
        try:
            for name in ("V013__studio_projects.sql","V020__studio_worker_jobs.sql","V022__studio_temporary_media_and_youtube.sql"):
                await conn.execute((directory/name).read_text())
            # Isolate the personal-card DDL from its unrelated legacy data migration.
            await conn.execute((directory/"V016__personal_flashcard_library.sql").read_text().split("-- Preserve existing")[0])
            await conn.execute("ALTER TABLE personal_flashcard_decks ADD COLUMN course_id BIGINT")
            await conn.execute((directory/"V021__speech_jobs.sql").read_text())
            create = {"course_id":8,"action":"create","request_id":str(uuid4()),"confirmed":True,"data":{"kind":"video","title":"Matrix"}}
            async def invoke(name, payload):
                result = await authoring.call(name,payload,10)
                assert result.status == "success", result
                return result.data
            first = await invoke("mcp_studio_write",create)
            assert await invoke("mcp_studio_write",create) == first
            assert await conn.fetchval("SELECT count(*) FROM studio_projects") == 1
            project_id = first["project_id"]
            async def write(action,data):
                return await invoke("mcp_studio_write",{"course_id":8,"project_id":project_id,"action":action,"confirmed":True,"data":data})
            await write("add_source",{"title":"Approved excerpt","text":"Matrix multiplication computes dot products."})
            await write("outline",{"plan":{"title":"Matrix","narrative":{"learner_goal":"Understand dot products","concept_dependencies":["row","column"]},"sections":[{"title":"Dot product","source_refs":["S1"]}]}})
            await write("scene",{"index":0,"scene":{"title":"Dot product","learning_goal":"Understand one output cell","source_refs":["S1"],"narration":"Một hàng kết hợp với một cột.","animation_steps":["highlight_row","highlight_column","multiply","reduce"],"visual_type":"matrix_dot_product"}})
            queued = await write("render",{})
            assert (await write("render",{}))["job_id"] == queued["job_id"]
            assert await conn.fetchval("SELECT count(*) FROM studio_jobs") == 1
            assert (await studio.studio_service.get_project(project_id,10))["status"] == "generating"
            forbidden = await authoring.call("mcp_studio_read",{"course_id":9,"project_id":project_id,"action":"get"},10)
            assert forbidden.status == "error"

            deck_request = {"course_id":8,"action":"create_deck","request_id":str(uuid4()),"confirmed":True,"data":{"name":"HPC"}}
            deck = await invoke("mcp_flashcards_write",deck_request)
            assert await invoke("mcp_flashcards_write",deck_request) == deck
            save = {"course_id":8,"action":"save_cards","request_id":str(uuid4()),"confirmed":True,"data":{"deck_id":deck["id"],"cards":[{"front_text":"OpenMP?","back_text":"Shared memory","accepted_answers":["shared-memory"]}]}}
            cards = await invoke("mcp_flashcards_write",save)
            assert await invoke("mcp_flashcards_write",save) == cards
            assert await conn.fetchval("SELECT count(*) FROM personal_flashcards") == 1
            review = {"course_id":8,"action":"review","confirmed":True,"data":{"answer":{"card_id":cards["cards"][0]["id"],"revision":1,"review_id":str(uuid4()),"answer":"shared-memory"}}}
            assert (await invoke("mcp_flashcards_write",review))["correct"]
            assert (await invoke("mcp_flashcards_write",review))["correct"]
            assert await conn.fetchval("SELECT count(*) FROM personal_flashcard_reviews") == 1

            storage = MagicMock()
            monkeypatch.setattr(media,"_private_client",lambda:storage)
            monkeypatch.setattr(media,"_client",lambda:storage)
            monkeypatch.setattr(media,"bucket_name",lambda:"private-test")
            project = await studio.studio_service.get_project(project_id,10)
            generation = queued["job_id"]
            video = await media.store(project,generation,"video.mp4",b"video","video/mp4")
            source = await media.store(project,generation,"video.html",b"html","text/html",persistent=True)
            await media.activate(project_id,generation)
            upload_id = uuid4()
            await conn.execute("""INSERT INTO studio_youtube_uploads
                (id,asset_id,owner_id,channel_id,title,privacy,made_for_kids)
                VALUES($1,$2,10,'shared','Matrix','unlisted',false)""",upload_id,UUID(video["asset_id"]))
            snapshot = await invoke("mcp_studio_read",{"course_id":8,"project_id":project_id,"action":"get"})
            assert snapshot["youtube_uploads"][0]["id"] == upload_id
            assert "text" not in snapshot["sources"][0]
            assert await conn.fetchval("SELECT extract(epoch from expires_at-ready_at) FROM studio_temporary_media WHERE id=$1",UUID(video["asset_id"])) == 600
            assert await conn.fetchval("SELECT expires_at FROM studio_temporary_media WHERE id=$1",UUID(source["asset_id"])) is None
            await conn.execute("UPDATE studio_temporary_media SET expires_at=now()-interval '1 second' WHERE id=$1",UUID(video["asset_id"]))
            with pytest.raises(ValueError): await media.owned_asset(video["asset_id"],10)
            assert await media.cleanup_once() == 1
            storage.remove_object.assert_called_once()
            assert (await media.owned_asset(source["asset_id"],10))["ready_at"]
            # A deleted temporary MP4 does not break the durable YouTube lesson.
            from mcp import resources
            from app.services.studio import youtube_publishing
            from app.agents.tools.teacher import mcp_create_lesson
            monkeypatch.setattr(authoring,"user_owns_course",AsyncMock(return_value=True))
            sections = [{"id":20,"contents":[]}]
            monkeypatch.setattr(resources,"_fetch_course_contents",AsyncMock(return_value=sections))
            async def create_content(**kwargs):
                content = {"id":51,**kwargs["payload"]}
                sections[0]["contents"].append(content)
                return content
            create_content = AsyncMock(side_effect=create_content)
            monkeypatch.setattr(mcp_create_lesson,"_create_lesson_content",create_content)
            monkeypatch.setattr(youtube_publishing,"get_upload",AsyncMock(return_value={"asset_id":video["asset_id"],"status":"ready","processing_status":"processed", "actual_privacy":"unlisted","url":"https://www.youtube.com/watch?v=abcdefghijk","video_id":"abcdefghijk"}))
            await conn.execute("UPDATE studio_projects SET status='ready' WHERE id=$1::uuid",project_id)
            published = await write("publish",{"section_id":20,"upload_id":str(uuid4())})
            assert (await write("publish",{"section_id":20,"upload_id":str(uuid4())}))["content"]["id"] == published["content"]["id"]
            create_content.assert_awaited_once()
            assert published["content"]["metadata"]["video_type"] == "youtube"
            assert published["content"]["metadata"]["studio_generation"] == generation
            await conn.execute("UPDATE studio_projects SET current_job_id=$2 WHERE id=$1::uuid",project_id,uuid4())
            stale = await authoring.call("mcp_studio_write",{"course_id":8,"project_id":project_id,"action":"publish","confirmed":True,"data":{"section_id":20,"upload_id":str(uuid4())}},10)
            assert stale.status == "error"
            create_content.assert_awaited_once()
        finally:
            await conn.execute(f"DROP SCHEMA {schema} CASCADE")
            await conn.close()
    asyncio.run(run())
