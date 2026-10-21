"""Own-model Studio and private flashcard tools. No BDC text-model calls.

Small requests, source pagination and one-scene edits are deliberate: clients
with limited context never have to send an entire course/storyboard at once.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.agents.tools.base_tool import ToolResult
from app.core.database import get_ai_conn
from app.services.studio.plan_schema import StudioPlan, PlanSection
from app.services.studio.studio_service import studio_service
from mcp.course_access import user_can_read_course, user_owns_course


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(gt=0)
    action: str
    project_id: UUID | None = None
    request_id: UUID | None = None
    data: dict = Field(default_factory=dict)


class StudioRead(Request):
    action: Literal["list", "get", "source", "download", "youtube_status", "upload_status"]


class StudioWrite(Request):
    action: Literal["create", "add_source", "outline", "scene", "render", "youtube_upload", "publish"]
    confirmed: StrictBool


class FlashcardRead(Request):
    action: Literal["list", "speech_status"]


class FlashcardWrite(Request):
    action: Literal["create_deck", "save_cards", "review", "speak"]
    confirmed: StrictBool


MODELS = {"mcp_studio_read": StudioRead, "mcp_studio_write": StudioWrite,
          "mcp_flashcards_read": FlashcardRead, "mcp_flashcards_write": FlashcardWrite}
DESCRIPTIONS = {
    "mcp_studio_read": "Read your course-scoped Studio projects, paged source evidence, a single scene, temporary download links or SHARED YouTube channel/upload status. Read bdc://studio/guide and bdc://studio/schema first. No text-model calls.",
    "mcp_studio_write": "Use YOUR model to author Studio content. Create a private course project, add grounded evidence, save a compact narrative outline, edit ONE scene, enqueue HTML→PDF/MP4 rendering, upload to the SHARED channel or publish a durable lesson. Never calls BDC's text LLM. confirmed=true means the user approved this operation. Rendering uses paid managed TTS. MP4/audio/ZIP expire ten minutes after ready. YouTube upload and course publish require course owner/co-teacher. See bdc://studio/guide.",
    "mcp_flashcards_read": "Read your own course flashcard decks/cards in small pages or check neural speech job status. Never reads another user's library. Uses no text LLM.",
    "mcp_flashcards_write": "Persist flashcards authored by YOUR model, record a review using exact matching or your verdict, or enqueue shared Gateway neural speech. No BDC text-model calls. confirmed=true records user approval; request_id UUID makes deck/card writes retry-safe. Read bdc://flashcards/guide first.",
}


def descriptors() -> list[dict]:
    return [{"name": name, "description": DESCRIPTIONS[name], "inputSchema": model.model_json_schema(),
             "annotations": {"readOnlyHint": name.endswith("_read"), "destructiveHint": False,
                             "idempotentHint": name.endswith("_read"), "openWorldHint": name == "mcp_studio_write"}}
            for name, model in MODELS.items()]


def bounded_int(data: dict, key: str, default: int, lower: int, upper: int) -> int:
    value = data.get(key, default)
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{key} must be between {lower} and {upper}")
    return value


async def scoped_project(request: Request, owner_id: int) -> dict:
    if not request.project_id:
        raise ValueError("project_id required")
    project = await studio_service.get_project(str(request.project_id), owner_id)
    if not project or project["course_id"] != request.course_id:
        raise LookupError("Project not found in this course")
    return project


def project_summary(project: dict, index: int = 0) -> dict:
    plan = project.get("plan") or {}
    sections = plan.get("sections") or []
    sources = project.get("context_pack") or []
    return {**{key: project.get(key) for key in ("id", "course_id", "kind", "title", "status", "error_detail", "current_job_id", "updated_at", "settings", "artifacts")},
            "sources": [{"ref": f"S{i}", "title": str(s.get("title") or "")[:80], "chars": len(s.get("text", "")), "content_id": s.get("content_id") or s.get("ref")} for i, s in enumerate(sources[:20], 1)],
            "source_count": len(sources),
            "narrative": plan.get("narrative"), "learning_objectives": plan.get("learning_objectives", []),
            "sections": [{"index": i, "title": s.get("title")} for i, s in enumerate(sections)],
            "scene_index": index, "scene": sections[index] if index < len(sections) else None,
            "workspace_path": f"/lms/teacher/courses/{project['course_id']}/studio?project={project['id']}"}


async def _idempotent(conn, owner_id: int, request: Request, operation: str, perform):
    if not request.request_id:
        raise ValueError("request_id UUID required for retry-safe creation/save")
    digest = hashlib.sha256(json.dumps(request.model_dump(mode="json", exclude={"confirmed"}), sort_keys=True).encode()).hexdigest()
    await conn.execute("SELECT pg_advisory_xact_lock($1)", owner_id)
    previous = await conn.fetchrow("SELECT * FROM mcp_authoring_requests WHERE owner_id=$1 AND request_id=$2", owner_id, request.request_id)
    if previous:
        if previous["operation"] != operation or previous["input_hash"] != digest:
            raise ValueError("request_id was used for different content")
        return json.loads(previous["result"]) if isinstance(previous["result"], str) else previous["result"]
    result = await perform()
    await conn.execute("INSERT INTO mcp_authoring_requests(owner_id,request_id,operation,input_hash,result) VALUES($1,$2,$3,$4,$5::jsonb)",
                       owner_id, request.request_id, operation, digest, json.dumps(result, default=str))
    return result


async def call(name: str, arguments: dict, owner_id: int) -> ToolResult:
    try:
        request = MODELS[name].model_validate(arguments)
        if len(json.dumps(request.data, ensure_ascii=False)) > 48_000:
            raise ValueError("Request exceeds 48,000 characters; send one scene or up to 20 cards")
        if not await user_can_read_course(owner_id, request.course_id):
            raise PermissionError("Course is not accessible to this account")
        if name.endswith("_write") and not request.confirmed:
            raise ValueError("Get explicit user approval for this operation before confirmed=true")
        if name == "mcp_studio_read":
            result = await studio_read(request, owner_id)
        elif name == "mcp_studio_write":
            result = await studio_write(request, owner_id)
        else:
            result = await flashcards(request, owner_id)
        return ToolResult(status="success", data=result)
    except PermissionError as exc:
        return ToolResult(status="error", data={"error": "forbidden"}, message=str(exc))
    except (ValueError, LookupError, TypeError, KeyError) as exc:
        return ToolResult(status="error", data={"error": "invalid_authoring_request"}, message=str(exc)[:2000])


async def studio_read(request: StudioRead, owner_id: int):
    data = request.data
    if request.action == "youtube_status":
        from app.services.studio.youtube_publishing import bridge
        return await bridge("status")
    if request.action == "upload_status":
        from app.services.studio.youtube_publishing import get_upload
        result = await get_upload(str(UUID(data["upload_id"])), owner_id, refresh=True)
        async with get_ai_conn() as conn:
            course_id = await conn.fetchval("SELECT course_id FROM studio_temporary_media WHERE id=$1", UUID(result["asset_id"]))
        if course_id != request.course_id:
            raise LookupError("Upload not found in this course")
        return result
    if request.action == "list":
        offset = bounded_int(data, "offset", 0, 0, 100000)
        async with get_ai_conn() as conn:
            rows = await conn.fetch("SELECT id,title,kind,status,updated_at FROM studio_projects WHERE created_by=$1 AND course_id=$2 ORDER BY updated_at DESC,id LIMIT 21 OFFSET $3", owner_id, request.course_id, offset)
        return {"projects": [dict(row) for row in rows[:20]], "next_offset": offset+20 if len(rows)>20 else None}
    project = await scoped_project(request, owner_id)
    if request.action == "get":
        result = project_summary(project, bounded_int(data, "index", 0, 0, 29))
        if project["kind"] == "video":
            async with get_ai_conn() as conn:
                uploads = await conn.fetch("""SELECT u.id,u.asset_id,u.status,u.title,u.actual_privacy,u.processing_status,u.video_id,u.error
                    FROM studio_youtube_uploads u JOIN studio_temporary_media m ON m.id=u.asset_id
                    WHERE m.project_id=$1::uuid AND u.owner_id=$2 AND m.generation=$3
                    ORDER BY u.created_at DESC LIMIT 10""", project["id"], owner_id, str(project.get("current_job_id") or "draft"))
            result["youtube_uploads"] = [dict(row) for row in uploads]
        return result
    if request.action == "source":
        index = bounded_int(data, "source_index", 0, 0, 99)
        sources = project.get("context_pack") or []
        if index >= len(sources):
            raise ValueError("source_index out of range")
        text = sources[index].get("text", "")
        offset = bounded_int(data, "offset", 0, 0, 2000000)
        limit = bounded_int(data, "limit", 4000, 1, 6000)
        return {"ref": f"S{index+1}", "text": text[offset:offset+limit], "total_chars": len(text),
                "next_offset": offset+limit if offset+limit < len(text) else None}
    if request.action == "download":
        from app.services.studio.temporary_media import owned_asset, capability
        asset = await owned_asset(str(UUID(data["asset_id"])), owner_id)
        if str(asset["project_id"]) != project["id"]:
            raise LookupError("Media not in this project")
        expiry = min(asset["expires_at"], datetime.now(timezone.utc)+timedelta(seconds=600)) if asset["expires_at"] else datetime.now(timezone.utc)+timedelta(seconds=600)
        until = int(expiry.timestamp())
        return {"download_path": f"/mcp/media/{asset['id']}?token={capability(asset, until)}&until={until}", "expires_at": expiry,
                "notice": "Use this path on the MCP server origin. Anyone with this link can download until expiry; keep it private."}


async def studio_write(request: StudioWrite, owner_id: int):
    data = request.data
    if request.action == "create":
        kind = data.get("kind", "slides")
        if kind not in {"slides", "document", "report", "video"}:
            raise ValueError("Invalid project kind")
        title = str(data.get("title", "Bài học"))
        if not 1 <= len(title) <= 180:
            raise ValueError("Title must have 1–180 characters")
        settings = {"theme": data.get("theme", "google"), "aspect_ratio": data.get("aspect_ratio", "16:9"),
                    "language": data.get("language", "vi"), "authoring_mode": "external_model"}
        if settings["aspect_ratio"] not in {"16:9", "9:16"} or settings["theme"] not in {"google", "apple", "microsoft", "nvidia"} or settings["language"] not in {"vi", "en"}:
            raise ValueError("Invalid theme, language or aspect ratio")
        async with get_ai_conn() as conn, conn.transaction():
            async def create():
                project_id = str(uuid4())
                await conn.execute("INSERT INTO studio_projects(id,course_id,created_by,kind,title,settings) VALUES($1::uuid,$2,$3,$4,$5,$6::jsonb)", project_id, request.course_id, owner_id, kind, title, json.dumps(settings))
                return {"project_id": project_id, "course_id": request.course_id, "status": "collecting"}
            return await _idempotent(conn, owner_id, request, "studio.create", create)
    project = await scoped_project(request, owner_id)
    project_id = project["id"]
    if request.action == "add_source":
        text = str(data.get("text", ""))
        title = str(data.get("title", "Nguồn được người dùng cung cấp"))[:200]
        content_id = data.get("content_id")
        if content_id:
            from mcp.resources import _read_content_resource
            page = json.loads(await _read_content_resource(request.course_id, bounded_int(data, "content_id", 0, 1, 2**53), owner_id,
                              bounded_int(data, "offset", 0, 0, 2000000), 12000))
            if page.get("error") or not page.get("text"):
                raise ValueError("No readable evidence available; index source first")
            text = page["text"]; title = page["content"].get("title", title)
        if not text.strip() or len(text) > 12000:
            raise ValueError("Source must contain 1–12,000 characters. Add canonical content_id or an approved excerpt.")
        result = await studio_service.add_context_source(project_id, owner_id, {"type": "text", "title": title, "text": text, "ref": content_id})
        return {**result, "next": "get source refs, then save narrative outline"}
    if request.action == "outline":
        # Validate; do not silently coerce/drop external-client content.
        plan = StudioPlan.model_validate(data["plan"])
        if not 1 <= len(plan.sections) <= 30 or not plan.narrative.learner_goal or not plan.narrative.concept_dependencies:
            raise ValueError("Outline needs 1–30 sections and a teaching narrative")
        if any(s.narration or s.slide_bullets or s.visual_spec.nodes for s in plan.sections):
            raise ValueError("Send a compact outline first, then one detailed scene per call")
        return {"project": project_summary((await studio_service.update_plan(project_id, owner_id, plan.model_dump()))["project"])}
    if request.action == "scene":
        index = bounded_int(data, "index", 0, 0, 29)
        section = PlanSection.model_validate(data["scene"])
        if len(section.title)>110 or len(section.narration)>2400 or len(section.slide_bullets)>3 or len(section.key_points)>3:
            raise ValueError("One scene: short title, <=3 points, <=2400 narration characters")
        updated = await studio_service.update_section(project_id, owner_id, index, section.model_dump())
        return project_summary(updated, index)
    if request.action == "render":
        from app.services.studio.storyboard import compile_storyboard
        plan = StudioPlan.model_validate(project["plan"])
        compile_storyboard(plan, project["settings"], video=project["kind"] == "video")
        return await studio_service.start_generate(project_id, owner_id)
    if request.action == "youtube_upload":
        from app.services.studio.youtube_publishing import request_upload
        if not isinstance(data.get("made_for_kids"), bool) or not isinstance(data.get("contains_synthetic_media"), bool):
            raise ValueError("Confirm made_for_kids and contains_synthetic_media explicitly")
        asset_id = str(UUID(data["asset_id"]))
        from app.services.studio.temporary_media import owned_asset
        asset = await owned_asset(asset_id, owner_id)
        if str(asset["project_id"]) != project_id:
            raise LookupError("Media not in project")
        return await request_upload(owner_id, asset_id, str(data["channel_id"]), str(data["title"]), str(data.get("description", "")), str(data["privacy"]), data["made_for_kids"], data["contains_synthetic_media"])
    if request.action == "publish":
        return await publish_project(project, owner_id, data)


async def publish_project(project: dict, owner_id: int, data: dict):
    if not await user_owns_course(owner_id, project["course_id"]):
        raise PermissionError("Only course owners/co-teachers can publish lessons")
    # Resolve section membership through LMS, never trust a foreign section_id.
    from mcp.resources import _fetch_course_contents
    sections = await _fetch_course_contents(project["course_id"], owner_id)
    section_id = bounded_int(data, "section_id", 0, 1, 2**53)
    if not any(section["id"] == section_id for section in sections):
        raise ValueError("section_id is not in this course")
    from app.agents.tools.teacher.mcp_create_lesson import _create_lesson_content
    from app.services.studio.doc_renderer import render_plan_to_markdown
    plan = StudioPlan.model_validate(project["plan"])
    if project["kind"] == "video":
        from app.services.studio.youtube_publishing import get_upload
        upload = await get_upload(str(UUID(data["upload_id"])), owner_id, refresh=True)
        async with get_ai_conn() as conn:
            asset = await conn.fetchrow("SELECT project_id,generation FROM studio_temporary_media WHERE id=$1", UUID(upload["asset_id"]))
        if not asset or str(asset["project_id"]) != project["id"] or project.get("status") != "ready" or asset["generation"] != str(project.get("current_job_id") or "draft") or upload["status"] != "ready" or upload["processing_status"] != "processed" or upload["actual_privacy"] not in {"unlisted", "public"}:
            raise ValueError("Wait for a processed shared-channel video with actual visibility unlisted/public")
        payload = {"type": "VIDEO", "metadata": {"video_url": upload["url"], "video_type": "youtube", "file_path": f"https://www.youtube.com/embed/{upload['video_id']}"}}
    elif project["kind"] == "slides":
        pdf = next((a for a in project["artifacts"] if a["type"] == "pdf"), None)
        if not pdf or project["status"] != "ready":
            raise ValueError("Render PDF before publishing")
        if pdf.get("asset_id"):
            from app.services.studio.temporary_media import read_checkpoint
            from app.services.minio_storage import upload_bytes
            document = await read_checkpoint(pdf["asset_id"], owner_id)
            key = f"document/studio/{project['id']}/{pdf['asset_id']}.pdf"
            if not document or not await upload_bytes(key, document, "application/pdf"):
                raise ValueError("Could not attach the PDF to the course")
        else:
            key = pdf["url"].removeprefix("/files/")
        payload = {"type": "DOCUMENT", "metadata": {"file_path": key, "file_name": f"{project['title']}.pdf"}}
    else:
        payload = {"type": "TEXT", "metadata": {"content": render_plan_to_markdown(plan)}}
    payload.update(title=plan.title or project["title"], description=plan.summary[:2000])
    payload["metadata"]["studio_project_id"] = project["id"]
    generation = str(project.get("current_job_id") or hashlib.sha256(plan.model_dump_json().encode()).hexdigest()[:20])
    payload["metadata"]["studio_generation"] = generation
    # LMS has no cross-service idempotency key. Serialize retries per project,
    # then reconcile metadata after a lost HTTP response before creating again.
    async with get_ai_conn() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", f"studio-publish:{project['id']}:{section_id}")
            current = await conn.fetchrow("SELECT plan,current_job_id FROM studio_projects WHERE id=$1::uuid AND created_by=$2 FOR UPDATE", project["id"], owner_id)
            current_plan = json.loads(current["plan"]) if current and isinstance(current["plan"],str) else current["plan"] if current else None
            if not current or current_plan != project["plan"] or str(current["current_job_id"] or "") != str(project.get("current_job_id") or ""):
                raise ValueError("Project changed during publication; reload and review the current version")
            sections = await _fetch_course_contents(project["course_id"], owner_id)
            previous = next((c for s in sections if s["id"] == section_id for c in s["contents"] if (c.get("metadata") or {}).get("studio_project_id") == project["id"] and (c.get("metadata") or {}).get("studio_generation") == generation), None)
            content = previous or await _create_lesson_content(section_id=section_id, user_id=owner_id, payload=payload, order_index=None, is_mandatory=False)
    return {"content": content, "state": "published" if content.get("is_published") else "draft", "notice": "Lesson attached to this course. Review unpublished drafts through the course editor."}


async def flashcards(request: Request, owner_id: int):
    from app.services.personal_flashcard_service import CardDraft, Answer, Verdict, owned_card, exact_match, record_answer, decode
    data = request.data
    if request.action == "speech_status":
        job_id = UUID(data["job_id"])
        async with get_ai_conn() as conn:
            row = await conn.fetchrow("""SELECT s.id,s.status,s.error FROM speech_jobs s
                JOIN personal_flashcards c ON c.id=s.card_id JOIN personal_flashcard_decks d ON d.id=c.deck_id
                WHERE s.id=$1 AND s.owner_id=$2 AND c.student_id=$2 AND d.student_id=$2 AND d.course_id=$3""", job_id, owner_id, request.course_id)
        if not row:
            raise LookupError("Speech job not found in this course")
        return {**dict(row), "audio_path": f"/mcp/flashcards/speech/{job_id}", "browser_audio_path": f"/api/ai/speech/jobs/{job_id}/audio"}
    if request.action == "speak":
        from app.services.speech_service import request_flashcard_speech
        side = data.get("side", "front")
        speed = data.get("speed", 0.97)
        if side not in {"front", "back"} or not isinstance(speed, (int,float)) or not 0.7<=speed<=1.2:
            raise ValueError("Invalid speech side/speed")
        return await request_flashcard_speech(owner_id, bounded_int(data,"card_id",0,1,2**53), request.course_id, side, speed)
    async with get_ai_conn() as conn, conn.transaction():
        if request.action == "list":
            offset = bounded_int(data,"offset",0,0,100000)
            limit = bounded_int(data,"limit",10,1,20)
            decks = await conn.fetch("SELECT id,name FROM personal_flashcard_decks WHERE student_id=$1 AND course_id=$2 ORDER BY id", owner_id, request.course_id)
            rows = await conn.fetch("""SELECT c.* FROM personal_flashcards c JOIN personal_flashcard_decks d ON d.id=c.deck_id
                WHERE c.student_id=$1 AND d.student_id=$1 AND d.course_id=$2 AND ($3::bigint IS NULL OR d.id=$3)
                AND ($4::boolean=false OR c.due_at<=now()) ORDER BY c.id LIMIT $5 OFFSET $6""", owner_id, request.course_id,
                data.get("deck_id"), bool(data.get("due_only", False)), limit+1, offset)
            page = []
            size = 0
            for row in rows[:limit]:
                card = decode(row)
                chars = len(json.dumps(card, default=str))
                if page and size+chars>12000:
                    break
                page.append(card); size += chars
            return {"decks": [dict(d) for d in decks[:100]], "cards": page, "next_offset": offset+len(page) if len(rows)>len(page) else None}
        if request.action == "review":
            answer = Answer.model_validate(data["answer"])
            card = await owned_card(conn, owner_id, request.course_id, answer.card_id, lock=True)
            matched = not answer.reveal and exact_match(card, answer.answer)
            verdict = Verdict(correct=matched, feedback="Chính xác!" if matched else "Chưa khớp đáp án.")
            if not answer.reveal and not matched and card["match_mode"] == "ai":
                verdict = Verdict.model_validate(data["verdict"])
            return await record_answer(conn, owner_id, request.course_id, card, answer, verdict)
        if request.action == "create_deck":
            name = str(data["name"]).strip()
            if not 1 <= len(name) <= 120:
                raise ValueError("Deck name: 1–120 characters")
            async def create():
                return dict(await conn.fetchrow("INSERT INTO personal_flashcard_decks(student_id,course_id,name) VALUES($1,$2,$3) RETURNING id,name", owner_id, request.course_id, name))
            return await _idempotent(conn, owner_id, request, "flashcards.create_deck", create)
        if request.action == "save_cards":
            items = data["cards"]
            if not isinstance(items, list) or not 1 <= len(items) <= 20:
                raise ValueError("Send 1–20 cards per call")
            cards = [CardDraft.model_validate(item) for item in items]
            deck_id = bounded_int(data,"deck_id",0,1,2**53)
            async def save():
                if not await conn.fetchval("SELECT id FROM personal_flashcard_decks WHERE id=$1 AND student_id=$2 AND course_id=$3 FOR UPDATE", deck_id, owner_id, request.course_id):
                    raise LookupError("Deck not found")
                saved = []
                for card in cards:
                    row = await conn.fetchrow("""INSERT INTO personal_flashcards(student_id,deck_id,front_text,back_text,accepted_answers,note,language,answer_language,match_mode,case_sensitive)
                        VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10) RETURNING id,revision""", owner_id, deck_id, card.front_text, card.back_text,
                        json.dumps(card.accepted_answers), card.note, card.language, card.answer_language, card.match_mode, card.case_sensitive)
                    saved.append(dict(row))
                return {"cards": saved}
            return await _idempotent(conn, owner_id, request, "flashcards.save_cards", save)
    raise ValueError("Unsupported operation")
