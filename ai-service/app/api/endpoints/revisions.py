"""Teacher-controlled AI revision previews.

This endpoint deliberately never writes to the LMS.  It produces a structured
proposal from a teacher instruction; the browser shows that proposal and uses
the normal, permission-checked LMS update endpoint only after the teacher
chooses Apply.  Keeping generation and mutation separate prevents an AI call
from silently changing published learning material.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.llm import chat_complete_json
from app.core.llm_gateway.types import TASK_CONTENT_STUDIO, TASK_QUIZ_GEN

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/revisions", tags=["Teacher AI revisions"])


class RevisionRequest(BaseModel):
    # user_id is injected by the authenticated Next.js proxy.  It is retained
    # for audit correlation and prevents direct anonymous proxy use.
    user_id: int = Field(..., gt=0)
    kind: Literal["lesson", "question", "quiz", "slide_section"]
    instruction: str = Field(..., min_length=3, max_length=2_000)
    source: dict[str, Any]

    @field_validator("source")
    @classmethod
    def source_must_be_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("source is required")
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("source must be JSON serializable") from exc
        if len(encoded) > 80_000:
            raise ValueError("source is too large; revise one item at a time")
        return value


def _verify(x_ai_secret: Optional[str]) -> None:
    from app.core.config import get_settings
    if not x_ai_secret or x_ai_secret != get_settings().ai_service_secret:
        raise HTTPException(status_code=401, detail="Invalid AI service secret")


_FIELDS: dict[str, tuple[str, ...]] = {
    "lesson": ("title", "description", "markdown"),
    "question": (
        "question_text", "explanation", "answer_options", "correct_answers",
        "difficulty", "bloom_level", "points",
    ),
    "quiz": (
        "title", "description", "instructions", "time_limit_minutes", "max_attempts",
        "passing_score", "shuffle_questions", "shuffle_answers", "auto_grade",
    ),
    "slide_section": (
        "title", "key_points", "slide_bullets", "narration", "visual_suggestion",
        "visual_type", "visual_labels",
    ),
}


def _clean_proposal(kind: str, source: dict[str, Any], proposal: Any) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise ValueError("AI did not return an object")
    allowed = _FIELDS[kind]
    # A complete shape makes Apply deterministic while preserving source values
    # the teacher did not ask to alter.  Unknown model-produced keys are dropped.
    cleaned = {key: proposal.get(key, source.get(key)) for key in allowed if key in source or key in proposal}
    if not cleaned:
        raise ValueError("AI returned no editable fields")
    if kind == "question" and isinstance(cleaned.get("answer_options"), list):
        options = cleaned["answer_options"]
        if len(options) > 12 or any(not isinstance(option, dict) for option in options):
            raise ValueError("AI returned invalid answer options")
    return cleaned


@router.post("/preview")
async def preview_revision(body: RevisionRequest, x_ai_secret: Optional[str] = Header(None)):
    """Return a proposal only.  The caller must explicitly apply it in LMS."""
    _verify(x_ai_secret)
    allowed = _FIELDS[body.kind]
    source = {key: body.source[key] for key in allowed if key in body.source}
    if not source:
        raise HTTPException(status_code=422, detail="source has no fields supported for this revision kind")

    task = TASK_QUIZ_GEN if body.kind == "question" else TASK_CONTENT_STUDIO
    messages = [
        {
            "role": "system",
            "content": (
                "You are an instructional editor. Return ONLY one JSON object. "
                "Revise the supplied learning content according to the teacher instruction. "
                "Do not claim to have performed actions, do not add fields, do not alter IDs, "
                "and preserve factual accuracy. Keep the language of the source unless asked to translate. "
                "For multiple-choice questions, keep answers unambiguous and mark correct options with "
                "is_correct. The response is only a proposal; it will be reviewed by a teacher."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "kind": body.kind,
                    "teacher_instruction": body.instruction,
                    "editable_fields": list(source),
                    "source": source,
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        raw = await chat_complete_json(messages=messages, task=task, max_tokens=4_096)
        proposal = _clean_proposal(body.kind, source, raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Could not form a safe revision preview: {exc}") from exc
    except Exception as exc:
        logger.exception("AI revision preview failed", extra={"kind": body.kind, "user_id": body.user_id})
        raise HTTPException(status_code=502, detail="AI could not prepare a revision preview") from exc

    return {"kind": body.kind, "proposal": proposal, "apply_required": True}
