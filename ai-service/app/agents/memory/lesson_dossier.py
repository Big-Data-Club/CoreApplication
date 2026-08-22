"""
ai-service/app/agents/memory/lesson_dossier.py

Lesson dossier - deterministic structural understanding of the lesson the
user is currently viewing.

The browser only knows surface facts (courseId, contentId, contentTitle).
For FILE / VIDEO lessons there is no page text at all, yet the index holds
a rich structure: knowledge nodes generated from the material, their place
in the course hierarchy, prerequisite relations, and chunk coverage stats.

This module turns that structure into a compact prompt block so the agent
understands WHERE it stands (course -> chapter -> node) before it reads
any raw in-page content. Everything here is verified index data - the same
source of truth `search_course_materials` retrieves from - never LLM
guesswork.

Envelope:

    {
        "course_id": int,
        "content_id": int,
        "index_status": str | None,     # content_index_status.status
        "chunks": int,                  # ready chunk count
        "page_span": [int, int] | None, # document page coverage
        "video_span_sec": [int, int] | None,
        "nodes": [
            {
                "id": int,
                "name": str,
                "level": int | None,
                "path": ["root", "chapter", ...],   # ancestor chain, root first
                "requires": [{"id": int, "name": str}, ...],
                "unlocks": [{"id": int, "name": str}, ...],
                "extends": [{"id": int, "name": str}, ...],
            },
            ...
        ],
    }

Cached per (course_id, content_id) with a short TTL; every query is
defensive - a dossier must never break a turn.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE: dict[tuple[int, int], tuple[float, dict]] = {}
_TTL_SECONDS = 60.0

_MAX_NODES = 4
_MAX_RELATIONS_PER_NODE = 6


async def load_lesson_dossier(course_id: int, content_id: int) -> Optional[dict]:
    """
    Build the structural dossier for one lesson from the AI index DB.

    Returns None when nothing is known about this content (never indexed,
    no nodes) so callers can skip the prompt section entirely.
    """
    try:
        course_id = int(course_id)
        content_id = int(content_id)
    except (TypeError, ValueError):
        return None
    if course_id <= 0 or content_id <= 0:
        return None

    cache_key = (course_id, content_id)
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    try:
        from app.core.database import get_ai_conn
    except Exception as exc:  # noqa: BLE001 - dossier is best-effort
        logger.warning("lesson_dossier db import failed: %s", exc)
        return None

    dossier: dict = {"course_id": course_id, "content_id": content_id}

    try:
        async with get_ai_conn() as conn:
            # -- 1. Index status -------------------------------------------------
            row = await conn.fetchrow(
                """SELECT title, status FROM content_index_status
                   WHERE content_id = $1 AND course_id = $2""",
                content_id, course_id,
            )
            if row:
                dossier["index_status"] = row["status"]
                if row.get("title"):
                    dossier.setdefault("title", row["title"])

            # -- 2. Chunk coverage ----------------------------------------------
            stats = await conn.fetchrow(
                """SELECT count(*)::int AS chunks,
                          MIN(page_number)::int AS min_page,
                          MAX(page_number)::int AS max_page,
                          MIN(start_time_sec)::int AS start_sec,
                          MAX(end_time_sec)::int AS end_sec
                   FROM document_chunks
                   WHERE content_id = $1 AND course_id = $2 AND status = 'ready'""",
                content_id, course_id,
            )
            chunks = int(stats["chunks"] or 0) if stats else 0
            dossier["chunks"] = chunks
            if stats:
                if stats["min_page"] is not None:
                    dossier["page_span"] = [stats["min_page"], stats["max_page"]]
                if stats["start_sec"] is not None:
                    dossier["video_span_sec"] = [stats["start_sec"], stats["end_sec"]]

            # -- 3. Knowledge nodes for this lesson ------------------------------
            # Primary source: nodes generated directly from this content.
            # Fallback: nodes that own its indexed chunks (covers legacy rows
            # whose source_content_id was never backfilled).
            node_rows = await conn.fetch(
                """SELECT id, parent_id, name, name_vi, level
                   FROM knowledge_nodes
                   WHERE course_id = $1 AND source_content_id = $2
                   ORDER BY level, order_index
                   LIMIT $3""",
                course_id, content_id, _MAX_NODES,
            )
            if not node_rows:
                node_rows = await conn.fetch(
                    """SELECT DISTINCT n.id, n.parent_id, n.name, n.name_vi, n.level
                       FROM document_chunks c
                       JOIN knowledge_nodes n ON n.id = c.node_id
                       WHERE c.content_id = $1 AND c.course_id = $2
                       ORDER BY n.level
                       LIMIT $3""",
                    content_id, course_id, _MAX_NODES,
                )

            node_ids = [r["id"] for r in node_rows]
            nodes: list[dict] = []
            if node_ids:
                id_list = node_ids[:_MAX_NODES]

                # Ancestor chains (course hierarchy position), root first.
                chain_map = await conn.fetch(
                    """WITH RECURSIVE chain(node_id, root_path) AS (
                           SELECT id, ARRAY[]::text[]
                           FROM knowledge_nodes WHERE id = ANY($1)
                           UNION ALL
                           SELECT k.id,
                                  chain.root_path || COALESCE(k.name_vi, k.name)
                           FROM knowledge_nodes k
                           JOIN chain c ON k.id = (
                               SELECT parent_id FROM knowledge_nodes
                               WHERE id = c.node_id
                           )
                       )
                       SELECT DISTINCT ON (node_id) node_id, root_path
                       FROM chain
                       ORDER BY node_id, array_length(root_path, 1) DESC NULLS LAST""",
                    id_list,
                )
                paths = {r["node_id"]: list(r["root_path"] or []) for r in chain_map}

                # Relations touching these nodes, strongest first.
                rel_rows = await conn.fetch(
                    """SELECT r.relation_type, r.source_node_id, r.target_node_id,
                              COALESCE(s.name_vi, s.name) AS src_name,
                              COALESCE(t.name_vi, t.name) AS tgt_name
                       FROM knowledge_node_relations r
                       JOIN knowledge_nodes s ON s.id = r.source_node_id
                       JOIN knowledge_nodes t ON t.id = r.target_node_id
                       WHERE r.course_id = $1
                         AND (r.source_node_id = ANY($2) OR r.target_node_id = ANY($2))
                       ORDER BY r.strength DESC
                       LIMIT 24""",
                    course_id, id_list,
                )
                rel_by_node: dict[int, dict[str, list]] = {}
                id_set = set(id_list)
                for rel in rel_rows:
                    stype = rel["relation_type"]
                    if stype == "prerequisite":
                        # Edge source -> target means the target builds on the
                        # source. From the owner node's perspective: if the
                        # owner is the target, it requires the source; if the
                        # owner is the source, it unlocks the target.
                        if rel["target_node_id"] in id_set:
                            bucket_key = "requires"
                            owner_id = rel["target_node_id"]
                            entry = {"id": rel["source_node_id"], "name": rel["src_name"]}
                        elif rel["source_node_id"] in id_set:
                            bucket_key = "unlocks"
                            owner_id = rel["source_node_id"]
                            entry = {"id": rel["target_node_id"], "name": rel["tgt_name"]}
                        else:
                            continue
                    elif stype == "extends":
                        # The target extends the source concept.
                        if rel["target_node_id"] not in id_set:
                            continue
                        bucket_key = "extends"
                        owner_id = rel["target_node_id"]
                        entry = {"id": rel["source_node_id"], "name": rel["src_name"]}
                    else:
                        continue

                    entries = rel_by_node.setdefault(owner_id, {}).setdefault(bucket_key, [])
                    if len(entries) < _MAX_RELATIONS_PER_NODE:
                        entries.append(entry)

                for r in node_rows[:_MAX_NODES]:
                    name = r.get("name_vi") or r["name"] or ""
                    nodes.append({
                        "id": r["id"],
                        "name": name,
                        "level": r.get("level"),
                        "path": paths.get(r["id"], []),
                        **rel_by_node.get(r["id"], {}),
                    })

            dossier["nodes"] = nodes

    except Exception as exc:  # noqa: BLE001 - dossier must never break a turn
        logger.warning(
            "lesson_dossier load failed course=%s content=%s err=%s",
            course_id, content_id, exc,
        )
        return None

    if not dossier.get("nodes") and not dossier.get("chunks") and not dossier.get("index_status"):
        return None

    _CACHE[cache_key] = (now + _TTL_SECONDS, dossier)
    return dossier


def format_lesson_dossier(dossier: Optional[dict]) -> str:
    """
    Render the dossier as a bounded prompt block. Returns "" when there is
    nothing to say so templates can drop the section cleanly.
    """
    if not dossier:
        return ""

    lines: list[str] = [
        "CURRENT LESSON STRUCTURE (verified from the course index)",
        "(Structural ground truth about the exact lesson on screen. Use "
        "`node_id` values for gap/diagnose tools; use "
        "`search_course_materials` scoped to this course/content for raw text.)",
        f"- Course: course_id={dossier['course_id']}",
        f"- Lesson: content_id={dossier['content_id']}"
        + (f" \"{str(dossier['title'])[:120]}\"" if dossier.get("title") else ""),
    ]

    status = dossier.get("index_status")
    if status:
        coverage = []
        if dossier.get("chunks"):
            coverage.append(f"{dossier['chunks']} indexed chunks")
        span = dossier.get("page_span")
        if span:
            coverage.append(f"pages {span[0]}-{span[1]}")
        vspan = dossier.get("video_span_sec")
        if vspan:
            coverage.append(f"transcript {vspan[0]}s-{vspan[1]}s")
        detail = f" ({'; '.join(coverage)})" if coverage else ""
        lines.append(f"- Index status: {status}{detail}")

    nodes = dossier.get("nodes") or []
    if nodes:
        lines.append("Knowledge nodes extracted from this lesson:")
        for n in nodes:
            line = f"  - node_id={n['id']} \"{n['name']}\""
            if n.get("level") is not None:
                line += f" (level {n['level']})"
            lines.append(line)
            path = n.get("path") or []
            if path:
                lines.append(f"      Position: {' > '.join(str(p) for p in path[-3:])}")
            for label, items in (
                ("Requires first", n.get("requires")),
                ("Extends", n.get("extends")),
                ("Unlocks", n.get("unlocks")),
            ):
                for item in (items or [])[:3]:
                    lines.append(f"      {label}: node_id={item['id']} \"{item['name']}\"")

    return "\n".join(lines)


def invalidate_lesson_dossier(course_id: int, content_id: Optional[int] = None) -> None:
    """Drop cached dossiers after re-indexing/mutation."""
    try:
        course_id = int(course_id)
    except (TypeError, ValueError):
        return
    if content_id is None:
        for key in [k for k in _CACHE if k[0] == course_id]:
            _CACHE.pop(key, None)
    else:
        _CACHE.pop((course_id, int(content_id)), None)
