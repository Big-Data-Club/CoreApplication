"""Owner-scoped flashcard speech, cached by text and managed voice configuration."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.core.database import get_ai_conn
from app.core.llm_gateway import get_gateway
from app.core.llm_gateway.types import SpeechRequest, TASK_TEXT_TO_SPEECH
from app.services.minio_storage import upload_bytes
from app.services.studio.browser_renderer import command

logger = logging.getLogger(__name__)


async def request_flashcard_speech(owner_id: int, card_id: int, course_id: int, side: str, speed: float) -> dict:
    async with get_ai_conn() as conn:
        card = await conn.fetchrow("""SELECT c.* FROM personal_flashcards c JOIN personal_flashcard_decks d ON d.id=c.deck_id
            WHERE c.id=$1 AND c.student_id=$2 AND d.student_id=$2 AND d.course_id=$3""", card_id, owner_id, course_id)
    if not card:
        raise LookupError("Flashcard not found")
    chain = await get_gateway().registry.get_binding_chain(TASK_TEXT_TO_SPEECH)
    if not chain:
        raise ValueError("Configure text_to_speech in Gateway")
    request = {"text": card["front_text" if side == "front" else "back_text"],
               "language": card["language" if side == "front" else "answer_language"], "speed": speed}
    config = [(b.model.id, b.model.model_name, b.model.config) for b in chain]
    digest = hashlib.sha256(json.dumps([card_id, request, config], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    async with get_ai_conn() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", owner_id)
        existing = await conn.fetchrow("SELECT id,status FROM speech_jobs WHERE owner_id=$1 AND content_hash=$2", owner_id, digest)
        if existing and existing["status"] != "failed":
            return {"job_id": str(existing["id"]), "status": existing["status"]}
        count = await conn.fetchval("SELECT count(*) FROM speech_jobs WHERE owner_id=$1 AND created_at>now()-interval '1 hour'", owner_id)
        if count >= 60:
            raise ValueError("Speech quota reached; try again later")
        if existing:
            await conn.execute("UPDATE speech_jobs SET status='queued',attempts=0,error=NULL,created_at=now(),updated_at=now() WHERE id=$1", existing["id"])
            return {"job_id": str(existing["id"]), "status": "queued"}
        job_id = uuid4()
        await conn.execute("INSERT INTO speech_jobs(id,owner_id,card_id,content_hash,request) VALUES($1,$2,$3,$4,$5::jsonb)",
                           job_id, owner_id, card_id, digest, json.dumps(request))
    return {"job_id": str(job_id), "status": "queued"}


async def run_next_speech() -> bool:
    token = uuid4()
    async with get_ai_conn() as conn:
        row = await conn.fetchrow("""UPDATE speech_jobs SET status='running',lease_token=$1,lease_until=now()+interval '3 minutes',
            attempts=attempts+1,updated_at=now() WHERE id=(SELECT id FROM speech_jobs WHERE status='queued'
            OR (status='running' AND lease_until<now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""", token)
    if not row:
        return False
    work = asyncio.current_task()
    lost_lease = False
    async def heartbeat():
        nonlocal lost_lease
        while True:
            await asyncio.sleep(30)
            async with get_ai_conn() as conn:
                result = await conn.fetchval("""UPDATE speech_jobs SET lease_until=now()+interval '3 minutes'
                    WHERE id=$1 AND lease_token=$2 AND lease_until>now() AND status='running' RETURNING id""", row["id"], token)
            if not result:
                lost_lease = True
                work.cancel()
                return
    beat = asyncio.create_task(heartbeat())
    try:
        async with asyncio.timeout(600):
            if row["attempts"] > 3:
                raise ValueError("Speech retry limit reached")
            data = json.loads(row["request"]) if isinstance(row["request"], str) else row["request"]
            text = data.pop("text").strip()
            parts = []
            while text:
                end = len(text) if len(text) <= 2200 else max(text.rfind(". ", 600, 2200)+1, text.rfind(" ", 600, 2200))
                end = end if end > 0 else min(2200,len(text))
                parts.append(text[:end]); text = text[end:].lstrip()
            with TemporaryDirectory(prefix="flashcard-speech-") as temporary:
                directory = Path(temporary); inputs = []
                for index, part in enumerate(parts):
                    response = await get_gateway().speech(SpeechRequest(text=part, **data))
                    path = directory / f"part{index}.mp3"; path.write_bytes(response.audio)
                    inputs.extend(["-i", str(path)])
                chain = ''.join(f'[{i}:a]' for i in range(len(parts)))
                await command("ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", f"{chain}concat=n={len(parts)}:v=0:a=1[a]",
                              "-map", "[a]", "-c:a", "libmp3lame", directory / "speech.mp3")
                key = f"studio/speech/{row['owner_id']}/{row['id']}.mp3"
                if not await upload_bytes(key, (directory / "speech.mp3").read_bytes(), "audio/mpeg"):
                    raise ValueError("Speech storage failed")
            async with get_ai_conn() as conn:
                await conn.execute("""UPDATE speech_jobs SET status='ready',object_key=$3,lease_until=NULL,updated_at=now()
                    WHERE id=$1 AND lease_token=$2 AND lease_until>now()""", row["id"], token, key)
    except asyncio.CancelledError:
        if lost_lease:
            work.uncancel()
            return True
        raise
    except Exception:
        logger.exception("Speech generation failed job=%s", row["id"])
        async with get_ai_conn() as conn:
            await conn.execute("""UPDATE speech_jobs SET status='failed',error='Giọng neural chưa sẵn sàng. Kiểm tra key và voice trong Gateway.',
                lease_until=NULL,updated_at=now() WHERE id=$1 AND lease_token=$2 AND lease_until>now()""", row["id"], token)
    finally:
        beat.cancel(); await asyncio.gather(beat, return_exceptions=True)
    return True


async def serve_speech():
    while True:
        try:
            if await run_next_speech():
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Speech queue sweep failed")
        await asyncio.sleep(2)
