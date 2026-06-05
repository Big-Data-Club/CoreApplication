"""
ai-service/app/services/section_overview_service.py

Generate a section-level overview lesson (Markdown) and a comprehensive
overview quiz (N MCQs) from ALL indexed content in the section.

Data flow
---------
  1. Accept a list of indexed content items for the section.
  2. Fetch ALL knowledge_nodes whose source_content_id is in that list.
  3. Topologically sort the nodes (prerequisite graph) so the lesson
     narrative follows a logical learning order.
  4. Overview Lesson – one LLM call with all node summaries concatenated;
     the LLM synthesises a coherent Markdown narrative that connects topics.
  5. Overview Quiz  – one (or two) LLM call(s) producing exactly
     question_count MCQs distributed proportionally across nodes.
     Integrative questions that span multiple topics are encouraged.
  6. POST lesson + quiz back to the LMS via internal HTTP callback.
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_SECTION_OVERVIEW_GEN

logger = logging.getLogger(__name__)
settings = get_settings()

_LLM_SEMAPHORE = asyncio.Semaphore(4)

BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ContentRef:
    content_id: int
    title: str
    content_type: str


@dataclass
class OverviewLesson:
    title: str
    summary: str
    markdown_content: str
    references: list[ContentRef]


@dataclass
class OverviewQuestion:
    question: str
    options: list[dict]           # [{text, is_correct}, ...]
    explanation: str
    bloom_level: str
    reference_content_ids: list[int]


@dataclass
class OverviewQuiz:
    title: str
    summary: str
    question_count: int
    questions: list[OverviewQuestion]
    references: list[ContentRef]


# ── System prompts ────────────────────────────────────────────────────────────

_LESSON_SYSTEM_VI = (
    "Bạn là một chuyên gia giáo dục. Nhiệm vụ của bạn là tổng hợp các chủ đề kiến thức "
    "thành một bài học tổng quan mạch lạc bằng tiếng Việt dưới dạng Markdown. "
    "Hãy trả về JSON đúng theo schema được yêu cầu, không thêm bất kỳ bình luận nào bên ngoài JSON."
)

_LESSON_SYSTEM_EN = (
    "You are an expert educator. Your task is to synthesise knowledge topics "
    "into a coherent overview lesson in English using Markdown. "
    "Always return JSON matching the requested schema, with no extra commentary."
)

_QUIZ_SYSTEM_VI = (
    "Bạn là chuyên gia thiết kế bài kiểm tra. Nhiệm vụ của bạn là tạo các câu hỏi trắc nghiệm "
    "toàn diện bao phủ toàn bộ chương học. "
    "Hãy trả về JSON đúng theo schema được yêu cầu, không thêm bất kỳ bình luận nào bên ngoài JSON."
)

_QUIZ_SYSTEM_EN = (
    "You are an expert quiz designer. Your task is to create comprehensive multiple-choice questions "
    "covering the entire section broadly. "
    "Always return JSON matching the requested schema, with no extra commentary."
)


# ── Service ───────────────────────────────────────────────────────────────────

class SectionOverviewService:

    async def generate(
        self,
        *,
        job_id: int,
        section_id: int,
        course_id: int,
        question_count: int,
        language: str,
        contents_info: list[dict],   # [{content_id, title, content_type, description}]
    ) -> None:
        """
        Main entry-point.  Called as a FastAPI BackgroundTask.
        Posts status updates and final results back to the LMS.
        """
        import datetime
        lang = language or "vi"
        job_logs = []

        def add_log(msg: str):
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            entry = f"[{ts}] {msg}"
            job_logs.append(entry)
            logger.info("Job %d: %s", job_id, entry)

        add_log(f"Bắt đầu khởi tạo tác vụ tổng quan chương (Section ID: {section_id}, Số câu hỏi: {question_count}, Ngôn ngữ: {lang})")

        if not contents_info:
            add_log("Thất bại: Không có nội dung nào được cung cấp")
            await self._post_status(job_id, "failed", 0, "no_contents",
                                    "Không có nội dung nào được cung cấp", "\n".join(job_logs))
            return

        content_ids = [c["content_id"] for c in contents_info]
        add_log(f"Danh sách {len(content_ids)} tài liệu liên quan: {content_ids}")

        # Build a lookup map: content_id → {title, content_type}
        content_map: dict[int, dict] = {
            c["content_id"]: {"title": c.get("title", ""), "content_type": c.get("content_type", "")}
            for c in contents_info
        }

        # ── 1. Fetch all nodes ────────────────────────────────────────────────
        add_log("Đang truy vấn các Knowledge Nodes từ cơ sở dữ liệu AI...")
        await self._post_status(job_id, "processing", 10, "fetching_nodes", "", "\n".join(job_logs))
        nodes_with_chunks = await self._fetch_all_nodes(content_ids)

        if not nodes_with_chunks:
            add_log("Thất bại: Không tìm thấy Knowledge Node nào liên kết với các tài liệu trên")
            await self._post_status(job_id, "failed", 0, "no_nodes",
                                    "Không tìm thấy Knowledge Node nào từ các nội dung này", "\n".join(job_logs))
            return

        add_log(f"Truy xuất thành công {len(nodes_with_chunks)} Knowledge Nodes (đã được sắp xếp topo).")
        add_log("Bắt đầu quá trình sinh bài học tổng quan (Lesson overview)...")
        await self._post_status(job_id, "processing", 25, "generating_lesson", "", "\n".join(job_logs))

        # ── 2. Generate overview lesson ───────────────────────────────────────
        try:
            lesson = await self._generate_lesson(
                nodes_with_chunks=nodes_with_chunks,
                content_map=content_map,
                section_id=section_id,
                language=lang,
                job_id=job_id,
                add_log=add_log,
                job_logs=job_logs,
            )
            add_log("Đã hoàn thành sinh bài học tổng quan thành công!")
        except Exception as exc:
            logger.error("Section overview lesson generation failed: %s", exc)
            add_log(f"Lỗi khi sinh bài học: {exc}")
            await self._post_status(job_id, "failed", 0, "lesson_failed", str(exc)[:300], "\n".join(job_logs))
            return

        add_log("Bắt đầu quá trình sinh câu hỏi trắc nghiệm tổng quan (Quiz overview)...")
        await self._post_status(job_id, "processing", 55, "generating_quiz", "", "\n".join(job_logs))

        # ── 3. Generate overview quiz ─────────────────────────────────────────
        try:
            quiz = await self._generate_quiz(
                nodes_with_chunks=nodes_with_chunks,
                content_map=content_map,
                question_count=question_count,
                section_id=section_id,
                language=lang,
                job_id=job_id,
                add_log=add_log,
                job_logs=job_logs,
            )
            add_log("Đã hoàn thành sinh câu hỏi trắc nghiệm tổng quan thành công!")
        except Exception as exc:
            logger.error("Section overview quiz generation failed: %s", exc)
            add_log(f"Lỗi khi sinh quiz: {exc}")
            await self._post_status(job_id, "failed", 0, "quiz_failed", str(exc)[:300], "\n".join(job_logs))
            return

        add_log("Đang gửi kết quả bài học và quiz về server LMS...")
        await self._post_status(job_id, "processing", 90, "saving", "", "\n".join(job_logs))

        # ── 4. POST results to LMS ────────────────────────────────────────────
        await self._post_results(
            job_id=job_id,
            section_id=section_id,
            course_id=course_id,
            language=lang,
            lesson=lesson,
            quiz=quiz,
        )

        add_log("Tác vụ sinh tổng quan chương hoàn tất thành công!")
        await self._post_status(job_id, "completed", 100, "done", "", "\n".join(job_logs))

    async def _chat_complete_json_with_retry(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2500,
        task: str = "",
        add_log = None,
        max_retries: int = 3,
    ) -> dict:
        """
        Call chat_complete_json with exponential backoff on failure.
        """
        import asyncio
        delay = 2.0
        for attempt in range(max_retries + 1):
            try:
                result = await chat_complete_json(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task=task,
                )
                if isinstance(result, dict):
                    return result
                raise ValueError(f"LLM returned invalid response type: {type(result)}")
            except Exception as exc:
                if attempt == max_retries:
                    if add_log:
                        add_log(f"Thất bại: LLM Call không thành công sau {max_retries} lần thử lại: {exc}")
                    raise exc
                if add_log:
                    add_log(f"Cảnh báo: LLM Call gặp lỗi ({exc}). Đang tự động thử lại lần {attempt + 1}/{max_retries} sau {delay}s...")
                await asyncio.sleep(delay)
                delay *= 2.0
        return {}

    # ── Node fetching + topological sort ──────────────────────────────────────

    async def _fetch_all_nodes(self, content_ids: list[int]) -> list[dict]:
        """
        Fetch all knowledge nodes whose source_content_id is in *content_ids*,
        attach their chunks, and return them in topological (prerequisite) order.
        Each item: {node: {id, name, description, source_content_id, min_chunk_idx}, chunks: [str]}
        """
        if not content_ids:
            return []

        from app.core.database import get_ai_conn

        async with get_ai_conn() as conn:
            # Parameterised ANY($1) requires passing a list; asyncpg accepts it
            nodes_rows = await conn.fetch(
                """
                SELECT kn.id,
                       kn.name,
                       kn.description,
                       kn.source_content_id,
                       COALESCE(MIN(dc.chunk_index), 999999) AS min_chunk_idx
                FROM knowledge_nodes kn
                LEFT JOIN document_chunks dc ON dc.node_id = kn.id
                WHERE kn.source_content_id = ANY($1::int[])
                GROUP BY kn.id, kn.name, kn.description, kn.source_content_id
                """,
                content_ids,
            )

            if not nodes_rows:
                return []

            all_node_ids = [r["id"] for r in nodes_rows]

            # Prerequisite edges between these nodes
            prereq_rows = await conn.fetch(
                """
                SELECT knr.source_node_id, knr.target_node_id
                FROM knowledge_node_relations knr
                WHERE knr.source_node_id = ANY($1::int[])
                  AND knr.target_node_id = ANY($1::int[])
                  AND knr.relation_type = 'prerequisite'
                """,
                all_node_ids,
            )

            # All chunks for the nodes (ordered by chunk_index within each content)
            chunks_rows = await conn.fetch(
                """
                SELECT dc.node_id, dc.chunk_text
                FROM document_chunks dc
                WHERE dc.node_id = ANY($1::int[])
                ORDER BY dc.content_id, dc.chunk_index
                """,
                all_node_ids,
            )

        # Build node_map
        node_map: dict[int, dict] = {}
        for row in nodes_rows:
            node_map[row["id"]] = {
                "node": {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "source_content_id": row["source_content_id"],
                    "min_chunk_idx": row["min_chunk_idx"],
                },
                "chunks": [],
            }

        for row in chunks_rows:
            nid = row["node_id"]
            if nid in node_map:
                node_map[nid]["chunks"].append(row["chunk_text"])

        # Keep only nodes with at least one chunk
        valid_items = [v for v in node_map.values() if v["chunks"]]
        if not valid_items:
            return []

        # ── Topological sort ────────────────────────────────────────────────
        node_ids = {item["node"]["id"] for item in valid_items}
        adj: dict[int, list[int]] = {nid: [] for nid in node_ids}
        in_degree: dict[int, int] = {nid: 0 for nid in node_ids}

        for row in prereq_rows:
            u, v = row["source_node_id"], row["target_node_id"]
            if u in node_ids and v in node_ids:
                adj[u].append(v)
                in_degree[v] += 1

        sources = sorted(
            [nid for nid in node_ids if in_degree[nid] == 0],
            key=lambda nid: node_map[nid]["node"]["min_chunk_idx"],
        )

        sorted_ids: list[int] = []
        while sources:
            curr = sources.pop(0)
            sorted_ids.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    sources.append(neighbor)
            sources.sort(key=lambda nid: node_map[nid]["node"]["min_chunk_idx"])

        # Cycle fallback
        if len(sorted_ids) < len(valid_items):
            sorted_set = set(sorted_ids)
            remaining = sorted(
                [nid for nid in node_ids if nid not in sorted_set],
                key=lambda nid: node_map[nid]["node"]["min_chunk_idx"],
            )
            sorted_ids.extend(remaining)

        return [node_map[nid] for nid in sorted_ids]

    # ── Overview lesson generation ────────────────────────────────────────────

    async def _verify_and_refine_lesson(
        self,
        *,
        title: str,
        summary: str,
        markdown_content: str,
        references: list[ContentRef],
        language: str,
        section_id: int,
        add_log,
    ) -> tuple[str, str, str]:
        """
        Runs a verifier agent to polish the synthesized lesson, verifying references
        and formatting.
        """
        add_log("Lesson Verifier Agent: Đang bắt đầu kiểm tra chất lượng và tinh chỉnh bài học...")
        lang_name = "Vietnamese" if language == "vi" else "English"
        sys_msg = _LESSON_SYSTEM_VI if language == "vi" else _LESSON_SYSTEM_EN
        
        ref_list_str = "\n".join(
            f"- content_id={r.content_id}, title=\"{r.title}\""
            for r in references
        )

        user_msg = (
            f"## TASK: Verify and Refine Overview Lesson\n\n"
            f"You are a Quality Control (QC) agent. Review the following draft of the section overview lesson "
            f"for Section ID {section_id} and refine it for maximum clarity, pedagogical quality, and smooth transitions.\n\n"
            f"Please verify the following guidelines:\n"
            f"1. Structure: Ensure proper Markdown headers (using #, ##, ###), clear paragraph structures, and list bullet points.\n"
            f"2. Tone: Keep it highly engaging, educational, and professional.\n"
            f"3. References: Ensure any resource mentions or links utilize valid content IDs from: \n{ref_list_str}.\n"
            f"4. Format: Return the output as JSON matching the exact required schema.\n\n"
            f"## REQUIRED JSON SCHEMA\n"
            "{\n"
            f'  "title": "Polished title in {lang_name}",\n'
            f'  "summary": "Polished 2-3 sentence summary in {lang_name}",\n'
            f'  "markdown_content": "Polished Markdown lesson content in {lang_name}"\n'
            "}\n\n"
            f"## ORIGINAL DRAFT TO REFINE\n"
            f"Title: {title}\n"
            f"Summary: {summary}\n"
            f"Markdown Content:\n{markdown_content}\n"
        )

        try:
            async with _LLM_SEMAPHORE:
                result = await self._chat_complete_json_with_retry(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=settings.quiz_model,
                    temperature=0.3,
                    max_tokens=4000,
                    task=TASK_SECTION_OVERVIEW_GEN,
                    add_log=add_log,
                )

            if not isinstance(result, dict) or "markdown_content" not in result:
                add_log("Lesson Verifier Agent: Cảnh báo - Phản hồi QC không hợp lệ. Giữ lại bản gốc.")
                return title, summary, markdown_content

            v_title = (result.get("title") or "").strip() or title
            v_summary = (result.get("summary") or "").strip() or summary
            v_md = (result.get("markdown_content") or "").strip() or markdown_content

            add_log("Lesson Verifier Agent: Đã kiểm tra và tinh chỉnh bài học thành công!")
            return v_title, v_summary, v_md
        except Exception as exc:
            logger.error("Lesson verifier failed: %s", exc)
            add_log(f"Lesson Verifier Agent: Thất bại do lỗi ({exc}). Sử dụng bản nháp coordinator gốc.")
            return title, summary, markdown_content

    async def _generate_lesson(
        self,
        nodes_with_chunks: list[dict],
        content_map: dict[int, dict],
        section_id: int,
        language: str,
        job_id: int,
        add_log,
        job_logs: list[str],
    ) -> OverviewLesson:
        """
        Build one coherent Markdown lesson from all node summaries/chunks.
        Splits nodes into optimal subsets, runs sub-agents in parallel to generate partial synopses,
        and then calls a master agent to merge the synopses into a final coherent lesson.
        """
        MAX_AGENTS = 5
        MAX_NODES_PER_AGENT = 8

        groups = self._partition_nodes(nodes_with_chunks, MAX_NODES_PER_AGENT, MAX_AGENTS)
        num_agents = len(groups)
        add_log(f"Lesson Coordinator: Phân chia thành {num_agents} nhóm nodes cho các sub-agents xử lý song song.")

        agent_statuses = {
            i + 1: {
                "task": f"Synopsis of {len(groups[i])} nodes",
                "status": "queued",
                "detail": "Đang chờ..."
            }
            for i in range(num_agents)
        }

        async def update_status_cb(agent_id: int, status: str, detail: str):
            agent_statuses[agent_id]["status"] = status
            agent_statuses[agent_id]["detail"] = detail
            
            active_count = sum(1 for a in agent_statuses.values() if a["status"] == "running")
            queued_count = sum(1 for a in agent_statuses.values() if a["status"] == "queued")
            done_count = sum(1 for a in agent_statuses.values() if a["status"] == "completed")
            
            agent_details = []
            for aid in sorted(agent_statuses.keys()):
                info = agent_statuses[aid]
                agent_details.append(f"Agent {aid}: {info['task']} ({info['status']} - {info['detail']})")
                
            stage_str = f"Lesson ({done_count}/{num_agents}): {active_count} active, {queued_count} queued | " + ", ".join(agent_details)
            stage_str = stage_str[:400]
            
            progress = 25 + int((done_count / num_agents) * 25)
            await self._post_status(job_id, "processing", progress, stage_str, "", "\n".join(job_logs))

        # Initial status update
        add_log(f"Lesson Coordinator: Đang kích hoạt {num_agents} sub-agents song song...")
        await update_status_cb(1, "queued", "Bắt đầu các sub-agents...")

        # Run sub-agents in parallel with context bridging (previous group reference)
        tasks = []
        for i in range(num_agents):
            prev_group = groups[i - 1] if i > 0 else None
            tasks.append(
                self._generate_lesson_synopsis(
                    agent_id=i + 1,
                    nodes_group=groups[i],
                    prev_group_nodes=prev_group,
                    language=language,
                    section_id=section_id,
                    update_status_cb=update_status_cb,
                    add_log=add_log,
                )
            )

        synopses = await asyncio.gather(*tasks)
        add_log(f"Lesson Coordinator: Tất cả {num_agents} sub-agents đã sinh bản synopsis cục bộ thành công.")

        # Notify master agent start
        add_log("Lesson Coordinator: Master Synthesis Agent bắt đầu tích hợp các bản tóm tắt thành bài học Markdown hoàn chỉnh...")
        await self._post_status(job_id, "processing", 50, "Lesson: Master synthesis merging partial synopses...", "", "\n".join(job_logs))

        # Now run master synthesis to merge synopses into a coherent lesson
        lang_name = "Vietnamese" if language == "vi" else "English"
        sys_msg = _LESSON_SYSTEM_VI if language == "vi" else _LESSON_SYSTEM_EN

        seen_cids = set()
        references = []
        for item in nodes_with_chunks:
            cid = item["node"]["source_content_id"]
            if cid not in seen_cids and cid in content_map:
                seen_cids.add(cid)
                references.append(ContentRef(
                    content_id=cid,
                    title=content_map[cid]["title"],
                    content_type=content_map[cid]["content_type"],
                ))

        ref_list_str = "\n".join(
            f"- content_id={r.content_id}, title=\"{r.title}\", content_type=\"{r.content_type}\""
            for r in references
        )

        synopses_combined = "\n\n=== SECTION SYNOPSIS ===\n\n".join(synopses)

        user_msg = (
            f"## TASK: Synthesize Final Section Overview Lesson\n\n"
            f"You are the master coordinator. You are given a sequence of partial synopses generated "
            f"by parallel sub-agents covering Section ID: {section_id}.\n"
            f"Write a unified, comprehensive overview lesson in **{lang_name}** using **Markdown** that:\n"
            f"1. Merges the synopses into a single coherent, narrative-driven lesson (do NOT just list them or concatenate them).\n"
            f"2. Adds introduction transitions and smooth flowing prose between sections.\n"
            f"3. Emphasizes key concepts and uses clear Markdown headings, bullet points, and formatting.\n"
            f"4. Ends with a short 'Key Takeaways' section.\n\n"
            f"## AVAILABLE CONTENT REFERENCES (use content_id values exactly)\n"
            f"{ref_list_str}\n\n"
            f"## REQUIRED JSON SCHEMA\n"
            "{\n"
            f'  "title": "Section overview title in {lang_name}",\n'
            f'  "summary": "2-3 sentence summary in {lang_name}",\n'
            f'  "markdown_content": "Full Markdown lesson body in {lang_name}"\n'
            "}\n\n"
            f"## PARTIAL SYNOPSES TO MERGE\n"
            f"{synopses_combined}\n"
        )

        async with _LLM_SEMAPHORE:
            result = await self._chat_complete_json_with_retry(
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_msg},
                ],
                model=settings.quiz_model,
                temperature=0.4,
                max_tokens=4000,
                task=TASK_SECTION_OVERVIEW_GEN,
                add_log=add_log,
            )

        if not isinstance(result, dict):
            raise ValueError("LLM returned non-dict for lesson generation")

        title = (result.get("title") or "").strip() or f"Section {section_id} Overview"
        summary = (result.get("summary") or "").strip()
        markdown_content = (result.get("markdown_content") or "").strip()

        if not markdown_content:
            raise ValueError("LLM returned empty markdown_content for lesson")

        add_log(f"Lesson Coordinator: Tích hợp hoàn tất. Tiêu đề: '{title}', Độ dài Markdown: {len(markdown_content)} ký tự.")

        # Verify and refine the lesson using the QC Agent
        v_title, v_summary, v_md = await self._verify_and_refine_lesson(
            title=title,
            summary=summary,
            markdown_content=markdown_content,
            references=references,
            language=language,
            section_id=section_id,
            add_log=add_log,
        )

        return OverviewLesson(
            title=v_title,
            summary=v_summary,
            markdown_content=v_md,
            references=references,
        )

    # ── Overview quiz generation ──────────────────────────────────────────────

    async def _verify_and_refine_quiz(
        self,
        *,
        questions: list[OverviewQuestion],
        language: str,
        section_id: int,
        add_log,
    ) -> list[OverviewQuestion]:
        """
        Runs a verifier agent to de-duplicate, validate and refine the generated questions list.
        """
        if not questions:
            return []
            
        add_log("Quiz Verifier Agent: Đang tiến hành thẩm định và làm sạch danh sách câu hỏi trắc nghiệm...")
        lang_name = "Vietnamese" if language == "vi" else "English"
        sys_msg = _QUIZ_SYSTEM_VI if language == "vi" else _QUIZ_SYSTEM_EN

        # Serialize questions to pass to LLM
        raw_list = []
        for q in questions:
            raw_list.append({
                "question": q.question,
                "options": q.options,
                "explanation": q.explanation,
                "bloom_level": q.bloom_level,
                "reference_content_ids": q.reference_content_ids
            })
        
        import json
        raw_json_str = json.dumps(raw_list, ensure_ascii=False, indent=2)

        user_msg = (
            f"## TASK: Verify, Clean, and Refine Quiz Questions\n\n"
            f"You are a Quality Control (QC) agent reviewing generated multiple-choice questions (MCQs) for Section ID {section_id}.\n"
            f"Your job is to read the questions list and perform these verifications/refinements:\n"
            f"1. De-duplication: Remove duplicate or highly similar questions (keep the single best version).\n"
            f"2. Validation: Ensure each question has exactly 4 options (A, B, C, D) and exactly ONE option marked as 'is_correct': true.\n"
            f"3. Formatting: Standardize the answer options (e.g., prefixing them clearly). Ensure the explanation is clear and pedagogical.\n"
            f"4. Bloom Level: Keep the bloom level labels valid (e.g. remember, understand, apply, analyze, evaluate, create).\n"
            f"5. Return the cleaned and verified list matching the exact required schema.\n\n"
            f"## REQUIRED JSON SCHEMA\n"
            "{\n"
            '  "questions": [\n'
            '    {\n'
            f'      "question": "Cleaned question text in {lang_name}",\n'
            f'      "options": [\n'
            f'        {{"text": "A. ...", "is_correct": false}},\n'
            f'        {{"text": "B. ...", "is_correct": true}},\n'
            f'        {{"text": "C. ...", "is_correct": false}},\n'
            f'        {{"text": "D. ...", "is_correct": false}}\n'
            f'      ],\n'
            f'      "explanation": "Clear explanation in {lang_name}",\n'
            f'      "bloom_level": "understand",\n'
            f'      "reference_content_ids": [1, 2]\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            f"## ORIGINAL QUESTIONS TO REVIEW AND CLEAN\n"
            f"{raw_json_str}\n"
        )

        try:
            async with _LLM_SEMAPHORE:
                result = await self._chat_complete_json_with_retry(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=settings.quiz_model,
                    temperature=0.3,
                    max_tokens=4000,
                    task=TASK_SECTION_OVERVIEW_GEN,
                    add_log=add_log,
                )

            if not isinstance(result, dict) or "questions" not in result:
                add_log("Quiz Verifier Agent: Cảnh báo - Phản hồi QC không hợp lệ. Giữ lại bản gốc.")
                return questions

            cleaned_raw = result.get("questions") or []
            cleaned_questions = []
            for raw_q in cleaned_raw:
                if not isinstance(raw_q, dict):
                    continue
                q_text = (raw_q.get("question") or "").strip()
                options_raw = raw_q.get("options") or []
                if not q_text or not isinstance(options_raw, list) or len(options_raw) < 2:
                    continue
                
                normalised_opts = []
                has_correct = False
                for opt in options_raw[:4]:
                    if not isinstance(opt, dict):
                        continue
                    text = (opt.get("text") or "").strip()
                    is_correct = bool(opt.get("is_correct", False))
                    if text:
                        normalised_opts.append({"text": text, "is_correct": is_correct})
                        if is_correct:
                            has_correct = True
                            
                if len(normalised_opts) < 2 or not has_correct:
                    continue
                    
                bloom = (raw_q.get("bloom_level") or "understand").strip().lower()
                if bloom not in BLOOM_LEVELS:
                    bloom = "understand"
                    
                ref_cids = raw_q.get("reference_content_ids") or []
                if not isinstance(ref_cids, list):
                    ref_cids = []
                ref_cids = [int(x) for x in ref_cids if isinstance(x, (int, float, str))
                            and str(x).isdigit()]
                            
                cleaned_questions.append(OverviewQuestion(
                    question=q_text,
                    options=normalised_opts,
                    explanation=(raw_q.get("explanation") or "").strip()[:1000],
                    bloom_level=bloom,
                    reference_content_ids=ref_cids,
                ))
            
            diff_count = len(questions) - len(cleaned_questions)
            if diff_count > 0:
                add_log(f"Quiz Verifier Agent: Đã lọc bỏ {diff_count} câu hỏi trùng lặp hoặc không đạt yêu cầu.")
            add_log(f"Quiz Verifier Agent: Thẩm định hoàn tất. Còn lại {len(cleaned_questions)} câu hỏi chất lượng cao.")
            return cleaned_questions if cleaned_questions else questions
        except Exception as exc:
            logger.error("Quiz verifier failed: %s", exc)
            add_log(f"Quiz Verifier Agent: Thất bại do lỗi ({exc}). Sử dụng danh sách câu hỏi gốc.")
            return questions

    async def _generate_quiz(
        self,
        nodes_with_chunks: list[dict],
        content_map: dict[int, dict],
        question_count: int,
        section_id: int,
        language: str,
        job_id: int,
        add_log,
        job_logs: list[str],
    ) -> OverviewQuiz:
        """
        Generate exactly *question_count* MCQs covering the section broadly.
        Splits nodes into optimal subsets, runs sub-agents in parallel to generate questions,
        and then combines them.
        """
        question_count = max(1, question_count)
        lang_name = "Vietnamese" if language == "vi" else "English"
        sys_msg = _QUIZ_SYSTEM_VI if language == "vi" else _QUIZ_SYSTEM_EN

        # Build context and per-node allocation
        total_chunks = sum(len(item["chunks"]) for item in nodes_with_chunks)
        if total_chunks == 0:
            raise ValueError("No chunks found in any node")

        # Distribute questions proportionally across nodes
        node_allocations: list[int] = []
        for item in nodes_with_chunks:
            frac = len(item["chunks"]) / total_chunks
            node_allocations.append(max(0, round(frac * question_count)))

        # Fix rounding drift across nodes
        diff = question_count - sum(node_allocations)
        if diff != 0:
            heaviest_idx = max(range(len(nodes_with_chunks)), key=lambda i: len(nodes_with_chunks[i]["chunks"]))
            node_allocations[heaviest_idx] = max(0, node_allocations[heaviest_idx] + diff)

        # Attach allocation to each item
        for idx, item in enumerate(nodes_with_chunks):
            item["allocation"] = node_allocations[idx]

        # Partition nodes
        MAX_AGENTS = 5
        MAX_NODES_PER_AGENT = 8
        groups = self._partition_nodes(nodes_with_chunks, MAX_NODES_PER_AGENT, MAX_AGENTS)
        num_agents = len(groups)
        add_log(f"Quiz Coordinator: Phân chia thành {num_agents} nhóm nodes cho các sub-agents sinh câu hỏi trắc nghiệm.")

        agent_statuses = {
            i + 1: {
                "task": f"Quiz of {sum(item['allocation'] for item in groups[i])} Qs",
                "status": "queued",
                "detail": "Đang chờ..."
            }
            for i in range(num_agents)
        }

        async def update_status_cb(agent_id: int, status: str, detail: str):
            agent_statuses[agent_id]["status"] = status
            agent_statuses[agent_id]["detail"] = detail
            
            active_count = sum(1 for a in agent_statuses.values() if a["status"] == "running")
            queued_count = sum(1 for a in agent_statuses.values() if a["status"] == "queued")
            done_count = sum(1 for a in agent_statuses.values() if a["status"] == "completed")
            
            agent_details = []
            for aid in sorted(agent_statuses.keys()):
                info = agent_statuses[aid]
                agent_details.append(f"Agent {aid}: {info['task']} ({info['status']} - {info['detail']})")
                
            stage_str = f"Quiz ({done_count}/{num_agents}): {active_count} active, {queued_count} queued | " + ", ".join(agent_details)
            stage_str = stage_str[:400]
            
            progress = 55 + int((done_count / num_agents) * 30)
            await self._post_status(job_id, "processing", progress, stage_str, "", "\n".join(job_logs))

        # Initial status update
        add_log(f"Quiz Coordinator: Đang kích hoạt {num_agents} sub-agents sinh câu hỏi song song...")
        await update_status_cb(1, "queued", "Bắt đầu các sub-agents...")

        # Run sub-agents in parallel to generate questions
        tasks = []
        for i in range(num_agents):
            group_q_count = sum(item["allocation"] for item in groups[i])
            tasks.append(
                self._generate_quiz_partial(
                    agent_id=i + 1,
                    nodes_group=groups[i],
                    group_q_count=group_q_count,
                    language=language,
                    section_id=section_id,
                    content_map=content_map,
                    update_status_cb=update_status_cb,
                    add_log=add_log,
                )
            )

        results = await asyncio.gather(*tasks)
        add_log(f"Quiz Coordinator: Tất cả {num_agents} sub-agents đã sinh các câu hỏi thành công.")

        # Combine all questions
        all_questions: list[OverviewQuestion] = []
        for q_list in results:
            all_questions.extend(q_list)

        # Truncate/pad to exact question_count
        questions = all_questions[:question_count]
        add_log(f"Quiz Coordinator: Đã thu thập được {len(questions)} câu hỏi trắc nghiệm thô từ các sub-agents.")

        # Verify and refine the quiz questions using the QC Agent
        verified_questions = await self._verify_and_refine_quiz(
            questions=questions,
            language=language,
            section_id=section_id,
            add_log=add_log,
        )

        if not verified_questions:
            raise ValueError("LLM generated 0 valid quiz questions after verification")

        # Notify quiz meta start
        add_log("Quiz Coordinator: Đang sinh tiêu đề và tóm tắt tổng quan cho Quiz...")
        await self._post_status(job_id, "processing", 85, "Quiz: Generating title and summary...", "", "\n".join(job_logs))

        # Generate quiz title & summary
        nodes_summary = ", ".join(n["node"]["name"] for n in nodes_with_chunks)
        user_msg = (
            f"Generate a quiz title and a 2-sentence summary in {lang_name} for a section overview quiz.\n"
            f"Section ID: {section_id}\n"
            f"Topics covered: {nodes_summary}\n\n"
            f"JSON Schema:\n"
            "{\n"
            f'  "title": "quiz title in {lang_name}",\n'
            f'  "summary": "quiz summary in {lang_name}"\n'
            "}"
        )
        
        async with _LLM_SEMAPHORE:
            meta_result = await self._chat_complete_json_with_retry(
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_msg},
                ],
                model=settings.quiz_model,
                temperature=0.3,
                max_tokens=500,
                task=TASK_SECTION_OVERVIEW_GEN,
                add_log=add_log,
            )
            
        quiz_title = meta_result.get("title") or f"Section {section_id} Overview Quiz"
        quiz_summary = meta_result.get("summary") or ""
        add_log(f"Quiz Coordinator: Tiêu đề Quiz: '{quiz_title}'")

        # Extract references
        seen_cids = set()
        references: list[ContentRef] = []
        for item in nodes_with_chunks:
            cid = item["node"]["source_content_id"]
            if cid not in seen_cids and cid in content_map:
                seen_cids.add(cid)
                references.append(ContentRef(
                    content_id=cid,
                    title=content_map[cid]["title"],
                    content_type=content_map[cid]["content_type"],
                ))

        return OverviewQuiz(
            title=quiz_title,
            summary=quiz_summary,
            question_count=len(verified_questions),
            questions=verified_questions,
            references=references,
        )

    @staticmethod
    def _partition_nodes(
        nodes: list[dict],
        max_nodes_per_agent: int = 8,
        max_agents: int = 5,
        max_chars_per_agent: int = 16000,
    ) -> list[list[dict]]:
        """
        Partition nodes topologically into groups, ensuring each group has:
          1. At most `max_nodes_per_agent` nodes.
          2. At most `max_chars_per_agent` characters of chunk text.
          3. We limit the number of groups to at most `max_agents` (merging adjacent groups if needed).
        """
        n = len(nodes)
        if n == 0:
            return []

        # Pack nodes sequentially based on limits
        groups = []
        current_group = []
        current_chars = 0
        
        for item in nodes:
            node_chars = sum(len(c) for c in item.get("chunks", []))
            if (len(current_group) >= max_nodes_per_agent) or (current_group and (current_chars + node_chars > max_chars_per_agent)):
                groups.append(current_group)
                current_group = [item]
                current_chars = node_chars
            else:
                current_group.append(item)
                current_chars += node_chars
        if current_group:
            groups.append(current_group)
            
        # If the number of groups exceeds max_agents, we merge adjacent groups to fit
        while len(groups) > max_agents:
            best_idx = 0
            min_cost = float('inf')
            for i in range(len(groups) - 1):
                # cost is the combined size of adjacent groups
                cost = len(groups[i]) + len(groups[i+1])
                if cost < min_cost:
                    min_cost = cost
                    best_idx = i
            # Merge best_idx and best_idx + 1
            groups[best_idx].extend(groups[best_idx + 1])
            groups.pop(best_idx + 1)
            
        return groups

    async def _generate_lesson_synopsis(
        self,
        agent_id: int,
        nodes_group: list[dict],
        prev_group_nodes: list[dict] | None,
        language: str,
        section_id: int,
        update_status_cb,
        add_log,
    ) -> str:
        nodes_names = ", ".join(n["node"]["name"] for n in nodes_group)
        add_log(f"Lesson Agent {agent_id}: Nhận nhiệm vụ viết tóm tắt cho các nodes: {nodes_names}")
        await update_status_cb(agent_id, "running", "đang xử lý...")
        try:
            async with _LLM_SEMAPHORE:
                lang_name = "Vietnamese" if language == "vi" else "English"
                sys_msg = _LESSON_SYSTEM_VI if language == "vi" else _LESSON_SYSTEM_EN
                
                node_blocks = []
                for item in nodes_group:
                    node = item["node"]
                    node_text = f"### {node['name']}\n"
                    if node.get("description"):
                        node_text += f"_{node['description']}_\n\n"
                    chunk_excerpt = "\n".join(item["chunks"])
                    node_text += chunk_excerpt
                    node_blocks.append(node_text)
                
                nodes_context = "\n\n---\n\n".join(node_blocks)
                
                context_bridge = ""
                if prev_group_nodes:
                    prev_names = ", ".join(n["node"]["name"] for n in prev_group_nodes)
                    context_bridge = (
                        f"## CONTEXT: PREVIOUS TOPICS COVERED\n"
                        f"The previous group of agents covered these topics: {prev_names}.\n"
                        f"Please write a smooth transition from those topics at the beginning of your synopsis "
                        f"to ensure narrative continuity.\n\n"
                    )

                user_msg = (
                    f"## TASK: Generate Local Synopsis\n\n"
                    f"You are a sub-agent preparing a detailed synopsis of a specific subset of knowledge topics "
                    f"for Section ID {section_id}. Write in **{lang_name}** using **Markdown** that:\n"
                    f"1. Summarizes the concepts in this group, connecting them logically.\n"
                    f"2. Prepares a detailed explanation with headings and key points.\n"
                    f"3. Returns a clean JSON response matching the required schema.\n\n"
                    f"{context_bridge}"
                    f"## REQUIRED JSON SCHEMA\n"
                    "{\n"
                    f'  "synopsis": "Detailed Markdown synopsis of these topics in {lang_name}"\n'
                    "}\n\n"
                    f"## TOPICS FOR THIS AGENT\n"
                    f"{nodes_context}\n"
                )
                
                result = await self._chat_complete_json_with_retry(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=settings.quiz_model,
                    temperature=0.3,
                    max_tokens=2500,
                    task=TASK_SECTION_OVERVIEW_GEN,
                    add_log=add_log,
                )
                
            if not isinstance(result, dict) or "synopsis" not in result:
                raise ValueError("LLM returned invalid JSON synopsis")
            
            synopsis = result["synopsis"]
            add_log(f"Lesson Agent {agent_id}: Hoàn thành synopsis cục bộ ({len(synopsis)} ký tự).")
            await update_status_cb(agent_id, "completed", "hoàn thành")
            return synopsis
            
        except Exception as exc:
            logger.error("Lesson sub-agent %d failed: %s", agent_id, exc)
            add_log(f"Lesson Agent {agent_id} thất bại: {exc}")
            await update_status_cb(agent_id, "failed", f"lỗi: {str(exc)[:60]}")
            raise exc

    async def _generate_quiz_partial(
        self,
        agent_id: int,
        nodes_group: list[dict],
        group_q_count: int,
        language: str,
        section_id: int,
        content_map: dict[int, dict],
        update_status_cb,
        add_log,
    ) -> list[OverviewQuestion]:
        if group_q_count <= 0:
            add_log(f"Quiz Agent {agent_id}: Nhận nhiệm vụ sinh 0 câu hỏi (bỏ qua).")
            await update_status_cb(agent_id, "completed", "không có câu hỏi")
            return []
            
        nodes_names = ", ".join(n["node"]["name"] for n in nodes_group)
        add_log(f"Quiz Agent {agent_id}: Nhận nhiệm vụ sinh {group_q_count} câu hỏi cho các nodes: {nodes_names}")
        await update_status_cb(agent_id, "running", f"sinh {group_q_count} câu...")
        
        try:
            async with _LLM_SEMAPHORE:
                lang_name = "Vietnamese" if language == "vi" else "English"
                sys_msg = _QUIZ_SYSTEM_VI if language == "vi" else _QUIZ_SYSTEM_EN
                
                node_descriptors = []
                seen_cids = set()
                references = []
                
                for idx, item in enumerate(nodes_group):
                    node = item["node"]
                    cid = node["source_content_id"]
                    if cid not in seen_cids and cid in content_map:
                        seen_cids.add(cid)
                        references.append(ContentRef(
                            content_id=cid,
                            title=content_map[cid]["title"],
                            content_type=content_map[cid]["content_type"],
                        ))
                    chunk_excerpt = "\n".join(item["chunks"])
                    node_descriptors.append(
                        f"[Node {idx + 1}] name=\"{node['name']}\" "
                        f"content_id={cid} allocation={item['allocation']}\n{chunk_excerpt}"
                    )
                
                nodes_context = "\n\n---\n\n".join(node_descriptors)
                
                ref_list_str = "\n".join(
                    f"- content_id={r.content_id}, title=\"{r.title}\""
                    for r in references
                )
                
                bloom_hint = ", ".join(
                    BLOOM_LEVELS[i % len(BLOOM_LEVELS)]
                    for i in range(group_q_count)
                )
                
                user_msg = (
                    f"## TASK: Generate Section Overview Quiz Partial\n\n"
                    f"You are a sub-agent. Create exactly **{group_q_count}** multiple-choice questions (MCQs) in **{lang_name}** "
                    f"for Section ID {section_id} based on your assigned knowledge nodes. Requirements:\n"
                    f"1. Each question must have exactly 4 options (A, B, C, D) with exactly 1 correct answer.\n"
                    f"2. Distribute questions across nodes as indicated by 'allocation' in each node header.\n"
                    f"3. Vary Bloom levels. Suggested order: {bloom_hint}.\n"
                    f"4. For each question, list the content_id(s) it draws from in 'reference_content_ids'.\n\n"
                    f"## CONTENT REFERENCES\n{ref_list_str}\n\n"
                    f"## REQUIRED JSON SCHEMA\n"
                    "{\n"
                    f'  "questions": [\n'
                    f'    {{\n'
                    f'      "question": "Question text in {lang_name}",\n'
                    f'      "options": [\n'
                    f'        {{"text": "A. ...", "is_correct": false}},\n'
                    f'        {{"text": "B. ...", "is_correct": true}},\n'
                    f'        {{"text": "C. ...", "is_correct": false}},\n'
                    f'        {{"text": "D. ...", "is_correct": false}}\n'
                    f'      ],\n'
                    f'      "explanation": "Explanation in {lang_name}",\n'
                    f'      "bloom_level": "understand",\n'
                    f'      "reference_content_ids": [1, 2]\n'
                    f'    }}\n'
                    f'  ]\n'
                    "}\n\n"
                    f"## ASSIGNED KNOWLEDGE NODES WITH CONTENT\n{nodes_context}\n"
                )
                
                result = await self._chat_complete_json_with_retry(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=settings.quiz_model,
                    temperature=0.5,
                    max_tokens=4000,
                    task=TASK_SECTION_OVERVIEW_GEN,
                    add_log=add_log,
                )
                
            if not isinstance(result, dict) or "questions" not in result:
                raise ValueError("LLM returned non-dict or missing 'questions'")
                
            raw_questions = result.get("questions") or []
            questions = []
            for raw_q in raw_questions:
                if not isinstance(raw_q, dict):
                    continue
                q_text = (raw_q.get("question") or "").strip()
                options_raw = raw_q.get("options") or []
                if not q_text or not isinstance(options_raw, list) or len(options_raw) < 2:
                    continue
                
                normalised_opts = []
                has_correct = False
                for opt in options_raw[:4]:
                    if not isinstance(opt, dict):
                        continue
                    text = (opt.get("text") or "").strip()
                    is_correct = bool(opt.get("is_correct", False))
                    if text:
                        normalised_opts.append({"text": text, "is_correct": is_correct})
                        if is_correct:
                            has_correct = True
                            
                if len(normalised_opts) < 2 or not has_correct:
                    continue
                    
                bloom = (raw_q.get("bloom_level") or "understand").strip().lower()
                if bloom not in BLOOM_LEVELS:
                    bloom = "understand"
                    
                ref_cids = raw_q.get("reference_content_ids") or []
                if not isinstance(ref_cids, list):
                    ref_cids = []
                ref_cids = [int(x) for x in ref_cids if isinstance(x, (int, float, str))
                            and str(x).isdigit()]
                            
                questions.append(OverviewQuestion(
                    question=q_text,
                    options=normalised_opts,
                    explanation=(raw_q.get("explanation") or "").strip()[:1000],
                    bloom_level=bloom,
                    reference_content_ids=ref_cids,
                ))
                
            add_log(f"Quiz Agent {agent_id}: Đã sinh thành công {len(questions)} câu hỏi trắc nghiệm.")
            await update_status_cb(agent_id, "completed", f"sinh xong {len(questions)} câu")
            return questions
            
        except Exception as exc:
            logger.error("Quiz sub-agent %d failed: %s", agent_id, exc)
            add_log(f"Quiz Agent {agent_id} thất bại: {exc}")
            await update_status_cb(agent_id, "failed", f"lỗi: {str(exc)[:60]}")
            raise exc

    # ── HTTP callbacks ────────────────────────────────────────────────────────

    async def _post_results(
        self,
        *,
        job_id: int,
        section_id: int,
        course_id: int,
        language: str,
        lesson: OverviewLesson,
        quiz: OverviewQuiz,
    ) -> None:
        payload = {
            "job_id": job_id,
            "section_id": section_id,
            "course_id": course_id,
            "language": language,
            "lesson": {
                "title": lesson.title,
                "summary": lesson.summary,
                "markdown_content": lesson.markdown_content,
                "references": [
                    {"content_id": r.content_id, "title": r.title, "content_type": r.content_type}
                    for r in lesson.references
                ],
            },
            "quiz": {
                "title": quiz.title,
                "summary": quiz.summary,
                "question_count": quiz.question_count,
                "questions": [
                    {
                        "question": q.question,
                        "options": q.options,
                        "explanation": q.explanation,
                        "bloom_level": q.bloom_level,
                        "reference_content_ids": q.reference_content_ids,
                    }
                    for q in quiz.questions
                ],
                "references": [
                    {"content_id": r.content_id, "title": r.title, "content_type": r.content_type}
                    for r in quiz.references
                ],
            },
        }
        await self._lms_post("/api/v1/internal/section-overview/results", payload)

    async def _post_status(
        self,
        job_id: int,
        status: str,
        progress: int,
        stage: str,
        error: str,
        logs: str = "",
    ) -> None:
        await self._lms_post("/api/v1/internal/section-overview/status", {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "stage": stage,
            "error": error,
            "logs": logs,
        })

    async def _lms_post(self, path: str, body: dict) -> None:
        url = settings.lms_service_url.rstrip("/") + path
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={"X-API-Secret": settings.ai_service_secret},
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "LMS callback %s → %d: %s",
                        path, resp.status_code, resp.text[:200],
                    )
        except Exception as exc:
            logger.error("LMS callback %s failed: %s", path, exc)


# Singleton
section_overview_service = SectionOverviewService()
