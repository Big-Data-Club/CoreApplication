"""
ai-service/app/api/endpoints/concept_check.py

Endpoints powering the Quick Action Panel "Quick Check" button on the
MicroLessonViewer. Generates 1–2 ultra-short multiple-choice questions
strictly grounded in either an inline text chunk or a knowledge node.

POST /ai/concept-check/generate
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.llm import build_concept_check_prompt, chat_complete_json
from app.core.llm_gateway import TASK_QUIZ_GEN
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/concept-check", tags=["Quick Action Panel"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class ConceptCheckRequest(BaseModel):
    """
    Either ``text_chunk`` or ``node_id`` must be provided. When both are
    supplied ``text_chunk`` wins because it represents exactly what the
    student is reading at this very moment.
    """
    text_chunk: Optional[str] = Field(default=None, max_length=8000)
    node_id: Optional[int] = None
    course_id: Optional[int] = None
    count: int = Field(default=2, ge=1, le=2)
    language: str = Field(default="vi", pattern="^(vi|en)$")


class ConceptCheckOption(BaseModel):
    text: str
    is_correct: bool
    explanation: str = ""


class ConceptCheckQuestion(BaseModel):
    question_text: str
    question_type: str = "SINGLE_CHOICE"
    answer_options: list[ConceptCheckOption]


class ConceptCheckResponse(BaseModel):
    node_id: Optional[int] = None
    questions: list[ConceptCheckQuestion]


# ── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/generate", response_model=ConceptCheckResponse)
async def generate_concept_check(body: ConceptCheckRequest, request: Request):
    """
    Generate 1–2 SINGLE_CHOICE 'Concept Check' questions for the Quick
    Action Panel. Always uses real source text - either the chunk passed
    in by the FE or the top RAG passages for ``node_id``.
    """
    _verify_internal(request)

    if not body.text_chunk and not body.node_id:
        raise HTTPException(
            status_code=400,
            detail="Either text_chunk or node_id must be provided",
        )

    text_chunk = body.text_chunk or ""
    node_name: Optional[str] = None

    # If the FE only gave us a node id, pull the top-3 retrieval chunks
    # and stitch them together - same pattern used by the quiz generator.
    if not text_chunk and body.node_id is not None:
        async with get_ai_conn() as conn:
            node = await conn.fetchrow(
                "SELECT id, name, name_vi FROM knowledge_nodes WHERE id = $1",
                body.node_id,
            )
        if not node:
            raise HTTPException(
                status_code=404,
                detail=f"Knowledge node {body.node_id} not found",
            )
        node_name = node["name_vi"] if body.language == "vi" and node["name_vi"] else node["name"]

        chunks = await rag_service.search(
            query=node_name,
            course_id=body.course_id,
            node_id=body.node_id,
            top_k=3,
        )
        text_chunk = "\n---\n".join(c.chunk_text for c in chunks if c.chunk_text)
        if not text_chunk:
            raise HTTPException(
                status_code=404,
                detail=f"No content found for node {body.node_id}",
            )

    messages = build_concept_check_prompt(
        text_chunk=text_chunk,
        node_name=node_name,
        count=body.count,
        language=body.language,
    )

    try:
        result = await chat_complete_json(
            messages=messages,
            model=settings.quiz_model,
            temperature=0.4,
            task=TASK_QUIZ_GEN,
        )
    except Exception as exc:
        logger.error("concept-check LLM failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    questions = result.get("questions") if isinstance(result, dict) else None
    if not questions or not isinstance(questions, list):
        raise HTTPException(
            status_code=500,
            detail="LLM returned no questions",
        )

    return ConceptCheckResponse(
        node_id=body.node_id,
        questions=[ConceptCheckQuestion(**q) for q in questions[: body.count]],
    )


def _verify_internal(request: Request):
    secret = request.headers.get("X-AI-Secret", "")
    if secret != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
