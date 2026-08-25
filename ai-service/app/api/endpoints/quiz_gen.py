"""
ai-service/app/api/endpoints/quiz_gen.py
Phase 2 endpoints:
POST /ai/quiz/generate   - generate Bloom's Taxonomy quiz for a node
GET  /ai/quiz/drafts/{course_id}   - list DRAFT questions for review
POST /ai/quiz/{gen_id}/approve     - approve + publish to quiz
POST /ai/quiz/{gen_id}/reject
POST /ai/spaced-repetition/record  - record review response (SM-2)
GET  /ai/spaced-repetition/due     - get due reviews for student
GET  /ai/spaced-repetition/stats   - review stats
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.quiz_service import quiz_gen_service, sr_service, BLOOM_LEVELS

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/quiz", tags=["Phase 2 - Quiz Generation"])
sr_router = APIRouter(prefix="/spaced-repetition", tags=["Phase 2 - Spaced Repetition"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class GenerateQuizRequest(BaseModel):
    node_id: int
    course_id: int
    created_by: int
    bloom_levels: Optional[list[str]] = None   # default: all 6 levels
    language: str = "vi"
    questions_per_level: int = Field(default=1, ge=1, le=3)


class GenerateToBankRequest(BaseModel):
    """Auto-generation INTO the course question bank.

    Node selection is automatic (sampled from the knowledge graph) - the
    teacher never picks nodes manually. ``exclude_questions`` carries recent
    bank question texts so the generator avoids duplicates.
    """
    course_id: int
    count: int = Field(default=10, ge=1, le=30)
    bloom_levels: Optional[list[str]] = None
    language: str = "vi"
    exclude_questions: list[str] = Field(default_factory=list, max_length=200)


class ApproveRequest(BaseModel):
    reviewer_id: int
    quiz_id: int
    review_note: str = ""


class RejectRequest(BaseModel):
    reviewer_id: int
    review_note: str


class RecordResponseRequest(BaseModel):
    student_id: int
    question_id: int
    course_id: int
    node_id: Optional[int] = None
    quality: int = Field(..., ge=0, le=5, description="SM-2 quality rating 0–5")


class ParseQuizTextRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, description="Raw unformatted text containing quiz questions")
    points_per_question: int = Field(default=10, ge=1, le=100)
    language: str = Field(default="vi")


# ── Quiz Generation Endpoints ─────────────────────────────────────────────────

@router.post("/generate")
async def generate_quiz(body: GenerateQuizRequest, request: Request):
    """
    Phase 2: Auto Quiz Generator using Bloom's Taxonomy.
    Generates DRAFT questions - require instructor review before publishing.
    """
    _verify_internal(request)

    # Validate bloom levels
    if body.bloom_levels:
        invalid = [l for l in body.bloom_levels if l not in BLOOM_LEVELS]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid bloom levels: {invalid}. Valid: {BLOOM_LEVELS}",
            )

    try:
        gen_ids = await quiz_gen_service.generate_for_node(
            node_id=body.node_id,
            course_id=body.course_id,
            created_by=body.created_by,
            bloom_levels=body.bloom_levels,
            language=body.language,
            questions_per_level=body.questions_per_level,
        )
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "generated": len(gen_ids),
        "gen_ids": gen_ids,
        "status": "DRAFT",
        "message": f"Generated {len(gen_ids)} questions. Awaiting instructor review.",
    }


@router.post("/generate-to-bank")
async def generate_to_bank(body: GenerateToBankRequest, request: Request):
    """
    Generate classified questions straight into the course question bank.

    Harness guarantees (model-independent): one question per LLM call,
    deterministic difficulty mapping from Bloom, strict option coercion,
    token-Jaccard dedup against ``exclude_questions``.
    """
    _verify_internal(request)
    try:
        questions, rejected = await quiz_gen_service.generate_for_bank(
            course_id=body.course_id,
            count=body.count,
            bloom_levels=body.bloom_levels,
            language=body.language or "vi",
            exclude_questions=body.exclude_questions,
        )
        return {
            "questions": questions,
            "count": len(questions),
            "rejected_count": rejected,
            "status": "ok",
        }
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        logger.error("generate_to_bank failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


@router.get("/drafts/{course_id}")
async def list_drafts(
    course_id: int,
    request: Request,
    node_id: Optional[int] = None,
):
    """List AI-generated DRAFT questions for instructor review."""
    _verify_internal(request)
    return await quiz_gen_service.list_drafts(course_id=course_id, node_id=node_id)


@router.post("/{gen_id}/approve")
async def approve_question(gen_id: int, body: ApproveRequest, request: Request):
    """
    Instructor approves a DRAFT question -> publishes to actual quiz.
    The question becomes visible to students.
    """
    _verify_internal(request)
    try:
        q_data = await quiz_gen_service.approve_question(
            gen_id=gen_id,
            reviewer_id=body.reviewer_id,
            quiz_id=body.quiz_id,
            review_note=body.review_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Approve failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return q_data


class UpdateQuestionIdRequest(BaseModel):
    quiz_question_id: int

@router.post("/{gen_id}/publish")
async def publish_question(gen_id: int, body: UpdateQuestionIdRequest, request: Request):
    """Callback for LMS to confirm successful insertion."""
    _verify_internal(request)
    await quiz_gen_service.update_quiz_question_id(gen_id, body.quiz_question_id)
    return {"status": "PUBLISHED"}


@router.post("/{gen_id}/reject")
async def reject_question(gen_id: int, body: RejectRequest, request: Request):
    """Instructor rejects a DRAFT question."""
    _verify_internal(request)
    await quiz_gen_service.reject_question(
        gen_id=gen_id,
        reviewer_id=body.reviewer_id,
        review_note=body.review_note,
    )
    return {"status": "REJECTED"}


@router.post("/parse-text")
async def parse_quiz_text(body: ParseQuizTextRequest, request: Request):
    """
    Synchronous endpoint: parse raw unformatted text into structured quiz questions.

    This is called directly from:
    1. The Smart Paste modal on the quiz manage page
    2. The Teacher chatbot agent's parse_quiz_questions tool

    Returns a list of question objects ready for batch insertion.
    Typical latency: 2-6 seconds for 1-10 questions.
    """
    _verify_internal(request)
    try:
        from app.services.quiz_parse_service import quiz_parse_service
        questions = await quiz_parse_service.parse(
            raw_text=body.raw_text,
            points_per_question=body.points_per_question,
            language=body.language,
        )
        return {
            "questions": questions,
            "count": len(questions),
            "status": "ok",
        }
    except Exception as e:
        logger.error("parse_quiz_text failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")


# ── Spaced Repetition Endpoints ────────────────────────────────────────────────


# ── Smart File Import ────────────────────────────────────────────────────────

_IMPORT_KEYWORDS = (
    "hình", "minh họa", "minh hoạ", "sơ đồ", "biểu đồ", "đồ thị",
    "figure", "diagram", "chart", "graph", "table", "bảng", "illustration",
)


def _match_images_to_questions(
    questions: list[dict], images: list[dict]
) -> tuple[list[dict], list[dict]]:
    """
    Heuristic illustration matching (deterministic, model-independent).

    An extracted image is suggested for a question when the question text
    references a figure ("hình", "sơ đồ", ...) - the same heuristic teachers
    apply by eye. Returns (questions, unused_images); each question gains a
    ``suggested_images: [{id, url, caption}]`` field.
    """
    if not images:
        for q in questions:
            q["suggested_images"] = []
        return questions, []

    used: set[int] = set()
    for q in questions:
        text = (q.get("question_text") or "").lower()
        refs_figure = any(kw in text for kw in _IMPORT_KEYWORDS)
        suggested: list[dict] = []
        if refs_figure:
            for img in images:
                idx = img.get("_idx", 0)
                if idx in used:
                    continue
                cap = (img.get("caption") or "").lower()
                relevant = any(w in cap for w in _IMPORT_KEYWORDS) or not cap
                if relevant:
                    suggested.append({
                        "id": f"img_{idx}",
                        "url": img.get("url"),
                        "caption": img.get("caption"),
                    })
                    used.add(idx)
                if len(suggested) >= 2:
                    break
        q["suggested_images"] = suggested
    unused = [img for img in images if img.get("_idx") not in used]
    return questions, unused


@router.post("/parse-file")
async def parse_quiz_file(
    request: Request,
    points_per_question: int = 10,
    language: str = "vi",
    instructions: str = "",
):
    """
    Smart quiz import from ANY document: scanned/text PDF, Word, Excel,
    PowerPoint, Markdown, plain text, or a photo of an exam paper.

    Pipeline (reuses the course-material ingestion stack):
      file bytes -> convert_to_markdown (text layer, VLM OCR fallback for
      scans/photos, embedded-image extraction to MinIO)
      -> quiz_parse_service.parse (schema-validated LLM extraction with
      deterministic normalisation, so accuracy does not depend on which
      provider/model answers)
      -> deterministic figure-matching heuristic.

    Multipart fields: file (required), plus optional form fields above.
    """
    _verify_internal(request)

    from fastapi import UploadFile, File, Form

    upload: UploadFile | None = None
    try:
        # FastAPI injects multipart pieces only when declared; re-declare here.
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise HTTPException(status_code=400, detail="Multipart field 'file' is required")
        raw_points = form.get("points_per_question")
        if raw_points:
            try:
                points_per_question = max(1, min(100, int(raw_points)))
            except (TypeError, ValueError):
                pass
        lang_raw = form.get("language")
        if lang_raw:
            language = str(lang_raw)[:8]
        instr_raw = form.get("instructions")
        if instr_raw:
            instructions = str(instr_raw)[:2000]

        file_bytes = await upload.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty file")
        if len(file_bytes) > 30 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (max 30MB)")

        filename = (upload.filename or "upload").lower()
        content_type = (upload.content_type or "").lower()
        if filename.endswith(".pdf") or "pdf" in content_type:
            file_type = "pdf"
        elif filename.endswith((".docx", ".doc")) or "wordprocessing" in content_type:
            file_type = "docx"
        elif filename.endswith((".pptx", ".ppt")) or "presentation" in content_type:
            file_type = "pptx"
        elif filename.endswith((".xlsx", ".xls", ".csv")) or "spreadsheet" in content_type or "csv" in content_type:
            file_type = "xlsx"
        elif filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) or content_type.startswith("image/"):
            file_type = "image"
        else:
            file_type = "text"  # .md / .txt / anything textual

        import uuid
        from app.services.file_to_markdown import convert_to_markdown

        doc = await convert_to_markdown(
            file_bytes=file_bytes,
            file_type=file_type,
            storage_prefix=f"quiz-import/{uuid.uuid4().hex[:12]}",
            language=language,
        )

        markdown = (doc.markdown or "").strip()
        if len(markdown) < 40:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Không trích xuất được đủ nội dung văn bản từ tệp này. "
                    "Ảnh scan quá mờ hoặc tệp rỗng?"
                ),
            )
        # Bound the parse like paste-flow does (chunking happens inside).
        markdown = markdown[:200_000]

        from app.services.quiz_parse_service import quiz_parse_service
        questions = await quiz_parse_service.parse(
            raw_text=markdown,
            points_per_question=points_per_question,
            language=language,
            instructions=instructions,
        )

        images = [
            {
                "_idx": i,
                "url": getattr(img, "url", None),
                "caption": (getattr(img, "caption_hint", "") or "")[:300],
                "page_number": getattr(img, "page_number", None),
            }
            for i, img in enumerate(getattr(doc, "images", []) or [])
            if getattr(img, "url", None)
        ]
        questions, unused_images = _match_images_to_questions(questions, images)

        return {
            "questions": questions,
            "count": len(questions),
            "rejected_count": 0,  # parse() already drops unusable ones silently
            "source": {
                "file_name": upload.filename,
                "file_type": file_type,
                "page_count": getattr(doc, "page_count", 0),
                "ocr_pages": getattr(doc, "ocr_pages", 0),
            },
            "extracted_images": [
                {k: v for k, v in img.items() if k != "_idx"} for img in images
            ],
            "unused_image_ids": [f"img_{img['_idx']}" for img in unused_images],
            "status": "ok",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("parse_quiz_file failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")


# ── Spaced Repetition (original location kept below) ──────────────────────────

@sr_router.post("/record")
async def record_review_response(body: RecordResponseRequest, request: Request):
    """
    Record student's review response and update SM-2 schedule.
    Call this after student answers a spaced repetition question.
    """
    _verify_internal(request)
    result = await sr_service.record_response(
        student_id=body.student_id,
        question_id=body.question_id,
        course_id=body.course_id,
        node_id=body.node_id,
        quality=body.quality,
    )
    return result


@sr_router.get("/due/student/{student_id}/course/{course_id}")
async def get_due_reviews(
    student_id: int,
    course_id: int,
    request: Request,
    limit: int = 20,
):
    """
    Get questions due for review today.
    Used by the 5-minute warm-up session on login.
    """
    _verify_internal(request)
    return await sr_service.get_due_reviews(
        student_id=student_id,
        course_id=course_id,
        limit=limit,
    )


@sr_router.get("/stats/student/{student_id}/course/{course_id}")
async def get_review_stats(student_id: int, course_id: int, request: Request):
    """Review progress stats for student dashboard."""
    _verify_internal(request)
    return await sr_service.get_review_stats(student_id, course_id)


@sr_router.get("/stats/student/{student_id}/due-today")
async def get_total_due_reviews(student_id: int, request: Request):
    """Get total reviews due today across all courses for student."""
    _verify_internal(request)
    count = await sr_service.get_total_due_reviews(student_id)
    return {"due_today": count}



def _verify_internal(request: Request):
    secret = request.headers.get("X-AI-Secret", "")
    if secret != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
