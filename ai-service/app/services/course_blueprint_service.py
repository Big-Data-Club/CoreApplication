"""Grounded, review-first curriculum modelling.

This service never turns a raw upload directly into a course.  It first
produces a compact evidence ledger (map), then a course plan (reduce), and
finally validates the plan as a prerequisite DAG.  The graph check is a model
invariant, not a chapter-number prompt trick: it works for any subject and
prevents a plan from being applied until prerequisite order is valid.
"""
from __future__ import annotations

import json
from urllib.parse import quote
from collections import defaultdict, deque
from typing import Any

from app.core.llm import chat_complete_structured
from app.core.llm_gateway import TASK_COURSE_BLUEPRINT
from app.core.llm_gateway.token_budget import pack_by_token_budget
from app.core.config import get_settings
from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    filename: str = Field(min_length=1, max_length=500)
    # UI clients normally provide no text: the service reads the exact object
    # uploaded to LMS.  Chat integrations may provide already-normalised text.
    text: str = ""
    file_path: str | None = None  # opaque LMS storage path, never invented by AI
    content_type: str = "application/octet-stream"


class Evidence(BaseModel):
    # The caller binds provenance after validation. Models commonly omit this
    # redundant field during map extraction, so it must not reject good source
    # evidence and trigger expensive retries.
    source_id: str = ""
    excerpt: str = Field(min_length=1, max_length=1200)
    topic: str = Field(default="", max_length=255)
    topics: list[str] = Field(default_factory=list, max_length=8)


class EvidenceLedger(BaseModel):
    evidence: list[Evidence] = Field(default_factory=list, max_length=16)


class BlueprintMaterial(BaseModel):
    source_id: str
    rationale: str = Field(min_length=1, max_length=500)


