"""
ai-service/app/services/graph_consolidation_service.py

"Compact Graph" — intelligent knowledge node consolidation.

Three phases:

  1. CANDIDATE DISCOVERY
     - Pull all nodes for a course from Qdrant (with vectors).
     - Pull chunk_count per node from PostgreSQL.
     - Compute pairwise cosine similarity, then build groups:
         * Hard duplicates (sim >= HARD_THRESHOLD)              -> auto-merge
         * Soft duplicates (SOFT_THRESHOLD <= sim < HARD_THRESHOLD) -> LLM confirm
         * Micro-fragments (chunk_count <= MICRO_FRAGMENT_MAX_CHUNKS)
           with sim >= MICRO_FRAGMENT_THRESHOLD -> absorb into a larger neighbour

  2. LLM VALIDATION
     - For non-hard groups, ask the LLM whether merge makes sense and pick
       the best survivor + final name/description/keywords.

  3. EXECUTE (cascaded)
     - PG: rewire FKs, merge progress stats, update survivor metadata,
       delete absorbed rows.
     - Qdrant: patch chunk payloads, drop absorbed node vectors.
     - Neo4j: rewire incoming/outgoing edges, then DETACH DELETE.
     - Kafka: publish `ai.graph.node_merged` events so LMS can update
       its `micro_lessons.node_id` / `quiz_questions.node_id` columns.

Phase 1+2 also runs as a synchronous "preview" used by the UI before the
teacher confirms the destructive Phase 3 step.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_GRAPH_LINK

logger   = logging.getLogger(__name__)
settings = get_settings()


# ── Tuning constants ──────────────────────────────────────────────────────────

HARD_THRESHOLD            = 0.92   # auto-merge — same concept, no LLM needed
SOFT_THRESHOLD            = 0.78   # LLM confirms whether to merge
MICRO_FRAGMENT_THRESHOLD  = 0.70   # absorb micro-fragments into a neighbour
MICRO_FRAGMENT_MAX_CHUNKS = 2      # "micro" = <= 2 chunks
MAX_LLM_GROUPS            = 25     # cap on LLM round-trips per consolidation


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass
class _Node:
    id: int
    name: str
    name_vi: str
    description: str
    keywords: list[str]
    chunk_count: int
    embedding: list[float]


@dataclass
class MergeGroup:
    """One cluster of nodes that will be collapsed into a single survivor."""
    survivor_id:     int
    absorbed_ids:    list[int]
    new_name:        str
    new_name_vi:     str
    new_description: str
    new_keywords:    list[str] = field(default_factory=list)
    similarity:      float     = 0.0
    reason:          str       = ""
    kind:            str       = "hard"   # hard | soft | micro
    old_names:       dict[int, str] = field(default_factory=dict)


@dataclass
class ConsolidationPlan:
    course_id:  int
    groups:     list[MergeGroup]
    total_nodes_before: int

    @property
    def total_nodes_after(self) -> int:
        absorbed = sum(len(g.absorbed_ids) for g in self.groups)
        return max(0, self.total_nodes_before - absorbed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "course_id":            self.course_id,
            "total_nodes_before":   self.total_nodes_before,
            "total_nodes_after":    self.total_nodes_after,
            "reduction_percent":    (
                round(100.0 * (self.total_nodes_before - self.total_nodes_after)
                      / max(1, self.total_nodes_before), 1)
            ),
            "groups": [
                {
                    "survivor_id":     g.survivor_id,
                    "absorbed_ids":    g.absorbed_ids,
                    "new_name":        g.new_name,
                    "new_name_vi":     g.new_name_vi,
                    "new_description": g.new_description,
                    "new_keywords":    g.new_keywords,
                    "similarity":      round(g.similarity, 3),
                    "reason":          g.reason,
                    "kind":            g.kind,
                    "old_names":       {str(k): v for k, v in g.old_names.items()},
                }
                for g in self.groups
            ],
        }


# ── LLM prompt ────────────────────────────────────────────────────────────────

_VALIDATION_SYSTEM_PROMPT = """\
Bạn là chuyên gia thiết kế bản đồ kiến thức (knowledge graph).
Nhiệm vụ: Đánh giá xem một nhóm "knowledge node" có thật sự nói về CÙNG MỘT khái niệm
hay không. Nếu CÓ, hãy chọn node "tồn tại" tốt nhất và đề xuất tên + mô tả mới đã hợp nhất.
Chỉ trả về JSON hợp lệ, không kèm văn bản khác.\
"""

_VALIDATION_PROMPT_TEMPLATE = """\
Hãy đánh giá nhóm node sau. Chúng có cùng khái niệm không? Nếu có, hãy gộp.

