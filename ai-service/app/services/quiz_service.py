from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.database import get_ai_conn
from app.core.llm import chat_complete_json, build_quiz_generation_prompt
from app.core.llm_gateway import TASK_QUIZ_GEN
from app.services.rag_service import rag_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

_LLM_SEMAPHORE = asyncio.Semaphore(4)

class QuizGenerationService:

    async def generate_for_node(
        self,
        node_id: int,
        course_id: int,
        created_by: int,
        bloom_levels: list[str] | None = None,
        language: str = "vi",
        questions_per_level: int = 1,
        assessment_purpose: str = "formative",
        teacher_instructions: str = "",
    ) -> list[int]:
        levels = bloom_levels or BLOOM_LEVELS
        gen_ids: list[int] = []

        async with get_ai_conn() as conn:
            node = await conn.fetchrow(
                "SELECT id, name, name_vi, name_en, course_id FROM knowledge_nodes WHERE id = $1",
                node_id,
            )
        if not node:
            raise ValueError(f"Knowledge node {node_id} not found")

        node_name = node["name_vi"] if language == "vi" and node["name_vi"] else node["name"]

        async with get_ai_conn() as conn:
            existing = await conn.fetch(
                "SELECT question_text FROM ai_quiz_generations WHERE node_id = $1", node_id,
            )
        existing_texts = [r["question_text"] for r in existing]

        tasks = []
        for bloom_level in levels:
            for _ in range(questions_per_level):
                tasks.append(
                    self._generate_single_with_semaphore(
                        node_id=node_id, course_id=course_id, created_by=created_by,
                        bloom_level=bloom_level, node_name=node_name,
                        language=language, existing_questions=existing_texts,
                        assessment_purpose=assessment_purpose,
                        teacher_instructions=teacher_instructions,
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, res in enumerate(results):
            if isinstance(res, Exception):
                level_index = i // max(questions_per_level, 1)
                level_name  = levels[level_index] if level_index < len(levels) else "unknown"
                logger.error("Quiz gen failed for bloom_level=%s node_id=%d: %s", level_name, node_id, res)
            else:
                gen_ids.append(res)

        logger.info(
            "Generated %d/%d questions for node_id=%d",
            len(gen_ids), len(tasks), node_id,
        )
        return gen_ids

    # ── Bank generation (Thư viện đề thi) ────────────────────────────────────
    # Harness rules that make ANY provider/model produce correct output:
    #   * one question per call (small models fail long-array JSON),
    #   * strict schema + few-shot prompt (build_quiz_generation_prompt),
    #   * deterministic normalisation AFTER generation - difficulty is mapped
    #     from Bloom, options are coerced to the bank contract, exactly one
    #     correct option is enforced for SINGLE_CHOICE, duplicates are dropped
    #     via token-Jaccard. The model never decides structure.

    _BLOOM_DIFFICULTY = {
        "remember": "EASY", "understand": "EASY",
        "apply": "MEDIUM",
        "analyze": "HARD", "evaluate": "HARD", "create": "HARD",
    }

    @staticmethod
    def _norm_tokens(text: str) -> set[str]:
        import re
        return set(re.findall(r"[a-zà-ỹ0-9]+", (text or "").lower()))

    @classmethod
    def _jaccard(cls, a: str, b: str) -> float:
        ta, tb = cls._norm_tokens(a), cls._norm_tokens(b)
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        return inter / (len(ta) + len(tb) - inter)

    def _coerce_bank_question(
        self, raw: dict, *, node_id: int, node_name: str,
        bloom_level: str, points: float = 10.0,
    ) -> dict | None:
        """Deterministic coercion of one generated question into the bank
        contract. Returns None when the output is unusable."""
        if not isinstance(raw, dict):
            return None
        text = str(raw.get("question_text") or "").strip()
        if len(text) < 8:
            return None

        raw_opts = raw.get("answer_options")
        if not isinstance(raw_opts, list):
            return None

        options: list[dict] = []
        correct_seen = False
        for i, opt in enumerate(raw_opts[:6]):
            if isinstance(opt, dict):
                otext = str(opt.get("text") or opt.get("option_text") or "").strip()
                if not otext:
                    continue
                is_correct = bool(opt.get("is_correct", opt.get("correct", False)))
                options.append({
                    "option_text": otext,
                    "is_correct": is_correct,
                    "order_index": len(options),
                    "blank_id": None,
                })
                if is_correct:
                    correct_seen = True
            elif isinstance(opt, str) and opt.strip():
                options.append({
                    "option_text": opt.strip(),
                    "is_correct": False,
                    "order_index": len(options),
                    "blank_id": None,
                })
            if len(options) >= 4:
                break

        q_type = str(raw.get("question_type") or "SINGLE_CHOICE").upper()
        if q_type not in ("SINGLE_CHOICE", "MULTIPLE_CHOICE"):
            q_type = "SINGLE_CHOICE"
        if len(options) < 2:
            return None

        # Enforce exactly one correct answer for SINGLE_CHOICE (deterministic).
        if q_type == "SINGLE_CHOICE":
            first_correct_fixed = False
            for o in options:
                if o["is_correct"] and not first_correct_fixed:
                    first_correct_fixed = True
                else:
                    o["is_correct"] = False
            if not first_correct_fixed:
                options[0]["is_correct"] = True

        explanation = str(raw.get("explanation") or raw.get("source_quote") or "").strip()

        return {
            "node_id": int(node_id),
            "question_type": q_type,
            "question_text": text,
            "points": points,
            "bloom_level": bloom_level,
            "difficulty": self._BLOOM_DIFFICULTY.get(bloom_level, "MEDIUM"),
            "answer_options": options,
            "correct_answers": [],
            "settings": {},
            "explanation": explanation[:2000],
            "source": "AI_GENERATED",
            "_node_name": node_name,
        }

    async def _generate_one_for_bank(
        self, node_id: int, node_name: str, bloom_level: str,
        language: str, exclude_samples: list[str],
    ) -> tuple[dict | None, str]:
        """Returns (coerced_question_or_None, error_reason)."""
        try:
            chunks = await rag_service.search_multilingual(
                query=node_name, course_id=None, node_id=node_id, top_k=4,
            )
            if not chunks:
                chunks = await rag_service.search_multilingual(
                    query=node_name, top_k=3,
                )
            context_texts = [c.chunk_text for c in chunks]
            if not context_texts:
                return None, f"no context for node {node_id}"

            messages = build_quiz_generation_prompt(
                bloom_level=bloom_level,
                context_chunks=context_texts,
                node_name=node_name,
                language=language,
                existing_questions=exclude_samples,
                assessment_purpose="formative",
            )
            result = await chat_complete_json(
                messages=messages, temperature=0.5, task=TASK_QUIZ_GEN,
            )
            if not isinstance(result, dict):
                return None, "non-object LLM response"
            q = self._coerce_bank_question(
                result, node_id=node_id, node_name=node_name, bloom_level=bloom_level,
            )
            if q is None:
                return None, "unusable structure"
            return q, ""
        except Exception as exc:  # noqa: BLE001 - per-question isolation
            logger.warning("bank gen failed node=%s bloom=%s: %s", node_id, bloom_level, exc)
            return None, str(exc)

    async def generate_for_bank(
        self,
        course_id: int,
        count: int = 10,
        bloom_levels: list[str] | None = None,
        language: str = "vi",
        exclude_questions: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        """
        Auto-select diverse nodes from the course knowledge graph, generate
        one classified question per selected (node, bloom) pair, dedupe
        against existing bank questions. Returns (questions, rejected_count).
        """
        count = max(1, min(30, int(count)))
        blooms = [b for b in (bloom_levels or BLOOM_LEVELS) if b in BLOOM_LEVELS] or BLOOM_LEVELS

        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT id, COALESCE(NULLIF(name_vi,''), name) AS name
                FROM knowledge_nodes
                WHERE course_id = $1
                ORDER BY RANDOM()
                LIMIT $2
                """,
                course_id, count * 2,
            )
        nodes = [(int(r["id"]), r["name"]) for r in rows]
        if not nodes:
            raise ValueError("Khóa học chưa có knowledge nodes để sinh đề.")

        excludes = [q for q in (exclude_questions or []) if q][:200]
        exclude_samples = excludes[-5:]

        plan = [
            (nodes[i % len(nodes)], blooms[i % len(blooms)])
            for i in range(count)
        ]

        tasks = [
            self._generate_one_for_bank(nid, name, bloom, language, exclude_samples)
            for (nid, name), bloom in plan
        ]
        results = await asyncio.gather(*tasks)

        seen_texts = list(excludes)
        questions: list[dict] = []
        rejected = 0
        for q, err in results:
            if q is None:
                rejected += 1
                logger.debug("bank gen skipped: %s", err)
                continue
            duplicate = any(
                self._jaccard(q["question_text"], prev) >= 0.8
                for prev in seen_texts
            )
            if duplicate:
                rejected += 1
                continue
            seen_texts.append(q["question_text"])
            questions.append(q)

        for i, q in enumerate(questions):
            q["order_index"] = i + 1
        logger.info(
            "generate_for_bank: %d generated, %d rejected (course=%d)",
            len(questions), rejected, course_id,
        )
        return questions, rejected

    async def _generate_single_with_semaphore(self, **kwargs) -> int:
        """Wraps _generate_single with the shared LLM semaphore."""
        async with _LLM_SEMAPHORE:
            return await self._generate_single(**kwargs)

    async def _generate_single(
        self, node_id, course_id, created_by, bloom_level, node_name, language, existing_questions,
        assessment_purpose="formative", teacher_instructions="",
    ) -> int:
        chunks = await rag_service.search_multilingual(
            query=node_name, course_id=course_id, node_id=node_id, top_k=4,
        )
        if not chunks:
            chunks = await rag_service.search_multilingual(
                query=node_name, course_id=course_id, top_k=3,
            )

        context_texts = [c.chunk_text for c in chunks]
        best_chunk_id = chunks[0].chunk_id if chunks else None

        if not context_texts:
            raise ValueError(f"No context chunks found for node {node_id}")

        messages = build_quiz_generation_prompt(
            bloom_level=bloom_level,
            context_chunks=context_texts,
            node_name=node_name,
            language=language,
            existing_questions=existing_questions[:5],
            assessment_purpose=assessment_purpose,
            teacher_instructions=teacher_instructions,
        )
        result = await chat_complete_json(
            messages=messages, model=settings.quiz_model, temperature=0.5,
            task=TASK_QUIZ_GEN,
        )
        # A bare-array or scalar response must fail with a CLEAN message -
        # the old f-string called result.keys() and raised AttributeError
        # while formatting the intended ValueError.
        if not isinstance(result, dict):
            raise ValueError(
                f"Invalid LLM response structure: expected object, got {type(result).__name__}"
            )

        if "question_text" not in result or "answer_options" not in result:
            raise ValueError(f"Invalid LLM response structure: {list(result.keys())}")

        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ai_quiz_generations
                    (node_id, course_id, created_by, bloom_level, question_text,
                     question_type, answer_options, explanation, source_quote,
                     source_chunk_id, language, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,'DRAFT')
                RETURNING id
                """,
                node_id, course_id, created_by, bloom_level,
                result["question_text"],
                result.get("question_type", "SINGLE_CHOICE"),
                __import__("json").dumps(result.get("answer_options", []), ensure_ascii=False),
                result.get("explanation", ""), result.get("source_quote", ""),
                best_chunk_id, language,
            )
        return row["id"]

    async def list_drafts(self, course_id: int, node_id: int | None = None) -> list[dict]:
        sql = """
            SELECT aiqg.*, kn.name AS node_name
            FROM ai_quiz_generations aiqg
            LEFT JOIN knowledge_nodes kn ON kn.id = aiqg.node_id
            WHERE aiqg.course_id = $1 AND aiqg.status = 'DRAFT'
        """
        params: list = [course_id]
        if node_id:
            sql += " AND aiqg.node_id = $2"
            params.append(node_id)
        sql += " ORDER BY aiqg.bloom_level, aiqg.created_at"

        async with get_ai_conn() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def approve_question(
        self, gen_id: int, reviewer_id: int, quiz_id: int, review_note: str = "",
    ) -> dict:
        import json as json_lib

        async with get_ai_conn() as conn:
            gen = await conn.fetchrow(
                "SELECT * FROM ai_quiz_generations WHERE id = $1", gen_id,
            )
        if not gen:
            raise ValueError(f"Generation {gen_id} not found")

        options = gen["answer_options"] or []
        if isinstance(options, str):
            options = json_lib.loads(options)

        async with get_ai_conn() as conn:
            await conn.execute(
                """
                UPDATE ai_quiz_generations
                SET status='APPROVED', reviewed_by=$1, reviewed_at=NOW(),
                    review_note=$2, updated_at=NOW()
                WHERE id=$3
                """,
                reviewer_id, review_note, gen_id,
            )

        return {
            "gen_id":        gen_id,
            "quiz_id":       quiz_id,
            "question_text": gen["question_text"],
            "question_type": gen["question_type"] or "SINGLE_CHOICE",
            "explanation":   gen["explanation"] or "",
            "answer_options": options,
            "node_id":       gen["node_id"],
            "bloom_level":   gen["bloom_level"],
            "source_chunk_id": gen["source_chunk_id"],
            "language":      gen["language"],
        }

    async def update_quiz_question_id(self, gen_id: int, quiz_question_id: int) -> None:
        async with get_ai_conn() as conn:
            await conn.execute(
                """
                UPDATE ai_quiz_generations
                SET status='PUBLISHED', quiz_question_id=$1, updated_at=NOW()
                WHERE id=$2
                """,
                quiz_question_id, gen_id,
            )

    async def reject_question(self, gen_id: int, reviewer_id: int, review_note: str) -> None:
        async with get_ai_conn() as conn:
            await conn.execute(
                """
                UPDATE ai_quiz_generations
                SET status='REJECTED', reviewed_by=$1, reviewed_at=NOW(),
                    review_note=$2, updated_at=NOW()
                WHERE id=$3
                """,
                reviewer_id, review_note, gen_id,
            )


# ── SM-2 Spaced Repetition ─────────────────────────────────────────────────────

class SpacedRepetitionService:
    MIN_EASINESS = 1.3

    def update(self, ef, interval, reps, quality):
        new_ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ef = max(self.MIN_EASINESS, new_ef)
        if quality < 3:
            new_interval, new_reps = 1, 0
        else:
            new_reps = reps + 1
            if   new_reps == 1: new_interval = 1
            elif new_reps == 2: new_interval = 6
            else:               new_interval = round(interval * new_ef)
        return new_ef, new_interval, new_reps

    async def record_response(
        self, student_id, question_id, course_id, node_id, quality,
    ) -> dict:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT easiness_factor, interval_days, repetitions
                FROM spaced_repetitions WHERE student_id=$1 AND question_id=$2
                """,
                student_id, question_id,
            )
            ef       = float(row["easiness_factor"]) if row else 2.5
            interval = int(row["interval_days"])      if row else 1
            reps     = int(row["repetitions"])         if row else 0

            new_ef, new_interval, new_reps = self.update(ef, interval, reps, quality)
            next_date  = date.today() + timedelta(days=new_interval)
            is_correct = 1 if quality >= 3 else 0
            is_wrong   = 1 if quality < 3  else 0

            await conn.execute(
                """
                INSERT INTO spaced_repetitions
                       (student_id, question_id, node_id, course_id,
                        easiness_factor, interval_days, repetitions,
                        quality_last, next_review_date, last_reviewed_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                ON CONFLICT (student_id, question_id) DO UPDATE SET
                    easiness_factor  = $5, interval_days    = $6,
                    repetitions      = $7, quality_last     = $8,
                    next_review_date = $9, last_reviewed_at = NOW(),
                    updated_at       = NOW()
                """,
                student_id, question_id, node_id, course_id,
                new_ef, new_interval, new_reps, quality, next_date,
            )

            await conn.execute(
                """
                INSERT INTO student_knowledge_progress
                       (student_id, node_id, course_id, total_attempts, correct_count,
                        wrong_count, mastery_level, last_tested_at)
                VALUES ($1, $2, $3, 1, $4, $5, $6, NOW())
                ON CONFLICT (student_id, node_id) DO UPDATE SET
                    total_attempts = student_knowledge_progress.total_attempts + 1,
                    correct_count  = student_knowledge_progress.correct_count + $4,
                    wrong_count    = student_knowledge_progress.wrong_count + $5,
                    mastery_level  = (student_knowledge_progress.correct_count + $4)::FLOAT
                                     / (student_knowledge_progress.total_attempts + 1),
                    last_tested_at = NOW(),
                    updated_at     = NOW()
                """,
                student_id, node_id, course_id, is_correct, is_wrong, float(is_correct),
            )

        return {
            "next_review_date": next_date.isoformat(),
            "interval_days":    new_interval,
            "easiness_factor":  round(new_ef, 2),
            "repetitions":      new_reps,
        }

    async def get_due_reviews(self, student_id, course_id, limit=20) -> list[dict]:
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT sr.question_id, sr.node_id, sr.next_review_date,
                       sr.interval_days, sr.repetitions, kn.name AS node_name
                FROM spaced_repetitions sr
                LEFT JOIN knowledge_nodes kn ON kn.id = sr.node_id
                WHERE sr.student_id = $1 AND sr.course_id = $2
                  AND sr.next_review_date <= CURRENT_DATE
                ORDER BY sr.next_review_date ASC, sr.easiness_factor ASC
                LIMIT $3
                """,
                student_id, course_id, limit,
            )
        return [dict(r) for r in rows]

    async def get_review_stats(self, student_id, course_id) -> dict:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE next_review_date <= CURRENT_DATE) AS due_today,
                    COUNT(*) FILTER (WHERE next_review_date > CURRENT_DATE)  AS upcoming,
                    COUNT(*)                                                   AS total_tracked,
                    AVG(easiness_factor)                                       AS avg_easiness,
                    AVG(repetitions)                                           AS avg_repetitions
                FROM spaced_repetitions
                WHERE student_id = $1 AND course_id = $2
                """,
                student_id, course_id,
            )
        return dict(row) if row else {}

    async def get_total_due_reviews(self, student_id: int) -> int:
        async with get_ai_conn() as conn:
            val = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM spaced_repetitions
                WHERE student_id = $1 AND next_review_date <= CURRENT_DATE
                """,
                student_id,
            )
        return val or 0



quiz_gen_service = QuizGenerationService()
sr_service       = SpacedRepetitionService()
