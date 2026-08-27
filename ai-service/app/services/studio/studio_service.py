"""
ai-service/app/services/studio/studio_service.py

Content Studio orchestration: project persistence (PG), context packing,
LLM plan generation through the model-agnostic gateway, and local rendering
to PPTX / Markdown artifacts uploaded to MinIO.

Generation runs as an asyncio background task guarded by a semaphore -
P0 keeps this in-process (single replica assumption documented); moving to
the Kafka worker pool is a drop-in swap of `start_generate`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.services.minio_storage import upload_bytes
from app.services.studio.doc_renderer import render_plan_to_markdown
from app.services.studio.plan_schema import StudioPlan, coerce_plan
from app.services.studio.pptx_renderer import render_plan_to_pptx_bytes

logger = logging.getLogger(__name__)
settings = get_settings()

_RENDER_SEMAPHORE = asyncio.Semaphore(2)
_running_tasks: dict[str, asyncio.Task] = {}

_MAX_SOURCES = 8
_MAX_SOURCE_CHARS = 6000

_PLAN_SYSTEM = (
    "You are an instructional designer for a university LMS. From the given "
    "SOURCE MATERIALS, produce a lecture plan as STRICT JSON matching:\n"
    '{"title": str, "language": "vi"|"en", "learning_objectives": [str],\n'
    ' "sections": [{"title": str, "key_points": [str], "slide_bullets": [str],\n'
    '               "narration": str, "visual_suggestion": str,\n'
    '               "duration_est_sec": int}],\n'
    ' "summary": str}\n'
    "Rules: slide_bullets are concise on-slide lines (<=12 words each); "
    "narration is the spoken script expanding the bullets (3-8 sentences); "
    "key_points are study-note phrasing; visual_suggestion describes one "
    "supporting figure/diagram. Order sections pedagogically. Write in the "
    "requested language. Output ONLY JSON."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_payload(payload: Any) -> str:
    return hashlib.md5(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


class StudioService:
    # ── Persistence ────────────────────────────────────────────────────────
    async def create_project(self, *, course_id: int, created_by: int,
                             kind: str, title: str,
                             settings_obj: dict) -> dict:
        pid = str(uuid.uuid4())
        allowed_kinds = ("slides", "document", "video")
        if kind not in allowed_kinds:
            raise ValueError(f"kind must be one of {allowed_kinds}")
        async with get_ai_conn() as conn:
            await conn.execute(
                """INSERT INTO studio_projects
                     (id, course_id, created_by, kind, title, settings)
                   VALUES ($1,$2,$3,$4,$5,$6::jsonb)""",
                pid, course_id, created_by, kind,
                title[:300] or "Bài giảng chưa đặt tên",
                json.dumps(settings_obj or {}, ensure_ascii=False),
            )
        return await self.get_project(pid, created_by)

    async def get_project(self, project_id: str, created_by: int) -> Optional[dict]:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM studio_projects WHERE id=$1::uuid AND created_by=$2",
                project_id, created_by,
            )
        if not row:
            return None
        d = dict(row)
        if d.get("id") is not None:
            d["id"] = str(d["id"])
        for k in ("context_pack", "plan", "settings", "artifacts", "section_hashes"):
            val = d.get(k)
            if isinstance(val, str):
                try:
                    d[k] = json.loads(val)
                except Exception:
                    pass
        return d

    async def _update(self, project_id: str, created_by: int, **fields) -> None:
        if not fields:
            return
        json_fields = {"context_pack", "plan", "settings", "artifacts", "section_hashes"}
        sets = []
        vals = []
        for i, (k, v) in enumerate(fields.items()):
            if k in json_fields:
                sets.append(f"{k} = ${i+3}::jsonb")
                vals.append(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            else:
                sets.append(f"{k} = ${i+3}")
                vals.append(v)
        async with get_ai_conn() as conn:
            await conn.execute(
                f"""UPDATE studio_projects SET {", ".join(sets)}, updated_at=NOW()
                    WHERE id=$1::uuid AND created_by=$2""",
                project_id, created_by, *vals,
            )

    # ── Context collection ────────────────────────────────────────────────
    async def add_context_source(self, project_id: str, created_by: int,
                                 source: dict) -> dict:
        project = await self.get_project(project_id, created_by)
        if not project:
            raise ValueError("project not found")

        stype = source.get("type")
        text = ""
        title = str(source.get("title") or "")
        ref = source.get("ref")

        if stype == "node":
            from app.services.rag_service import rag_service
            chunks = await rag_service.search_hierarchical(
                query=title, course_id=project["course_id"],
                node_id=int(ref) if ref else None, top_k=4,
                expansion_enabled=False, max_expansion_level="content",
            )
            text = "\n---\n".join(c.chunk_text for c in chunks)[:_MAX_SOURCE_CHARS]
            if not text:
                raise ValueError("Node chưa có nội dung được index.")
        elif stype == "text":
            text = str(source.get("text") or "")[:_MAX_SOURCE_CHARS]
        elif stype == "document_url":
            # Already-ingested material: pull its markdown chunks by content.
            from app.services.rag_service import rag_service
            chunks = await rag_service.search_multilingual(
                query=title or "nội dung", course_id=project["course_id"],
                content_id=int(ref) if ref else None, top_k=6,
                min_similarity=0.1,
            )
            text = "\n---\n".join(c.chunk_text for c in chunks)[:_MAX_SOURCE_CHARS]
            if not text:
                raise ValueError("Tài liệu chưa được index.")
        else:
            raise ValueError(f"unsupported source type {stype!r}")

        entry = {
            "type": stype, "ref": ref, "title": title[:200],
            "text": text, "hash": _hash_payload(text),
        }
        pack = project.get("context_pack") or []
        if not isinstance(pack, list):
            pack = []
        if any(isinstance(e, dict) and e.get("hash") == entry["hash"] for e in pack):
            return {"duplicate": True, "sources": len(pack)}

        pack.append(entry)
        pack = pack[-_MAX_SOURCES:]
        await self._update(project_id, created_by, context_pack=pack)
        return {"duplicate": False, "sources": len(pack), "chars": len(text)}

    # ── Plan ───────────────────────────────────────────────────────────────
    async def generate_plan(self, project_id: str, created_by: int,
                            target_sections: Optional[int] = None) -> dict:
        from app.core.llm_gateway import TASK_CONTENT_STUDIO, get_gateway, ChatRequest

        project = await self.get_project(project_id, created_by)
        if not project:
            raise ValueError("project not found")
        pack = project.get("context_pack") or []
        if not pack:
            raise ValueError("Chưa có nguồn tài liệu nào trong Context Pack.")

        settings_obj = project.get("settings") or {}
        n_sections = target_sections or int(settings_obj.get("slide_count") or 8)
        language = settings_obj.get("language") or "vi"

        sources_text = "\n\n".join(
            f"[NGUỒN {i+1}] {e.get('title','')}\n{e.get('text','')}"
            for i, e in enumerate(pack)
        )[:40_000]

        user_msg = (
            f"Ngôn ngữ bài giảng: {language}.\n"
            f"Số mục mục tiêu: {n_sections}.\n"
            f"Loại đầu ra: {project['kind']}.\n\n"
            f"TÀI LIỆU NGUỒN:\n{sources_text}\n\n"
            "Hãy tạo lecture plan theo JSON schema đã cho."
        )
        gateway = get_gateway()
        raw = await gateway.chat(ChatRequest(
            task=TASK_CONTENT_STUDIO,
            messages=[
                {"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
            max_tokens=4000,
        ))

        plan, warnings = coerce_plan(
            raw.content, kind=project["kind"],
            fallback_title=project["title"], target_sections=n_sections,
        )
        if plan is None:
            raise ValueError("Model returned unusable plan: " + "; ".join(warnings))

        await self._update(
            project_id, created_by,
            plan=json.dumps(plan.model_dump(), ensure_ascii=False),
            status="planned",
        )
        updated = await self.get_project(project_id, created_by)
        return {"project": updated, "warnings": warnings}

    async def update_plan(self, project_id: str, created_by: int,
                          plan_dict: dict) -> dict:
        plan, warnings = coerce_plan(
            plan_dict, kind="slides", fallback_title="", target_sections=99
        )
        if plan is None:
            raise ValueError("; ".join(warnings))
        await self._update(
            project_id, created_by,
            plan=json.dumps(plan.model_dump(), ensure_ascii=False),
            status="planned",
        )
        return {"project": await self.get_project(project_id, created_by),
                "warnings": warnings}

    async def update_section(self, project_id: str, created_by: int,
                             index: int, patch: dict) -> dict:
        project = await self.get_project(project_id, created_by)
        if not project or not project.get("plan"):
            raise ValueError("project/plan not found")
        plan_dict = project["plan"]
        sections = plan_dict.get("sections") or []
        if index < 0 or index >= len(sections):
            raise ValueError("section index out of range")
        sec = sections[index]
        for field in ("title", "narration", "visual_suggestion"):
            if field in patch:
                sec[field] = str(patch[field])[:6000]
        for field in ("key_points", "slide_bullets"):
            if field in patch and isinstance(patch[field], list):
                sec[field] = [str(x)[:300] for x in patch[field]][:8]
        sections[index] = sec
        plan_dict["sections"] = sections
        await self._update(project_id, created_by,
                           plan=json.dumps(plan_dict, ensure_ascii=False))
        return await self.get_project(project_id, created_by)

    # ── Generation ─────────────────────────────────────────────────────────
    async def start_generate(self, project_id: str, created_by: int) -> dict:
        project = await self.get_project(project_id, created_by)
        if not project or not project.get("plan"):
            raise ValueError("plan required before generating")
        if project["status"] == "generating":
            return {"already_running": True}
        existing = _running_tasks.get(project_id)
        if existing and not existing.done():
            return {"already_running": True}

        await self._update(project_id, created_by, status="generating",
                           error_detail=None)
        task = asyncio.create_task(
            self._generate_and_store(project_id, created_by)
        )
        _running_tasks[project_id] = task
        return {"started": True}

    def _parse_plan(self, project: dict) -> StudioPlan:
        return StudioPlan(**(project.get("plan") or {}))

    async def _generate_and_store(self, project_id: str, created_by: int) -> None:
        async with _RENDER_SEMAPHORE:
            try:
                project = await self.get_project(project_id, created_by)
                if not project:
                    return
                plan = self._parse_plan(project)
                theme = (project.get("settings") or {}).get("theme") or "academic"
                artifacts: list[dict] = []

                if project["kind"] in ("slides", "video"):
                    pptx_bytes = render_plan_to_pptx_bytes(plan, theme=theme)
                    url = await upload_bytes(
                        f"studio/{project_id}/deck-{_hash_payload(plan.model_dump())[:10]}.pptx",
                        pptx_bytes,
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )
                    if url:
                        artifacts.append({"type": "pptx", "url": url})

                if project["kind"] in ("document", "slides"):
                    md = render_plan_to_markdown(plan)
                    url = await upload_bytes(
                        f"studio/{project_id}/lecture-{_hash_payload(md)[:10]}.md",
                        md.encode(), "text/markdown",
                    )
                    if url:
                        artifacts.append({"type": "markdown", "url": url,
                                          "inline": md})

                hashes = {
                    str(i): _hash_payload(sec.model_dump())
                    for i, sec in enumerate(plan.sections)
                }
                if artifacts:
                    await self._update(
                        project_id, created_by,
                        artifacts=json.dumps(artifacts, ensure_ascii=False),
                        section_hashes=json.dumps(hashes),
                        status="ready",
                    )
                else:
                    await self._update(project_id, created_by,
                                       status="failed",
                                       error_detail="artifact upload failed")
            except Exception as exc:  # noqa: BLE001
                logger.error("studio generate failed %s: %s", project_id, exc,
                             exc_info=True)
                try:
                    await self._update(project_id, created_by, status="failed",
                                       error_detail=str(exc)[:800])
                except Exception:  # noqa: BLE001
                    pass
            finally:
                _running_tasks.pop(project_id, None)

    async def regenerate_section_preview(self, project_id: str, created_by: int,
                                         index: int) -> dict:
        """Re-render ONE section into a mini-deck for instant preview after edit."""
        project = await self.get_project(project_id, created_by)
        if not project or not project.get("plan"):
            raise ValueError("project not found")
        plan = self._parse_plan(project)
        if index < 0 or index >= len(plan.sections):
            raise ValueError("index out of range")
        theme = (project.get("settings") or {}).get("theme") or "academic"
        async with _RENDER_SEMAPHORE:
            data = render_plan_to_pptx_bytes(plan, theme=theme)
        url = await upload_bytes(
            f"studio/{project_id}/preview-s{index}-{_hash_payload(plan.sections[index].model_dump())[:10]}.pptx",
            data, "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        return {"url": url}


studio_service = StudioService()