class BlueprintChapter(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    learning_outcomes: list[str] = Field(default_factory=list, max_length=8)
    material_ids: list[str] = Field(min_length=1, max_length=100)
    prerequisites: list[str] = Field(default_factory=list, max_length=30)


class CourseGovernance(BaseModel):
    """Course ownership choices validated by LMS, never inferred from content."""
    organization_id: int | None = Field(default=None, gt=0)
    visibility: str = Field(default="ORG_ONLY", pattern="^(PUBLIC|ORG_ONLY)$")
    co_teacher_ids: list[int] = Field(default_factory=list, max_length=20)
    thumbnail_url: str | None = Field(default=None, max_length=500)


class CoursePlan(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    category: str = Field(default="", max_length=100)
    level: str = Field(default="ALL_LEVELS", pattern="^(BEGINNER|INTERMEDIATE|ADVANCED|ALL_LEVELS)$")
    tags: list[str] = Field(default_factory=list, max_length=12)
    chapters: list[BlueprintChapter] = Field(min_length=1, max_length=50)
    governance: CourseGovernance = Field(default_factory=CourseGovernance)
    # Persisted provenance for review/audit.  The UI can reveal the excerpts
    # behind a recommendation without sending the full source to a model again.
    evidence_ledger: list[Evidence] = Field(default_factory=list)


def validate_plan(
    plan: CoursePlan,
    source_ids: set[str],
    allowed_organization_ids: set[int] | None = None,
    allowed_co_teacher_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Validate source grounding and return a deterministic topological order.

    Teacher edits go through this same validator, so a manual rearrangement can
    never accidentally place a dependent chapter before its prerequisite.
    """
    ids = [chapter.id for chapter in plan.chapters]
    errors: list[dict[str, str]] = []
    if len(ids) != len(set(ids)):
        errors.append({"code": "duplicate_chapter_id", "message": "Chapter ids must be unique."})

    known = set(ids)
    graph: dict[str, set[str]] = {item: set() for item in known}
    indegree: dict[str, int] = {item: 0 for item in known}
    if allowed_organization_ids is not None:
        org_id = plan.governance.organization_id
        if org_id is None:
            errors.append({"code": "organization_required", "message": "Choose the organization that owns this course."})
        elif org_id not in allowed_organization_ids:
            errors.append({"code": "organization_not_allowed", "message": "You cannot create a course in this organization."})
    if allowed_co_teacher_ids is not None:
        invalid_teachers = sorted(set(plan.governance.co_teacher_ids) - allowed_co_teacher_ids)
        if invalid_teachers:
            errors.append({"code": "co_teacher_not_allowed", "message": f"Unknown or unauthorized co-teachers: {invalid_teachers}"})
    for chapter in plan.chapters:
        unknown_sources = sorted(set(chapter.material_ids) - source_ids)
        if unknown_sources:
            errors.append({"code": "unknown_source", "message": f"{chapter.id}: unknown material ids {unknown_sources}"})
        for prerequisite in chapter.prerequisites:
            if prerequisite not in known:
                errors.append({"code": "unknown_prerequisite", "message": f"{chapter.id}: unknown prerequisite {prerequisite}"})
                continue
            if prerequisite == chapter.id:
                errors.append({"code": "self_prerequisite", "message": f"{chapter.id} cannot require itself."})
                continue
            # prerequisite -> dependent; a topological traversal is the only
            # ordering authority, not the original LLM list position.
            if chapter.id not in graph[prerequisite]:
                graph[prerequisite].add(chapter.id)
                indegree[chapter.id] += 1

    queue = deque(chapter.id for chapter in plan.chapters if indegree[chapter.id] == 0)
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for dependent in sorted(graph[current]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(ordered) != len(known):
        errors.append({"code": "prerequisite_cycle", "message": "Prerequisite graph contains a cycle."})
    return {"valid": not errors, "errors": errors, "topological_order": ordered}


class CourseBlueprintService:
    # Keep individual map calls comfortably below Groq's TPM cap, leaving
    # room for instructions and structured output.  All content is represented
    # in the ledger, so no source is silently dropped when documents are large.
    MAP_SOURCE_BUDGET = 1800

    async def _source_text(self, document: SourceDocument) -> str:
        if document.text.strip():
            return document.text
        if not document.file_path:
            raise ValueError(f"Document {document.filename} has neither text nor a file_path")
        # Do not accept arbitrary URLs here.  The server fetches only the LMS
        # object referenced by the authenticated upload manifest (SSRF-safe).
        import httpx
        from app.services.auto_index_service import _detect_file_type
        from app.services.file_to_markdown import convert_to_markdown

        settings = get_settings()
        path = quote(document.file_path.lstrip("/"), safe="/")
        url = f"{settings.lms_service_url.rstrip('/')}/api/v1/files/serve/{path}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()
        file_type = _detect_file_type(document.filename, document.content_type)
        if file_type == "binary":
            # Keep it in the manifest and course, but never fabricate a lesson
            # from bytes we cannot interpret (archives, executables, CAD, ...).
            return ""
        if file_type == "text":
            return _normalise_textual_source(response.content, document.filename)
        converted = await convert_to_markdown(
            response.content, file_type, f"course-blueprints/{document.id}", language="vi",
        )
        if not converted.markdown.strip():
            raise ValueError(f"Could not extract teaching text from {document.filename}")
        return converted.markdown

    async def draft(self, documents: list[SourceDocument], language: str = "vi") -> tuple[CoursePlan, dict[str, Any]]:
        source_ids = {doc.id for doc in documents}
        ledger: list[Evidence] = []
        for document in documents:
            source_text = await self._source_text(document)
            if not source_text.strip():
                continue
            batches = pack_by_token_budget([source_text], self.MAP_SOURCE_BUDGET)
            for batch_index, batch in enumerate(batches):
                excerpt = "".join(batch)
                result = await chat_complete_structured(
                    messages=[
                        {"role": "system", "content": (
                            "Extract only curriculum evidence explicitly present in the supplied source. "
                            "Do not infer missing topics. For every evidence item return excerpt and either one topic "
                            "or a topics array in the source language. Do not return source_id; provenance is assigned by the system."
                        )},
                        {"role": "user", "content": json.dumps({
                            "source_id": document.id, "filename": document.filename,
                            "part": batch_index + 1, "content": excerpt,
                        }, ensure_ascii=False)},
                    ],
                    response_model=EvidenceLedger,
                    task=TASK_COURSE_BLUEPRINT,
                    max_tokens=1400,
                )
                # Do not trust a model-generated source id; provenance is bound
                # by the request scope.
                ledger.extend(Evidence(source_id=document.id, excerpt=item.excerpt,
                                       topics=item.topics or ([item.topic] if item.topic else []))
                              for item in result.evidence)

        plan = await chat_complete_structured(
            messages=[
                {"role": "system", "content": (
                    "You are a curriculum modeller. Build a course plan ONLY from the evidence ledger. "
                    "Every chapter must reference one or more source ids. Model prerequisite relationships "
                    "between chapter ids; do not use chapter numbers as a substitute for dependencies. "
                    "A source with no evidence is an attachment only; do not infer its contents or create a chapter from its filename. "
                    "Return the requested JSON only."
                )},
                {"role": "user", "content": json.dumps({
                    "language": language,
                    "sources": [{"id": d.id, "filename": d.filename} for d in documents],
                    "evidence_ledger": [item.model_dump() for item in ledger],
                }, ensure_ascii=False)},
            ],
            response_model=CoursePlan,
            task=TASK_COURSE_BLUEPRINT,
            max_tokens=4000,
        )
        report = validate_plan(plan, source_ids)
        if not report["valid"]:
            # A bad model output is surfaced for retry/review, never applied.
            raise ValueError("Generated course blueprint violates invariants: " + json.dumps(report["errors"]))
        order = {chapter_id: index for index, chapter_id in enumerate(report["topological_order"])}
        plan.chapters.sort(key=lambda chapter: order[chapter.id])
        plan.evidence_ledger = ledger
        return plan, report


def _normalise_textual_source(data: bytes, filename: str) -> str:
    """Turn code/data/notebooks into faithful, model-readable source text."""
    text = data.decode("utf-8", errors="replace")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "ipynb":
        try:
            notebook = json.loads(text)
            parts: list[str] = [f"# Notebook: {filename}"]
            for index, cell in enumerate(notebook.get("cells", []), 1):
                source = "".join(cell.get("source", []))
                if not source.strip():
                    continue
                parts.append(f"## Code cell {index}\n```python\n{source}\n```" if cell.get("cell_type") == "code" else source)
            return "\n\n".join(parts)
        except (ValueError, TypeError):
            pass
    if extension == "json":
        try:
            return "# JSON: " + filename + "\n\n```json\n" + json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n```"
        except ValueError:
            pass
    language = {"py": "python", "cpp": "cpp", "c": "c", "h": "c", "hpp": "cpp", "sh": "bash", "sbatch": "bash", "js": "javascript", "ts": "typescript", "tsx": "tsx", "go": "go", "rs": "rust", "sql": "sql"}.get(extension, "text")
    return f"# Source file: {filename}\n\n```{language}\n{text}\n```"


course_blueprint_service = CourseBlueprintService()
