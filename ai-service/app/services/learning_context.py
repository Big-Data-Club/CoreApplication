"""Curriculum-scoped evidence; nodes/chunks are internal retrieval aids.

LMS supplies canonical source IDs/text after its edit-access check. AI reads
only its own index, hydrates parents within the same content/course, and adds
bounded graph context without turning a concept label into source material.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import get_ai_conn


class AuthoringSource(BaseModel):
    content_id: int = Field(gt=0)
    section_id: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=1000)
    section_title: str = ""
    type: str = "DOCUMENT"
    text: str = Field(default="", max_length=2_000_000)


async def lms_sources(course_id: int, user_id: int, **scope) -> list[AuthoringSource]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.lms_service_url.rstrip('/')}/api/v1/courses/{course_id}/authoring-context",
            headers={"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)},
            json=scope,
        )
        if response.status_code in (401, 403):
            raise PermissionError("Bạn không có quyền soạn nội dung cho khóa học này.")
        if response.status_code == 422:
            raise ValueError("Chương/bài học không hợp lệ hoặc chưa có tài liệu học tập.")
        response.raise_for_status()
        return [AuthoringSource.model_validate(s) for s in response.json()["data"]]


@dataclass
class LearningContext:
    sources: list[dict]
    node_ids: list[int]
    relations: list[dict]

    def provenance(self) -> dict:
        return {"content_ids": [s["content_id"] for s in self.sources],
                "node_ids": self.node_ids, "context_version": 1}


async def build_learning_context(course_id: int, sources: list[AuthoringSource]) -> LearningContext:
    if not sources:
        raise ValueError("Hãy chọn chương hoặc bài học có nội dung.")
    # Overlapping chapter/lesson selections are a union, not repeated evidence.
    sources = list({s.content_id: s for s in sources}.values())
    ids = [s.content_id for s in sources]
    async with get_ai_conn() as conn:
        chunks = await conn.fetch("""
            SELECT c.id, c.content_id, c.node_id, c.chunk_index,
                   COALESCE(p.id, c.id) AS evidence_id,
                   COALESCE(NULLIF(p.chunk_text,''), c.chunk_text) AS text
            FROM document_chunks c
            LEFT JOIN document_chunks p ON p.id=c.parent_chunk_id
                AND p.course_id=c.course_id AND p.content_id=c.content_id AND p.status='ready' AND p.chunk_level='parent'
                AND NULLIF(BTRIM(p.chunk_text),'') IS NOT NULL
            WHERE c.course_id=$1 AND c.content_id=ANY($2::bigint[])
                AND c.status='ready' AND (c.chunk_level='child' OR c.chunk_level IS NULL)
            ORDER BY c.content_id,c.chunk_index,c.id
        """, course_id, ids)
        nodes = await conn.fetch("""
            SELECT id,name,description FROM knowledge_nodes WHERE course_id=$1
            AND (source_content_id=ANY($2::bigint[]) OR id IN
                (SELECT node_id FROM document_chunks WHERE course_id=$1
                 AND content_id=ANY($2::bigint[]) AND status='ready')) ORDER BY id
        """, course_id, ids)
        node_ids = [n["id"] for n in nodes]
        relations = await conn.fetch("""
            SELECT r.source_node_id,r.target_node_id,r.relation_type,
                   a.name AS source_name,b.name AS target_name
            FROM knowledge_node_relations r
            JOIN knowledge_nodes a ON a.id=r.source_node_id AND a.course_id=$1
            JOIN knowledge_nodes b ON b.id=r.target_node_id AND b.course_id=$1
            WHERE r.course_id=$1 AND
                (r.source_node_id=ANY($2::bigint[]) OR r.target_node_id=ANY($2::bigint[]))
            ORDER BY r.id LIMIT 80
        """, course_id, node_ids) if node_ids else []

    grouped: dict[int, list] = {cid: [] for cid in ids}
    seen: set[int] = set()
    for chunk in chunks:
        if chunk["evidence_id"] not in seen and chunk["text"]:
            grouped[chunk["content_id"]].append(dict(chunk))
            seen.add(chunk["evidence_id"])
    pack = []
    for source in sources:
        # Canonical TEXT wins over a potentially stale index. Documents/videos
        # require extracted material; titles and graph descriptions never suffice.
        material = source.text.strip() if source.type == "TEXT" else ""
        if not material:
            material = "\n\n".join(c["text"] for c in grouped[source.content_id])
        if not material.strip():
            raise ValueError(f'Bài "{source.title}" chưa có nội dung sẵn sàng. Hãy xử lý tài liệu trước khi tạo.')
        pack.append({"title": f"{source.section_title} / {source.title}".strip(" /"),
                     "text": material, "content_id": source.content_id,
                     "section_id": source.section_id,
                     "chunk_ids": [c["evidence_id"] for c in grouped[source.content_id]]})
    # Relations guide prerequisites and synthesis, but are explicitly not facts
    # from the selected lesson. No unscoped semantic fallback is performed.
    if sum(len(s["text"]) for s in pack) > 2_000_000:
        raise ValueError("Nguồn quá lớn. Hãy chọn ít chương/bài học hơn.")
    return LearningContext(pack, node_ids, [dict(r) for r in relations])
