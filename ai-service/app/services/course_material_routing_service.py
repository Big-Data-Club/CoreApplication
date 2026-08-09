from __future__ import annotations

import json
from pydantic import BaseModel, Field

from app.core.llm import chat_complete_structured
from app.core.llm_gateway import TASK_COURSE_BLUEPRINT
from app.services.course_blueprint_service import SourceDocument, course_blueprint_service


class RoutingSection(BaseModel):
    id: int
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)


class MaterialSuggestion(BaseModel):
    document_id: str
    section_id: int | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    rationale: str = Field(default="", max_length=500)
    requires_manual_selection: bool = False


class MaterialSuggestionEnvelope(BaseModel):
    suggestion: MaterialSuggestion


async def suggest_material_routes(documents: list[SourceDocument], sections: list[RoutingSection]) -> list[MaterialSuggestion]:
    allowed = {section.id for section in sections}
    suggestions: list[MaterialSuggestion] = []
    for document in documents:
        evidence = await course_blueprint_service.evidence_for_document(document)
        if not evidence:
            suggestions.append(MaterialSuggestion(
                document_id=document.id, rationale="Không thể đọc nội dung; giáo viên cần chọn chương.",
                requires_manual_selection=True,
            ))
            continue
        result = await chat_complete_structured(
            messages=[
                {"role": "system", "content": (
                    "Assign this document to exactly one existing course section using only the grounded evidence. "
                    "Use only a supplied numeric section_id. If evidence is insufficient, return section_id null and "
                    "requires_manual_selection true. Return compact JSON only."
                )},
                {"role": "user", "content": json.dumps({
                    "document": {"id": document.id, "filename": document.filename},
                    "sections": [section.model_dump() for section in sections],
                    "evidence": [item.model_dump() for item in evidence],
                }, ensure_ascii=False)},
            ], response_model=MaterialSuggestionEnvelope, task=TASK_COURSE_BLUEPRINT,
            max_tokens=700, native_json_mode=False,
        )
        item = result.suggestion
        item.document_id = document.id
        if item.section_id not in allowed:
            item.section_id = None
            item.requires_manual_selection = True
        suggestions.append(item)
    return suggestions