DANH SÁCH NODE (mỗi node có id, tên, mô tả, số chunks):
{nodes_block}

Yêu cầu trả về JSON:
{{
  "should_merge": true | false,
  "survivor_id": <id của node giữ lại>,
  "new_name":        "<tên tiếng Anh tốt nhất>",
  "new_name_vi":     "<tên tiếng Việt tốt nhất>",
  "new_description": "<mô tả 1-2 câu, gộp ý chính>",
  "new_keywords":    ["từ khóa 1", "từ khóa 2"],
  "reason":          "<1 câu lý do bằng tiếng Việt>"
}}

Quy tắc:
- Nếu các node KHÁC khái niệm (chỉ trùng từ vựng), trả về should_merge=false.
- Survivor nên là node có nhiều chunks nhất, hoặc tên rõ ràng / chuẩn nhất.
- new_description ngắn gọn, không lặp lại tên.\
"""


# ── Service ───────────────────────────────────────────────────────────────────

class GraphConsolidationService:

    # ── Public API ────────────────────────────────────────────────────────────

    async def analyze_graph(self, course_id: int) -> ConsolidationPlan:
        """Phase 1 + 2 — returns a dry-run plan; nothing is mutated."""
        nodes = await self._load_nodes(course_id)
        if len(nodes) < 2:
            return ConsolidationPlan(course_id=course_id, groups=[], total_nodes_before=len(nodes))

        raw_groups = self._discover_merge_candidates(nodes)
        groups     = await self._llm_validate_merges(raw_groups, nodes)

        return ConsolidationPlan(
            course_id=course_id,
            groups=groups,
            total_nodes_before=len(nodes),
        )

    async def execute_consolidation(
        self,
        course_id: int,
        plan: ConsolidationPlan,
        triggered_by: Optional[int] = None,
    ) -> dict[str, Any]:
        """Phase 3 — execute every approved group atomically (per group)."""
        if not plan.groups:
            return {"course_id": course_id, "merged_groups": 0, "absorbed_nodes": 0}

        absorbed_total = 0
        chunks_moved_total = 0
        executed_groups = 0

        for group in plan.groups:
            try:
                chunks_moved = await self._execute_single_merge(course_id, group, triggered_by)
                absorbed_total += len(group.absorbed_ids)
                chunks_moved_total += chunks_moved
                executed_groups += 1
            except Exception as exc:
                logger.error(
                    "Consolidation group failed (survivor=%d): %s",
                    group.survivor_id, exc, exc_info=True,
                )
                # Continue with the other groups — each is independent.

        return {
            "course_id":      course_id,
            "merged_groups":  executed_groups,
            "absorbed_nodes": absorbed_total,
            "chunks_moved":   chunks_moved_total,
        }

    # ── Phase 1: candidate discovery ──────────────────────────────────────────

    async def _load_nodes(self, course_id: int) -> list[_Node]:
        """Fetch every node for the course with vector + chunk count."""
        chunk_counts: dict[int, int] = {}
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT kn.id,
                       COUNT(DISTINCT dc.id) AS chunk_count
                FROM knowledge_nodes kn
                LEFT JOIN document_chunks dc ON dc.node_id = kn.id
                WHERE kn.course_id = $1
                GROUP BY kn.id
                """,
                course_id,
            )
            for r in rows:
                chunk_counts[r["id"]] = r["chunk_count"] or 0

        out: list[_Node] = []

        if settings.use_qdrant:
            from app.services.qdrant_service import qdrant_service
            records = await qdrant_service.scroll_nodes_for_course(course_id)
            for r in records:
                if not r.vector:
                    continue
                payload = r.payload or {}
                nid = int(r.id)
                out.append(_Node(
                    id=nid,
                    name=payload.get("name", "") or "",
                    name_vi=payload.get("name_vi", "") or "",
                    description=payload.get("description", "") or "",
                    keywords=payload.get("keywords", []) or [],
                    chunk_count=chunk_counts.get(nid, 0),
                    embedding=list(r.vector),
                ))
        else:
            # PG fallback path — no vectors available, so consolidation is a no-op.
            logger.warning("Qdrant disabled — graph consolidation requires Qdrant vectors.")

        return out

    def _discover_merge_candidates(self, nodes: list[_Node]) -> list[MergeGroup]:
        """Build merge groups using cosine similarity + chunk-count heuristics."""
        n = len(nodes)
        if n < 2:
            return []

        emb = np.array([nd.embedding for nd in nodes], dtype=np.float32)
        norm = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8
        sims = (emb / norm) @ (emb / norm).T

        # Union-find for hard duplicates so transitive matches collapse to one group.
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # 1. Hard duplicates -> merge greedily.
        for i in range(n):
            for j in range(i + 1, n):
                if sims[i, j] >= HARD_THRESHOLD:
                    union(i, j)

        clusters: dict[int, list[int]] = {}
        for i in range(n):
            clusters.setdefault(find(i), []).append(i)

        groups: list[MergeGroup] = []
        used: set[int] = set()

        # Hard-duplicate groups (>=2 members).
        for members in clusters.values():
            if len(members) < 2:
                continue
            members_sorted = sorted(members, key=lambda k: nodes[k].chunk_count, reverse=True)
            survivor_idx = members_sorted[0]
            absorbed_idx = members_sorted[1:]
            avg_sim = float(np.mean([sims[a, survivor_idx] for a in absorbed_idx])) if absorbed_idx else 1.0
            groups.append(self._make_group(
                nodes, survivor_idx, absorbed_idx, avg_sim,
                kind="hard",
                reason="Cosine similarity >= 0.92 — auto-merged",
            ))
            used.update(members)

        # 2. Soft-duplicate pairs — only consider nodes not already merged.
        soft_pairs: list[tuple[int, int, float]] = []
        for i in range(n):
            if i in used:
                continue
            for j in range(i + 1, n):
                if j in used:
                    continue
                s = float(sims[i, j])
                if SOFT_THRESHOLD <= s < HARD_THRESHOLD:
                    soft_pairs.append((i, j, s))

        soft_pairs.sort(key=lambda t: t[2], reverse=True)
        for i, j, s in soft_pairs:
            if i in used or j in used:
                continue
            survivor_idx, absorbed_idx = (
                (i, [j]) if nodes[i].chunk_count >= nodes[j].chunk_count else (j, [i])
            )
            groups.append(self._make_group(
                nodes, survivor_idx, absorbed_idx, s,
                kind="soft",
                reason=f"Soft duplicate (sim={s:.2f}) — pending LLM confirmation",
            ))
            used.add(i)
            used.add(j)

        # 3. Micro-fragments -> absorb into nearest non-micro neighbour.
        for k in range(n):
            if k in used:
                continue
            if nodes[k].chunk_count > MICRO_FRAGMENT_MAX_CHUNKS:
                continue
            best_idx = -1
            best_sim = MICRO_FRAGMENT_THRESHOLD
            for m in range(n):
                if m == k or m in used:
                    continue
                if nodes[m].chunk_count <= MICRO_FRAGMENT_MAX_CHUNKS:
                    continue
                if sims[k, m] > best_sim:
                    best_sim = float(sims[k, m])
                    best_idx = m
            if best_idx == -1:
                continue
            groups.append(self._make_group(
                nodes, best_idx, [k], best_sim,
                kind="micro",
                reason=(
                    f"Micro-fragment ({nodes[k].chunk_count} chunks) absorbed "
                    f"into '{nodes[best_idx].name}' (sim={best_sim:.2f})"
                ),
            ))
            used.add(k)
            used.add(best_idx)

        return groups

    @staticmethod
    def _make_group(
        nodes: list[_Node],
        survivor_idx: int,
        absorbed_idx: list[int],
        sim: float,
        *,
        kind: str,
        reason: str,
    ) -> MergeGroup:
        survivor = nodes[survivor_idx]
        absorbed = [nodes[i] for i in absorbed_idx]

        # Combine keywords (deduped, keeping order).
        seen: set[str] = set()
        merged_kw: list[str] = []
        for n in [survivor, *absorbed]:
            for kw in n.keywords:
                if kw and kw not in seen:
                    seen.add(kw)
                    merged_kw.append(kw)

        # Pick the longest non-empty description as the default.
        descs = [n.description for n in [survivor, *absorbed] if n.description]
        merged_desc = max(descs, key=len) if descs else ""

        return MergeGroup(
            survivor_id=survivor.id,
            absorbed_ids=[n.id for n in absorbed],
            new_name=survivor.name,
            new_name_vi=survivor.name_vi,
            new_description=merged_desc,
            new_keywords=merged_kw[:20],
            similarity=sim,
            reason=reason,
            kind=kind,
            old_names={n.id: (n.name_vi or n.name) for n in [survivor, *absorbed]},
        )

    # ── Phase 2: LLM validation ───────────────────────────────────────────────

    async def _llm_validate_merges(
        self,
        groups: list[MergeGroup],
        nodes: list[_Node],
    ) -> list[MergeGroup]:
        """LLM-confirm soft + micro groups; hard groups skip the call."""
        if not groups:
            return []

        node_by_id: dict[int, _Node] = {n.id: n for n in nodes}

        # Hard duplicates: take as-is. Soft/micro: LLM-validate (capped).
        hard = [g for g in groups if g.kind == "hard"]
        review = [g for g in groups if g.kind != "hard"][:MAX_LLM_GROUPS]

        if not review:
            return hard

        sem = asyncio.Semaphore(8)

        async def confirm(group: MergeGroup) -> MergeGroup | None:
            async with sem:
                return await self._llm_confirm_group(group, node_by_id)

        results = await asyncio.gather(
            *[confirm(g) for g in review], return_exceptions=True,
        )

        approved: list[MergeGroup] = list(hard)
        for original, res in zip(review, results):
            if isinstance(res, Exception):
                logger.warning("LLM validation failed for group %s: %s", original.survivor_id, res)
                continue
            if res is not None:
                approved.append(res)
        return approved

    async def _llm_confirm_group(
        self,
        group: MergeGroup,
        node_by_id: dict[int, _Node],
    ) -> MergeGroup | None:
        ids = [group.survivor_id, *group.absorbed_ids]
        members = [node_by_id[i] for i in ids if i in node_by_id]
        if len(members) < 2:
            return None

        nodes_block = "\n".join(
            f"- id={m.id} | name={m.name!r} | name_vi={m.name_vi!r} | "
            f"chunks={m.chunk_count} | desc={(m.description or '')[:200]!r}"
            for m in members
        )
        prompt = _VALIDATION_PROMPT_TEMPLATE.format(nodes_block=nodes_block)

        try:
            data = await chat_complete_json(
                messages=[
                    {"role": "system", "content": _VALIDATION_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.05,
                task=TASK_GRAPH_LINK,
            )
        except Exception as exc:
            logger.warning("LLM merge confirmation failed: %s", exc)
            return None

        if not isinstance(data, dict) or not data.get("should_merge"):
            return None

        survivor_id = data.get("survivor_id")
        if survivor_id not in {m.id for m in members}:
            survivor_id = group.survivor_id   # fall back to heuristic pick

        absorbed_ids = [m.id for m in members if m.id != survivor_id]
        if not absorbed_ids:
            return None

        survivor = node_by_id[survivor_id]
        return MergeGroup(
            survivor_id=survivor_id,
            absorbed_ids=absorbed_ids,
            new_name=str(data.get("new_name") or survivor.name),
            new_name_vi=str(data.get("new_name_vi") or survivor.name_vi),
            new_description=str(data.get("new_description") or group.new_description),
            new_keywords=list(data.get("new_keywords") or group.new_keywords),
            similarity=group.similarity,
            reason=str(data.get("reason") or group.reason),
            kind=group.kind,
            old_names={m.id: (m.name_vi or m.name) for m in members},
        )

    # ── Phase 3: cascaded execution ───────────────────────────────────────────

    async def _execute_single_merge(
        self,
        course_id: int,
        group: MergeGroup,
        triggered_by: Optional[int],
    ) -> int:
        """Apply one merge group across PG, Qdrant, Neo4j, then publish to Kafka."""
        survivor   = group.survivor_id
        absorbed   = group.absorbed_ids
        all_ids    = [survivor, *absorbed]

        # 1+2+3+4+5: PostgreSQL cascade in a single transaction.
        chunks_moved = await self._cascade_pg(course_id, group, triggered_by)

        # 6+7: Qdrant cascade.
        await self._cascade_qdrant(group)

        # 8: Re-embed survivor with the consolidated text + upsert.
        await self._refresh_survivor_embedding(course_id, survivor, group)

        # 9+10: Neo4j cascade.
        await self._cascade_neo4j(group)

        # 11: Notify LMS so it can rewrite its own node_id columns.
        await self._publish_lms_cascade(course_id, group)

        logger.info(
            "Consolidated %d nodes into survivor %d (course %d, %d chunks moved)",
            len(absorbed), survivor, course_id, chunks_moved,
        )
        # Keep `all_ids` referenced so reviewers can see the audit shape.
        _ = all_ids
        return chunks_moved

    async def _cascade_pg(
        self,
        course_id: int,
        group: MergeGroup,
        triggered_by: Optional[int],
    ) -> int:
        """Rewire PG FKs, merge progress stats, update survivor, delete absorbed."""
        survivor = group.survivor_id
        absorbed = group.absorbed_ids

        async with get_ai_conn() as conn:
            async with conn.transaction():
                # 1. Reassign chunks.
                chunks_moved = await conn.fetchval(
                    """
                    WITH moved AS (
                        UPDATE document_chunks
                           SET node_id = $1
                         WHERE node_id = ANY($2)
                         RETURNING 1
                    )
                    SELECT COUNT(*) FROM moved
                    """,
                    survivor, absorbed,
                ) or 0

                # 2. Reassign quiz drafts, flashcards, spaced repetitions, diagnoses.
                for table in (
                    "ai_quiz_generations",
                    "flashcards",
                    "spaced_repetitions",
                    "ai_diagnoses",
                ):
                    await conn.execute(
                        f"UPDATE {table} SET node_id = $1 WHERE node_id = ANY($2)",
                        survivor, absorbed,
                    )

                # 3. Merge student_knowledge_progress stats.
                #    For each student that has progress on absorbed nodes, accumulate
                #    counters into the survivor row (creating it if missing) and then
                #    drop the absorbed rows.
                await conn.execute(
                    """
                    INSERT INTO student_knowledge_progress
                        (student_id, node_id, course_id,
                         total_attempts, correct_count, wrong_count,
                         mastery_level, last_tested_at, updated_at)
                    SELECT student_id, $1, course_id,
                           SUM(total_attempts), SUM(correct_count), SUM(wrong_count),
                           AVG(mastery_level), MAX(last_tested_at), NOW()
                      FROM student_knowledge_progress
                     WHERE node_id = ANY($2)
                     GROUP BY student_id, course_id
                    ON CONFLICT (student_id, node_id) DO UPDATE
                       SET total_attempts = student_knowledge_progress.total_attempts
                                          + EXCLUDED.total_attempts,
                           correct_count  = student_knowledge_progress.correct_count
                                          + EXCLUDED.correct_count,
                           wrong_count    = student_knowledge_progress.wrong_count
                                          + EXCLUDED.wrong_count,
                           mastery_level  = GREATEST(student_knowledge_progress.mastery_level,
                                                     EXCLUDED.mastery_level),
                           last_tested_at = GREATEST(student_knowledge_progress.last_tested_at,
                                                     EXCLUDED.last_tested_at),
                           updated_at     = NOW()
                    """,
                    survivor, absorbed,
                )
                await conn.execute(
                    "DELETE FROM student_knowledge_progress WHERE node_id = ANY($1)",
                    absorbed,
                )

                # 4. Rewire knowledge_node_relations endpoints onto the survivor,
                #    skipping rows that would create self-loops or duplicate edges.
                await conn.execute(
                    """
                    UPDATE knowledge_node_relations
                       SET source_node_id = $1
                     WHERE source_node_id = ANY($2)
                       AND target_node_id <> $1
                       AND NOT EXISTS (
                           SELECT 1 FROM knowledge_node_relations r2
                            WHERE r2.source_node_id = $1
                              AND r2.target_node_id = knowledge_node_relations.target_node_id
                              AND r2.relation_type  = knowledge_node_relations.relation_type
                       )
                    """,
                    survivor, absorbed,
                )
                await conn.execute(
                    """
                    UPDATE knowledge_node_relations
                       SET target_node_id = $1
                     WHERE target_node_id = ANY($2)
                       AND source_node_id <> $1
                       AND NOT EXISTS (
                           SELECT 1 FROM knowledge_node_relations r2
                            WHERE r2.target_node_id = $1
                              AND r2.source_node_id = knowledge_node_relations.source_node_id
                              AND r2.relation_type  = knowledge_node_relations.relation_type
                       )
                    """,
                    survivor, absorbed,
                )

                # 5. Reparent any children pointing at absorbed nodes.
                await conn.execute(
                    "UPDATE knowledge_nodes SET parent_id = $1 WHERE parent_id = ANY($2)",
                    survivor, absorbed,
                )

                # 6. Update survivor metadata.
                await conn.execute(
                    """
                    UPDATE knowledge_nodes
                       SET name        = $2,
                           name_vi     = COALESCE(NULLIF($3, ''), name_vi),
                           description = COALESCE(NULLIF($4, ''), description),
                           updated_at  = NOW()
                     WHERE id = $1
                    """,
                    survivor, group.new_name, group.new_name_vi, group.new_description,
                )

                # 7. Delete absorbed nodes (cascades remaining FKs).
                await conn.execute(
                    "DELETE FROM knowledge_nodes WHERE id = ANY($1)", absorbed,
                )

                # 8. Audit log.
                await conn.execute(
                    """
                    INSERT INTO graph_consolidation_log
                        (course_id, survivor_id, absorbed_ids,
                         old_names, new_name, new_description,
                         chunks_moved, triggered_by)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
                    """,
                    course_id, survivor, absorbed,
                    json.dumps({str(k): v for k, v in group.old_names.items()}),
                    group.new_name, group.new_description,
                    int(chunks_moved), triggered_by,
                )

        return int(chunks_moved)

    async def _cascade_qdrant(self, group: MergeGroup) -> None:
        """Patch chunk payloads + drop absorbed node points."""
        if not settings.use_qdrant:
            return

        from app.services.qdrant_service import qdrant_service, CHUNK_COLLECTION, NODE_COLLECTION
        from qdrant_client.http.models import (
            FieldCondition, Filter, MatchAny, PointIdsList,
        )

        client = qdrant_service._get_client()
        try:
            # Repoint every chunk that referenced an absorbed node.
            await client.set_payload(
                collection_name=CHUNK_COLLECTION,
                payload={"node_id": group.survivor_id},
                points_selector=Filter(
                    must=[FieldCondition(key="node_id", match=MatchAny(any=group.absorbed_ids))]
                ),
                wait=True,
            )
        except Exception as exc:
            logger.error("Qdrant chunk payload update failed: %s", exc)

        try:
            await client.delete(
                collection_name=NODE_COLLECTION,
                points_selector=PointIdsList(points=group.absorbed_ids),
                wait=True,
            )
        except Exception as exc:
            logger.error("Qdrant absorbed-node delete failed: %s", exc)

    async def _refresh_survivor_embedding(
        self,
        course_id: int,
        survivor_id: int,
        group: MergeGroup,
    ) -> None:
        """Re-embed the survivor with merged text and upsert into Qdrant."""
        if not settings.use_qdrant:
            return
        try:
            from app.core.embeddings import create_passage_embedding
            from app.services.qdrant_service import qdrant_service

            text_parts = [group.new_name, group.new_name_vi, group.new_description]
            text = " | ".join(p for p in text_parts if p).strip()
            if not text:
                return

            vec = await create_passage_embedding(text)
            await qdrant_service.upsert_node(
                node_id=survivor_id,
                embedding=vec,
                payload={
                    "course_id":   course_id,
                    "name":        group.new_name,
                    "name_vi":     group.new_name_vi,
                    "description": group.new_description,
                    "keywords":    group.new_keywords,
                    "auto_generated": True,
                },
            )
        except Exception as exc:
            logger.error("Failed to refresh survivor embedding: %s", exc)

    async def _cascade_neo4j(self, group: MergeGroup) -> None:
        """Rewire all Neo4j edges onto the survivor, then DETACH DELETE absorbed."""
        if not settings.neo4j_enabled:
            return

        from app.services.neo4j_service import neo4j_service
        try:
            driver = neo4j_service._get_driver()
        except Exception as exc:
            logger.warning("Neo4j unavailable, skipping cascade: %s", exc)
            return

        survivor = group.survivor_id
        absorbed = group.absorbed_ids

        try:
            async with driver.session() as s:
                # Rewire incoming edges (a)-[r]->(absorbed)  ⇒  (a)-[r]->(survivor)
                await s.run(
                    """
                    UNWIND $absorbed AS aid
                    MATCH (a:KnowledgeNode)-[r]->(b:KnowledgeNode {id: aid})
                    WHERE a.id <> $survivor
                    WITH a, b, r, type(r) AS rt
                    MATCH (s:KnowledgeNode {id: $survivor})
                    CALL apoc.merge.relationship(a, rt, {}, properties(r), s, {})
                          YIELD rel
                    DELETE r
                    RETURN count(rel)
                    """,
                    survivor=survivor, absorbed=absorbed,
                )
        except Exception:
            # APOC may not be installed — fall back to a property-less rewire that
            # keeps relationship type via a parameterised Cypher per type.
            await self._neo4j_fallback_rewire(group)

        try:
            async with driver.session() as s:
                await s.run(
                    "UNWIND $ids AS id MATCH (n:KnowledgeNode {id: id}) DETACH DELETE n",
                    ids=absorbed,
                )
        except Exception as exc:
            logger.error("Neo4j absorbed-node delete failed: %s", exc)

    async def _neo4j_fallback_rewire(self, group: MergeGroup) -> None:
        """APOC-free rewire — re-create each edge under the survivor."""
        from app.services.neo4j_service import neo4j_service, RELATIONSHIP_TYPES

        driver = neo4j_service._get_driver()
        survivor = group.survivor_id
        absorbed = group.absorbed_ids

        async with driver.session() as s:
            for rel_type in RELATIONSHIP_TYPES.values():
                await s.run(
                    f"""
                    UNWIND $absorbed AS aid
                    MATCH (a:KnowledgeNode)-[r:{rel_type}]->(b:KnowledgeNode {{id: aid}})
                    WHERE a.id <> $survivor
                    MATCH (s:KnowledgeNode {{id: $survivor}})
                    MERGE (a)-[nr:{rel_type}]->(s)
                      ON CREATE SET nr += properties(r)
                    """,
                    survivor=survivor, absorbed=absorbed,
                )
                await s.run(
                    f"""
                    UNWIND $absorbed AS aid
                    MATCH (a:KnowledgeNode {{id: aid}})-[r:{rel_type}]->(b:KnowledgeNode)
                    WHERE b.id <> $survivor
                    MATCH (s:KnowledgeNode {{id: $survivor}})
                    MERGE (s)-[nr:{rel_type}]->(b)
                      ON CREATE SET nr += properties(r)
                    """,
                    survivor=survivor, absorbed=absorbed,
                )

    async def _publish_lms_cascade(
        self,
        course_id: int,
        group: MergeGroup,
    ) -> None:
        """Notify the LMS so it can update its own node_id columns."""
        try:
            from app.worker.kafka_producer import publish_node_merged_event
            await publish_node_merged_event(
                course_id=course_id,
                survivor_id=group.survivor_id,
                absorbed_ids=group.absorbed_ids,
            )
        except Exception as exc:
            logger.error("Failed to publish ai.graph.node_merged: %s", exc)


# ── Singleton + helper ────────────────────────────────────────────────────────

graph_consolidation_service = GraphConsolidationService()


async def consolidate_graph(course_id: int, triggered_by: Optional[int] = None) -> dict[str, Any]:
    """Convenience entrypoint used by the Kafka worker."""
    plan = await graph_consolidation_service.analyze_graph(course_id)
    result = await graph_consolidation_service.execute_consolidation(course_id, plan, triggered_by)
    result["plan"] = plan.to_dict()
    return result
