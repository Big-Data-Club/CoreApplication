from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.api.endpoints.studio import _verify
from app.core.database import get_ai_conn
from app.services.speech_service import request_flashcard_speech
from app.services.minio_storage import download_bytes

router = APIRouter(prefix="/speech", tags=["Neural speech"])


class FlashcardSpeechRequest(BaseModel):
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    card_id: int = Field(gt=0)
    side: Literal["front", "back"]
    speed: float = Field(default=0.97, ge=0.7, le=1.2)


@router.post("/flashcard", status_code=202)
async def flashcard_speech(body: FlashcardSpeechRequest, x_ai_secret: str | None = Header(None)):
    _verify(x_ai_secret)
    try:
        return await request_flashcard_speech(body.user_id, body.card_id, body.course_id, body.side, body.speed)
    except LookupError:
        raise HTTPException(404, "Flashcard not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


async def owned_job(job_id: UUID, user_id: int):
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("SELECT id,status,error,object_key FROM speech_jobs WHERE id=$1 AND owner_id=$2", job_id, user_id)
    if not row:
        raise HTTPException(404, "Speech job not found")
    return row


@router.get("/jobs/{job_id}")
async def speech_status(job_id: UUID, user_id: int = Query(gt=0), x_ai_secret: str | None = Header(None)):
    _verify(x_ai_secret)
    row = await owned_job(job_id, user_id)
    return {"job_id": str(row["id"]), "status": row["status"], "error": row["error"]}


@router.get("/jobs/{job_id}/audio")
async def speech_audio(job_id: UUID, user_id: int = Query(gt=0), x_ai_secret: str | None = Header(None)):
    _verify(x_ai_secret)
    row = await owned_job(job_id, user_id)
    if row["status"] != "ready":
        raise HTTPException(409, "Speech not ready")
    data = await download_bytes(row["object_key"])
    if not data:
        raise HTTPException(503, "Speech storage unavailable")
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})
