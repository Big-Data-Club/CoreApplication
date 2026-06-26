"""
ai-service/app/services/micro_quiz_service.py

Generate node-comprehensive MCQ quizzes from teacher-uploaded files or
YouTube URLs.  Each knowledge node produces one quiz; the number of
questions equals the number of document chunks for that node, ensuring
full coverage.

Data flow
---------
  1. Reuse the auto-index + node/chunk pipeline from micro_lesson_service.
  2. For each node, iterate its chunks.  Assign Bloom levels round-robin
     with LLM fallback (if the chunk can't support the requested level,
     the LLM may downgrade and report the actual level used).
  3. Per-chunk LLM call -> structured JSON question (no Markdown wrapper).
  4. POST the quiz array back to the LMS via HTTP callback.

All question/option/explanation text may contain Markdown (images, LaTeX,
etc.) but the top-level structure is always strict JSON.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_MICRO_QUIZ_GEN

logger = logging.getLogger(__name__)
settings = get_settings()

BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

_LLM_SEMAPHORE = asyncio.Semaphore(4)


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class QuizQuestion:
    question: str
    options: list[dict]          # [{text, is_correct}, ...]
    explanation: str
    bloom_level: str


@dataclass
class GeneratedQuiz:
    title: str
    summary: str
    questions: list[QuizQuestion]
    order_index: int
    node_id: Optional[int] = None


@dataclass
class QuizGenerationResult:
    job_id: int
    course_id: int
    quizzes: list[GeneratedQuiz]
    language: str


# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_VI = (
    "You are an expert quiz designer. Your job is to create a multiple-choice "
    "question (4 options, exactly 1 correct) based on the provided content. "
    "Even though this system instruction is in English, you MUST generate all output fields "
    "(question, options, and explanation) in Vietnamese. "
    "Always return JSON matching the requested schema, with no extra commentary."
)

_SYSTEM_PROMPT_EN = (
    "You are an expert quiz designer. Your job is to create a multiple-choice "
    "question (4 options, exactly 1 correct) based on the provided content. "
    "Always return JSON matching the requested schema, with no extra commentary."
)


# ── Service ──────────────────────────────────────────────────────────────────

class MicroQuizService:

    async def generate_from_file(
        self,
        *,
        job_id: int,
        course_id: int,
        section_id: Optional[int],
        source_content_id: Optional[int],
        source_file_path: str,
        source_file_type: str,
        language: str = "vi",
    ) -> QuizGenerationResult:
        if not source_content_id:
            await self._post_status(job_id, "failed", 0, "missing_content_id", 0,
                                    "Yêu cầu phải có source_content_id")
            return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=[], language=language)

        await self._post_status(job_id, "processing", 5, "checking_index", 0, "")

        from app.core.database import get_ai_conn
        from app.services.auto_index_service import auto_index_service

        is_indexed = False
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM knowledge_nodes WHERE source_content_id=$1 LIMIT 1",
                source_content_id,
            )
            is_indexed = row is not None

        if not is_indexed:
            await self._post_status(job_id, "processing", 10, "auto_indexing", 0, "")
            file_bytes = await auto_index_service._download_bytes(source_file_path)
            if not file_bytes:
                await self._post_status(job_id, "failed", 0, "download_failed", 0,
                                        "Không tải được file nguồn")
                return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=[], language=language)

            from app.services.auto_index_service import _detect_file_type
            file_type = _detect_file_type(source_file_path, source_file_type)
            try:
                if file_type == "text":
                    text_content = file_bytes.decode("utf-8", errors="replace")
                    await auto_index_service.auto_index_text(
                        content_id=source_content_id, course_id=course_id,
                        title="", text_content=text_content,
                    )
                else:
                    await auto_index_service.auto_index(
                        content_id=source_content_id, course_id=course_id,
                        file_url=source_file_path, content_type=file_type,
                        file_bytes=file_bytes,
                    )
            except Exception as exc:
                logger.error("Auto index failed: %s", exc)
                await self._post_status(job_id, "failed", 0, "index_failed", 0, str(exc))
                return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=[], language=language)

        return await self._generate_quizzes(job_id, course_id, section_id, source_content_id, language)

    async def generate_from_youtube(
        self,
        *,
        job_id: int,
        course_id: int,
        section_id: Optional[int],
        source_content_id: Optional[int],
        youtube_url: str,
        language: str = "vi",
    ) -> QuizGenerationResult:
        if not source_content_id:
            await self._post_status(job_id, "failed", 0, "missing_content_id", 0,
                                    "Yêu cầu phải có source_content_id")
            return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=[], language=language)

        await self._post_status(job_id, "processing", 5, "checking_index", 0, "")

        from app.core.database import get_ai_conn
        from app.services.auto_index_service import auto_index_service

        is_indexed = False
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM knowledge_nodes WHERE source_content_id=$1 LIMIT 1",
                source_content_id,
            )
            is_indexed = row is not None

        if not is_indexed:
            await self._post_status(job_id, "processing", 10, "auto_indexing", 0, "")
            try:
                await auto_index_service.auto_index(
                    content_id=source_content_id, course_id=course_id,
                    file_url=youtube_url, content_type="video/youtube",
                    file_bytes=b"",
                )
            except Exception as exc:
                logger.error("Auto index failed: %s", exc)
                await self._post_status(job_id, "failed", 0, "index_failed", 0, str(exc))
                return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=[], language=language)

        return await self._generate_quizzes(job_id, course_id, section_id, source_content_id, language)

    # ── Shared core pipeline ────────────────────────────────────────────

    async def _generate_quizzes(
        self,
        job_id: int,
        course_id: int,
        section_id: Optional[int],
        source_content_id: Optional[int],
        language: str,
    ) -> QuizGenerationResult:
        await self._post_status(job_id, "processing", 50, "fetching_nodes", 0, "")
        nodes_with_chunks = await self._fetch_nodes_and_chunks(source_content_id)
        if not nodes_with_chunks:
            await self._post_status(job_id, "failed", 0, "no_nodes", 0,
                                    "Không tìm thấy Node kiến thức nào từ tài liệu này")
            return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=[], language=language)

        await self._post_status(job_id, "processing", 60, "generating_quizzes", len(nodes_with_chunks), "")

        quizzes: list[GeneratedQuiz] = []
        for i, item in enumerate(nodes_with_chunks):
            prev_node = nodes_with_chunks[i - 1]["node"] if i > 0 else None
            quiz = await self._generate_quiz_for_node(
                node=item["node"],
                chunks=item["chunks"],
                language=language,
                order_index=i,
                prev_node=prev_node,
            )
            if quiz:
                quizzes.append(quiz)
            progress = 60 + int(30 * (i + 1) / len(nodes_with_chunks))
            await self._post_status(job_id, "processing", progress,
                                    "generating_quizzes", len(nodes_with_chunks), "")

        if not quizzes:
            await self._post_status(job_id, "failed", 0, "gen_failed", 0,
                                    "LLM không tạo được bài quiz nào")
            return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=[], language=language)

        await self._post_status(job_id, "processing", 95, "saving", len(quizzes), "")
        await self._post_quizzes(job_id, course_id, section_id, source_content_id, quizzes, language)
        await self._post_status(job_id, "completed", 100, "done", len(quizzes), "")
        return QuizGenerationResult(job_id=job_id, course_id=course_id, quizzes=quizzes, language=language)

    async def _fetch_nodes_and_chunks(self, source_content_id: int) -> list[dict]:
        """Fetch knowledge nodes and their chunks for the given content, sorted logically."""
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            # 1. Fetch nodes with their minimum chunk index to preserve document logical flow
            nodes_rows = await conn.fetch(
                """
                SELECT kn.id, kn.name, kn.description, COALESCE(MIN(dc.chunk_index), 999999) as min_chunk_idx
                FROM knowledge_nodes kn
                LEFT JOIN document_chunks dc ON dc.node_id = kn.id
                WHERE kn.source_content_id = $1
                GROUP BY kn.id, kn.name, kn.description
                """,
                source_content_id
            )
            if not nodes_rows:
                return []

            # 2. Fetch prerequisite relationships between these nodes
            prereq_rows = await conn.fetch(
                """
                SELECT knr.source_node_id, knr.target_node_id
                FROM knowledge_node_relations knr
                JOIN knowledge_nodes kn_src ON knr.source_node_id = kn_src.id
                JOIN knowledge_nodes kn_tgt ON knr.target_node_id = kn_tgt.id
                WHERE kn_src.source_content_id = $1 AND kn_tgt.source_content_id = $1
                  AND knr.relation_type = 'prerequisite'
                """,
                source_content_id
            )

            # 3. Fetch chunks in order
            chunks_rows = await conn.fetch(
                "SELECT node_id, chunk_text FROM document_chunks WHERE content_id=$1 ORDER BY chunk_index",
                source_content_id
            )

            # Organize data
            node_map = {}
            for row in nodes_rows:
                node_map[row["id"]] = {
                    "node": {
                        "id": row["id"], 
                        "name": row["name"], 
                        "description": row["description"],
                        "min_chunk_idx": row["min_chunk_idx"]
                    },
                    "chunks": [],
                }

            for row in chunks_rows:
                nid = row["node_id"]
                if nid in node_map:
                    node_map[nid]["chunks"].append(row["chunk_text"])

            # Keep only nodes that actually have chunks mapped to them
            valid_items = [n for n in node_map.values() if n["chunks"]]
            if not valid_items:
                return []

            # Extract nodes and relations for Topological Sorting
            nodes_to_sort = [item["node"] for item in valid_items]
            prereqs = [(row["source_node_id"], row["target_node_id"]) for row in prereq_rows]

            node_ids = {n["id"] for n in nodes_to_sort}
            adj = {nid: [] for nid in node_ids}
            in_degree = {nid: 0 for nid in node_ids}

            for u, v in prereqs:
                if u in node_ids and v in node_ids:
                    adj[u].append(v)
                    in_degree[v] += 1

            # Multi-criteria Queue: zero in-degree nodes sorted by their first appearance in document
            sources = [nid for nid in node_ids if in_degree[nid] == 0]
            sources.sort(key=lambda nid: node_map[nid]["node"]["min_chunk_idx"])

            sorted_node_ids = []
            while sources:
                curr_id = sources.pop(0)
                sorted_node_ids.append(curr_id)

                for neighbor in adj[curr_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        sources.append(neighbor)

                sources.sort(key=lambda nid: node_map[nid]["node"]["min_chunk_idx"])

            # Cycle fallback
            if len(sorted_node_ids) < len(nodes_to_sort):
                sorted_set = set(sorted_node_ids)
                remaining = [nid for nid in node_ids if nid not in sorted_set]
                remaining.sort(key=lambda nid: node_map[nid]["node"]["min_chunk_idx"])
                sorted_node_ids.extend(remaining)

            return [node_map[nid] for nid in sorted_node_ids]

    async def _generate_quiz_for_node(
        self,
        node: dict,
        chunks: list[str],
        language: str,
        order_index: int,
        prev_node: Optional[dict] = None,
    ) -> Optional[GeneratedQuiz]:
        """Generate one quiz (N questions) for a single knowledge node."""
        questions: list[QuizQuestion] = []

        # Create tasks for all chunks with semaphore-controlled concurrency
        tasks = []
        for chunk_idx, chunk_text in enumerate(chunks):
            bloom_level = BLOOM_LEVELS[chunk_idx % len(BLOOM_LEVELS)]
            
            # Make the last question of the quiz an integrative question if we have a prev_node
            is_integrative = False
            if prev_node and chunk_idx == len(chunks) - 1:
                is_integrative = True
                
            tasks.append(
                self._generate_single_question(
                    chunk_text=chunk_text,
                    node_name=node["name"],
                    bloom_level=bloom_level,
                    language=language,
                    prev_node=prev_node if is_integrative else None,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                logger.error("Question gen failed for node %d: %s", node["id"], res)
            elif res is not None:
                questions.append(res)

        if not questions:
            return None

        title_prefix = "Bài kiểm tra" if language == "vi" else "Quiz"
        return GeneratedQuiz(
            title=f"{title_prefix}: {node['name']}"[:500],
            summary=(node.get("description") or "")[:500],
            questions=questions,
            order_index=order_index,
            node_id=node["id"],
        )

    async def _generate_single_question(
        self,
        chunk_text: str,
        node_name: str,
        bloom_level: str,
        language: str,
        prev_node: Optional[dict] = None,
    ) -> Optional[QuizQuestion]:
        """Generate a single MCQ from one chunk at a specified Bloom level."""
        async with _LLM_SEMAPHORE:
            truncated = chunk_text[:6000]

            sys_msg = _SYSTEM_PROMPT_VI if language == "vi" else _SYSTEM_PROMPT_EN

            lang_name = "Vietnamese" if language == "vi" else "English"

            integrative_prompt = ""
            if prev_node:
                integrative_prompt = (
                    f"\n## SPECIAL REQUIREMENT: INTEGRATIVE KNOWLEDGE QUESTION\n"
                    f"This question must be an integrative, comparative, or logical connection question between:\n"
                    f"1. The current topic: '{node_name}' (based on the source content below)\n"
                    f"2. The previously learned topic: '{prev_node['name']}' (Description: {prev_node['description']})\n"
                    f"The goal is to test the student's ability to logically connect new and old concepts. "
                    f"Write the question, options, and explanation in {lang_name}. "
                    f"The explanation field must explicitly detail this logical connection.\n"
                )

            user_msg = (
                f"Create exactly 1 multiple-choice question (MCQ) at Bloom's level [{bloom_level}] "
                f"for the topic: {node_name}\n\n"
                f"{integrative_prompt}"
                f"## RULES\n"
                f"1. The question must be DIRECTLY based on the SOURCE CONTENT below.\n"
                f"2. Provide exactly 4 options (A, B, C, D) in the format 'A. [content]', 'B. [content]', etc., with exactly 1 correct option.\n"
                f"3. Write a brief explanation why the selected answer is correct.\n"
                f"4. If the content is too academic or simple to support a question at [{bloom_level}], "
                f"automatically downgrade/adjust to a more suitable level and record the actual level in the 'bloom_level' field.\n"
                f"5. All text fields ('question', option text, 'explanation') MUST be written in {lang_name}.\n"
                f"6. Text fields may contain Markdown (images, formulas if present in content).\n\n"
                f"## REQUIRED JSON SCHEMA\n"
                "{\n"
                f'  "question": "Question text in {lang_name}...",\n'
                f'  "options": [\n'
                f'    {{"text": "A. Option text in {lang_name}", "is_correct": false}},\n'
                f'    {{"text": "B. Option text in {lang_name}", "is_correct": true}},\n'
                f'    {{"text": "C. Option text in {lang_name}", "is_correct": false}},\n'
                f'    {{"text": "D. Option text in {lang_name}", "is_correct": false}}\n'
                f'  ],\n'
                f'  "explanation": "Explanation in {lang_name} why B is correct...",\n'
                f'  "bloom_level": "{bloom_level}"\n'
                "}\n\n"
                f"## SOURCE CONTENT\n"
                f"{truncated}\n"
            )


            try:
                result = await chat_complete_json(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=settings.quiz_model,
                    temperature=0.4,
                    max_tokens=2000,
                    task=TASK_MICRO_QUIZ_GEN,
                )
            except Exception as exc:
                logger.error("Quiz question LLM failed: %s", exc)
                return None

            if not isinstance(result, dict):
                return None

            question_text = (result.get("question") or "").strip()
            options = result.get("options") or []
            if not question_text or not isinstance(options, list) or len(options) < 2:
                return None

            # Validate and normalise options
            normalised = []
            has_correct = False
            for opt in options[:4]:
                if not isinstance(opt, dict):
                    continue
                text = (opt.get("text") or "").strip()
                is_correct = bool(opt.get("is_correct", False))
                if text:
                    normalised.append({"text": text, "is_correct": is_correct})
                    if is_correct:
                        has_correct = True

            if len(normalised) < 2 or not has_correct:
                return None

            actual_bloom = (result.get("bloom_level") or bloom_level).strip().lower()
            if actual_bloom not in BLOOM_LEVELS:
                actual_bloom = bloom_level

            return QuizQuestion(
                question=question_text,
                options=normalised,
                explanation=(result.get("explanation") or "").strip()[:1000],
                bloom_level=actual_bloom,
            )

    # ── HTTP callbacks into LMS ──────────────────────────────────────────

    async def _post_quizzes(
        self,
        job_id: int,
        course_id: int,
        section_id: Optional[int],
        source_content_id: Optional[int],
        quizzes: list[GeneratedQuiz],
        language: str,
    ) -> None:
        import json as json_lib
        payload = {
            "job_id": job_id,
            "course_id": course_id,
            "section_id": section_id,
            "source_content_id": source_content_id,
            "language": language,
            "quizzes": [
                {
                    "title": q.title,
                    "summary": q.summary,
                    "questions_json": [
                        {
                            "question": qn.question,
                            "options": qn.options,
                            "explanation": qn.explanation,
                            "bloom_level": qn.bloom_level,
                        }
                        for qn in q.questions
                    ],
                    "questions_count": len(q.questions),
                    "order_index": q.order_index,
                    "node_id": q.node_id,
                }
                for q in quizzes
            ],
        }
        await self._lms_post("/api/v1/internal/micro-quizzes/quizzes", payload)

    async def _post_status(
        self, job_id: int, status: str, progress: int,
        stage: str, quizzes_count: int, error: str,
    ) -> None:
        await self._lms_post("/api/v1/internal/micro-quizzes/status", {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "stage": stage,
            "quizzes_count": quizzes_count,
            "error": error,
        })

    async def _lms_post(self, path: str, body: dict) -> None:
        url = settings.lms_service_url.rstrip("/") + path
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url, json=body,
                    headers={"X-API-Secret": settings.ai_service_secret},
                )
                if resp.status_code >= 400:
                    logger.warning("LMS callback %s -> %d: %s",
                                   path, resp.status_code, resp.text[:200])
        except Exception as exc:
            logger.error("LMS callback %s failed: %s", path, exc)


# Singleton
micro_quiz_service = MicroQuizService()
