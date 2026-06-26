import logging
from datetime import date, timedelta
from typing import Optional
from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)

class FlashcardService:
    MIN_EASINESS = 1.3

    # ── Read ──────────────────────────────────────────────────────────────────

    async def list_due_flashcards(self, student_id: int, course_id: int) -> list[dict]:
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT f.id, f.course_id, f.node_id, f.lesson_id, f.content_id, f.front_text, f.back_text, f.status,
                       f.source_diagnosis_id, (f.created_at AT TIME ZONE 'UTC') as created_at,
                       fr.easiness_factor, fr.interval_days, fr.repetitions,
                       fr.next_review_date, fr.last_reviewed_at
                FROM flashcards f
                JOIN flashcard_repetitions fr ON fr.flashcard_id = f.id
                WHERE f.student_id = $1 AND f.course_id = $2
                  AND fr.next_review_date <= CURRENT_DATE
                  AND f.status = 'ACTIVE'
                ORDER BY fr.next_review_date ASC, fr.easiness_factor ASC
                """,
                student_id, course_id,
            )
        return [dict(r) for r in rows]

    async def list_flashcards_by_target(self, student_id: int, course_id: int, node_id: Optional[int] = None, lesson_id: Optional[int] = None, content_id: Optional[int] = None) -> list[dict]:
        async with get_ai_conn() as conn:
            if node_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT f.id, f.course_id, f.node_id, f.lesson_id, f.content_id, f.front_text, f.back_text, f.status,
                           f.source_diagnosis_id, (f.created_at AT TIME ZONE 'UTC') as created_at,
                           fr.easiness_factor, fr.interval_days, fr.repetitions,
                           fr.next_review_date, fr.last_reviewed_at
                    FROM flashcards f
                    LEFT JOIN flashcard_repetitions fr ON fr.flashcard_id = f.id
                    WHERE f.student_id = $1 AND f.course_id = $2 AND f.node_id = $3
                    ORDER BY f.created_at DESC
                    """,
                    student_id, course_id, node_id,
                )
            elif lesson_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT f.id, f.course_id, f.node_id, f.lesson_id, f.content_id, f.front_text, f.back_text, f.status,
                           f.source_diagnosis_id, (f.created_at AT TIME ZONE 'UTC') as created_at,
                           fr.easiness_factor, fr.interval_days, fr.repetitions,
                           fr.next_review_date, fr.last_reviewed_at
                    FROM flashcards f
                    LEFT JOIN flashcard_repetitions fr ON fr.flashcard_id = f.id
                    WHERE f.student_id = $1 AND f.course_id = $2 AND f.lesson_id = $3
                    ORDER BY f.created_at DESC
                    """,
                    student_id, course_id, lesson_id,
                )
            elif content_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT f.id, f.course_id, f.node_id, f.lesson_id, f.content_id, f.front_text, f.back_text, f.status,
                           f.source_diagnosis_id, (f.created_at AT TIME ZONE 'UTC') as created_at,
                           fr.easiness_factor, fr.interval_days, fr.repetitions,
                           fr.next_review_date, fr.last_reviewed_at
                    FROM flashcards f
                    LEFT JOIN flashcard_repetitions fr ON fr.flashcard_id = f.id
                    WHERE f.student_id = $1 AND f.course_id = $2 AND f.content_id = $3
                    ORDER BY f.created_at DESC
                    """,
                    student_id, course_id, content_id,
                )
            else:
                rows = []
        return [dict(r) for r in rows]

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create_flashcards(
        self,
        flashcards_data: list[dict],
        student_id: int,
        course_id: int,
        node_id: Optional[int] = None,
        lesson_id: Optional[int] = None,
        content_id: Optional[int] = None,
    ) -> list[dict]:
        results = []
        async with get_ai_conn() as conn:
            for item in flashcards_data:
                row = await conn.fetchrow(
                    """
                    INSERT INTO flashcards (course_id, node_id, lesson_id, content_id, student_id, front_text, back_text, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'ACTIVE')
                    ON CONFLICT DO NOTHING
                    RETURNING id, (created_at AT TIME ZONE 'UTC') as created_at
                    """,
                    course_id, node_id, lesson_id, content_id, student_id,
                    item.get("front_text", ""), item.get("back_text", ""),
                )
                if not row:
                    logger.info("Skipped duplicate flashcard creation for student %s, course %s, front: %s", 
                                student_id, course_id, item.get("front_text", "")[:40])
                    continue
                fc_id = row["id"]
                await conn.execute(
                    """
                    INSERT INTO flashcard_repetitions (student_id, flashcard_id, course_id, next_review_date)
                    VALUES ($1, $2, $3, CURRENT_DATE)
                    """,
                    student_id, fc_id, course_id,
                )
                results.append({
                    "id":         fc_id,
                    "course_id":  course_id,
                    "node_id":    node_id,
                    "lesson_id":  lesson_id,
                    "content_id": content_id,
                    "front_text": item.get("front_text", ""),
                    "back_text":  item.get("back_text", ""),
                    "status":     "ACTIVE",
                    "created_at": row["created_at"],
                })
        return results

    # ── LLM generation (used by HTTP endpoint AND Kafka worker) ───────────────

    async def generate_flashcards_with_llm(
        self,
        student_id: int,
        course_id: int,
        node_id: Optional[int] = None,
        lesson_id: Optional[int] = None,
        content_id: Optional[int] = None,
        text_chunk: Optional[str] = None,
        count: int = 3,
        language: str = "vi",
        existing_fronts: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Full pipeline: RAG retrieval -> LLM generation -> DB persist.
        Called by both the HTTP endpoint and the Kafka worker (GENERATE_FLASHCARD command).
        Returns the persisted flashcard dicts.
        """
        from app.core.config import get_settings
        from app.core.database import get_ai_conn
        from app.core.llm import chat_complete_json, build_flashcard_generation_prompt
        from app.services.rag_service import rag_service
        from app.core.llm_gateway import TASK_FLASHCARD_GEN

        settings = get_settings()

        # 1 & 2 & 3. Context gathering
        node_name = "Concept"
        wrong_answers_context = ""
        context_texts = []

        if node_id is not None:
            async with get_ai_conn() as conn:
                node = await conn.fetchrow(
                    "SELECT id, name, name_vi, name_en FROM knowledge_nodes WHERE id = $1",
                    node_id,
                )
            if not node:
                raise ValueError(f"Knowledge node {node_id} not found")

            node_name = node["name_vi"] if language == "vi" and node["name_vi"] else node["name"]

            async with get_ai_conn() as conn:
                mistakes = await conn.fetch(
                    """
                    SELECT explanation AS gap
                    FROM ai_diagnoses
                    WHERE student_id = $1 AND node_id = $2
                      AND explanation IS NOT NULL AND explanation != ''
                    ORDER BY created_at DESC
                    LIMIT 3
                    """,
                    student_id, node_id,
                )
            wrong_answers_context = (
                "\n".join(r["gap"] for r in mistakes if r["gap"])
                if mistakes
                else ("Không có thông tin lỗi sai cụ thể. Tập trung khái niệm nền tảng."
                      if language == "vi"
                      else "No specific error info available. Focus on foundational concepts.")
            )

            if text_chunk:
                context_texts = [text_chunk]
            else:
                chunks = await rag_service.search_multilingual(
                    query=node_name, course_id=course_id, node_id=node_id, top_k=3,
                )
                if not chunks:
                    chunks = await rag_service.search_multilingual(
                        query=node_name, course_id=course_id, top_k=2,
                    )
                context_texts = [c.chunk_text for c in chunks] or [f"Chủ đề: {node_name}"]
        else:
            context_texts = [text_chunk or ""]
            wrong_answers_context = ("Không có thông tin lỗi sai cụ thể. Tập trung khái niệm nền tảng."
                                     if language == "vi"
                                     else "No specific error info available. Focus on foundational concepts.")

        # 4. LLM generation
        messages = build_flashcard_generation_prompt(
            context_chunks=context_texts,
            node_name=node_name,
            wrong_answers_context=wrong_answers_context,
            count=count,
            language=language,
            existing_fronts=existing_fronts,
        )
        result = await chat_complete_json(
            messages=messages,
            model=settings.quiz_model,
            temperature=0.7,
            task=TASK_FLASHCARD_GEN,
        )
        if "flashcards" not in result:
            raise ValueError("Missing 'flashcards' key in LLM response")

        # 5. Persist and return
        return await self.create_flashcards(
            result["flashcards"],
            student_id=student_id,
            course_id=course_id,
            node_id=node_id,
            lesson_id=lesson_id,
            content_id=content_id,
        )

    # ── SM-2 review ───────────────────────────────────────────────────────────

    def _update_sm2(self, ef: float, interval: int, reps: int, quality: int):
        new_ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ef = max(self.MIN_EASINESS, new_ef)
        if quality < 3:
            new_interval, new_reps = 1, 0
        else:
            new_reps = reps + 1
            if new_reps == 1:   new_interval = 1
            elif new_reps == 2: new_interval = 6
            else:               new_interval = round(interval * new_ef)
        return new_ef, new_interval, new_reps

    async def review_flashcard(self, student_id: int, flashcard_id: int, quality: int) -> dict:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT easiness_factor, interval_days, repetitions, course_id
                FROM flashcard_repetitions
                WHERE student_id = $1 AND flashcard_id = $2
                """,
                student_id, flashcard_id,
            )
            if not row:
                raise ValueError("Flashcard repetition not found")

            new_ef, new_interval, new_reps = self._update_sm2(
                float(row["easiness_factor"]),
                int(row["interval_days"]),
                int(row["repetitions"]),
                quality,
            )
            next_date = date.today() + timedelta(days=new_interval)

            await conn.execute(
                """
                UPDATE flashcard_repetitions
                SET easiness_factor = $1, interval_days = $2, repetitions = $3,
                    quality_last = $4, next_review_date = $5,
                    last_reviewed_at = NOW(), updated_at = NOW()
                WHERE student_id = $6 AND flashcard_id = $7
                """,
                new_ef, new_interval, new_reps, quality, next_date,
                student_id, flashcard_id,
            )

        return {
            "flashcard_id":    flashcard_id,
            "easiness_factor": round(new_ef, 2),
            "interval_days":   new_interval,
            "repetitions":     new_reps,
            "next_review_date": next_date.isoformat(),
        }


flashcard_srv = FlashcardService()
