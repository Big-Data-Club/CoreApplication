"""
ai-service/scripts/migrate_to_neo4j.py

Migrate existing knowledge graph từ PostgreSQL + Qdrant vào Neo4j.

Steps:
  1. Đọc tất cả knowledge_nodes từ PostgreSQL (AI DB)
  2. Đọc embeddings từ Qdrant (knowledge_nodes collection)
  3. Upsert nodes vào Neo4j
  4. Đọc knowledge_node_relations từ PostgreSQL -> upsert edges vào Neo4j
  5. Chạy cross-course smart linking cho tất cả nodes

Usage:
  python scripts/migrate_to_neo4j.py [--dry-run] [--skip-cross-course]

Options:
  --dry-run           In ra số lượng, không ghi vào Neo4j
  --skip-cross-course Bỏ qua bước LLM cross-course linking (nhanh hơn)
  --course-id N       Chỉ migrate một course cụ thể
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Thêm app vào path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def migrate(
    dry_run: bool = False,
    skip_cross_course: bool = False,
    course_id_filter: int | None = None,
) -> None:
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.neo4j_enabled:
        log.error("NEO4J_ENABLED=false - set it to true before migrating")
        return

    # ── 1. Init connections ────────────────────────────────────────────────────
    from app.core.database import init_ai_pool, close_ai_pool, get_ai_conn
    from app.services.neo4j_service import neo4j_service
    from app.services.qdrant_service import qdrant_service

    await asyncio.gather(init_ai_pool())
    await neo4j_service.init()

    t0 = time.perf_counter()

    try:
        # ── 2. Đọc knowledge_nodes từ PostgreSQL ───────────────────────────────
        log.info("── Step 1: Reading knowledge_nodes from PostgreSQL ──")
        async with get_ai_conn() as conn:
            if course_id_filter:
                rows = await conn.fetch(
                    """
                    SELECT id, course_id, name, name_vi, name_en,
                           description, auto_generated, source_content_id
                    FROM knowledge_nodes
                    WHERE course_id = $1
                    ORDER BY id
                    """,
                    course_id_filter,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, course_id, name, name_vi, name_en,
                           description, auto_generated, source_content_id
                    FROM knowledge_nodes
                    ORDER BY id
                    """
                )

        nodes_pg = [dict(r) for r in rows]
        log.info("  Found %d knowledge nodes", len(nodes_pg))

        if not nodes_pg:
            log.warning("No nodes found - nothing to migrate")
            return

        if dry_run:
            log.info("[DRY RUN] Would upsert %d nodes to Neo4j", len(nodes_pg))
        else:
            # ── 3. Upsert nodes vào Neo4j (batch 500) ─────────────────────────
            log.info("── Step 2: Upserting nodes to Neo4j ──")
            batch_size = 500
            for i in range(0, len(nodes_pg), batch_size):
                batch = nodes_pg[i: i + batch_size]
                neo4j_batch = [
                    {
                        "id":               n["id"],
                        "course_id":        n["course_id"],
                        "name":             n["name"] or "",
                        "name_vi":          n["name_vi"] or "",
                        "name_en":          n["name_en"] or "",
                        "description":      n["description"] or "",
                        "auto_generated":   bool(n["auto_generated"]),
                        "source_content_id": n["source_content_id"] or 0,
                    }
                    for n in batch
                ]
                await neo4j_service.upsert_nodes_batch(neo4j_batch)
                log.info("  Upserted %d/%d nodes", min(i + batch_size, len(nodes_pg)), len(nodes_pg))

        # ── 4. Đọc knowledge_node_relations từ PostgreSQL ─────────────────────
        log.info("── Step 3: Reading knowledge_node_relations from PostgreSQL ──")
        node_ids = [n["id"] for n in nodes_pg]

        async with get_ai_conn() as conn:
            if course_id_filter:
                rel_rows = await conn.fetch(
                    """
                    SELECT source_node_id, target_node_id,
                           relation_type, strength, auto_generated
                    FROM knowledge_node_relations
                    WHERE course_id = $1
                    """,
                    course_id_filter,
                )
            else:
                rel_rows = await conn.fetch(
                    """
                    SELECT source_node_id, target_node_id,
                           relation_type, strength, auto_generated
                    FROM knowledge_node_relations
                    """
                )

        relations_pg = [dict(r) for r in rel_rows]
        log.info("  Found %d relations", len(relations_pg))

        if dry_run:
            log.info("[DRY RUN] Would upsert %d edges to Neo4j", len(relations_pg))
        else:
            # ── 5. Upsert edges vào Neo4j ──────────────────────────────────────
            log.info("── Step 4: Upserting edges to Neo4j ──")

            from app.services.neo4j_service import RELATIONSHIP_TYPES

            # Map PostgreSQL relation_type -> Neo4j relationship type constant
            def _map_rel_type(pg_type: str) -> str:
                mapping = {
                    "prerequisite":   "PREREQUISITE",
                    "related":        "RELATED",
                    "extends":        "EXTENDS",
                    "equivalent":     "EQUIVALENT",
                    "contrasts_with": "CONTRASTS_WITH",
                }
                return mapping.get((pg_type or "related").lower(), "RELATED")

            neo4j_edges = [
                {
                    "source_id":      r["source_node_id"],
                    "target_id":      r["target_node_id"],
                    "rel_type":       _map_rel_type(r["relation_type"]),
                    "strength":       float(r["strength"] or 0.5),
                    "auto_generated": bool(r["auto_generated"]),
                    "cross_course":   False,   # existing PG rels are intra-course
                    "reason":         "Migrated from PostgreSQL",
                }
                for r in relations_pg
            ]

            batch_size = 500
            for i in range(0, len(neo4j_edges), batch_size):
                batch = neo4j_edges[i: i + batch_size]
                await neo4j_service.upsert_relationships_batch(batch)
                log.info("  Upserted %d/%d edges", min(i + batch_size, len(neo4j_edges)), len(neo4j_edges))

        # ── 6. Cross-course smart linking ──────────────────────────────────────
        if skip_cross_course or dry_run:
            log.info("── Step 5: Skipping cross-course linking ──")
        else:
            log.info("── Step 5: Cross-course smart linking ──")
            log.info("  Fetching embeddings from Qdrant for all nodes...")

            await _run_cross_course_linking(nodes_pg)

        # ── 7. Verify ──────────────────────────────────────────────────────────
        if not dry_run:
            log.info("── Verification ──")
            health = await neo4j_service.health()
            log.info(
                "  Neo4j: %d nodes, %d edges, %d courses",
                health.get("total_nodes", 0),
                health.get("total_edges", 0),
                health.get("total_courses", 0),
            )

        elapsed = time.perf_counter() - t0
        log.info("\n✓ Migration completed in %.1fs", elapsed)
        if dry_run:
            log.info("(DRY RUN - no data written)")

    finally:
        await neo4j_service.close()
        await close_ai_pool()


async def _run_cross_course_linking(nodes_pg: list[dict]) -> None:
    """
    Group nodes by course, then for each course call link_cross_course.
    This enriches cross-course relationships using LLM + embeddings.
    """
    from collections import defaultdict
    from app.services.graph_linker import NodeInfo, link_cross_course
    from app.services.qdrant_service import qdrant_service

    # Group by course
    by_course: dict[int, list[dict]] = defaultdict(list)
    for n in nodes_pg:
        by_course[int(n["course_id"])].append(n)

    log.info("  %d courses to process for cross-course linking", len(by_course))

    # Fetch all node embeddings from Qdrant once (batch)
    log.info("  Fetching all node vectors from Qdrant...")
    all_node_ids = [n["id"] for n in nodes_pg]
    id_to_embedding: dict[int, list[float]] = {}

    # Scroll all nodes from Qdrant
    try:
        client = qdrant_service._get_client()
        offset = None
        while True:
            records, next_offset = await client.scroll(
                collection_name="knowledge_nodes",
                limit=500,
                offset=offset,
                with_vectors=True,
                with_payload=False,
            )
            for r in records:
                if r.vector is not None:
                    id_to_embedding[int(r.id)] = r.vector
            if next_offset is None or not records:
                break
            offset = next_offset
        log.info("  Loaded %d node embeddings from Qdrant", len(id_to_embedding))
    except Exception as exc:
        log.warning("  Could not fetch embeddings from Qdrant: %s", exc)
        log.warning("  Skipping cross-course linking (no embeddings available)")
        return

    if not id_to_embedding:
        log.warning("  No embeddings in Qdrant - skipping cross-course linking")
        log.info("  Tip: Run auto-index with force=True to re-generate embeddings")
        return

    # Build NodeInfo objects per course
    course_node_infos: dict[int, list[NodeInfo]] = {}
    for course_id, course_nodes in by_course.items():
        infos = []
        for n in course_nodes:
            emb = id_to_embedding.get(int(n["id"]))
            if emb is None:
                continue  # Skip nodes without embeddings
            infos.append(NodeInfo(
                id=int(n["id"]),
                course_id=int(n["course_id"]),
                name=n["name"] or "",
                description=n["description"] or "",
                embedding=emb,
            ))
        if infos:
            course_node_infos[course_id] = infos

    total_embedded = sum(len(v) for v in course_node_infos.values())
    log.info("  %d nodes have embeddings (out of %d total)", total_embedded, len(nodes_pg))

    # Process one course at a time - pass its nodes to cross-course linker
    total_edges = 0
    for i, (course_id, node_infos) in enumerate(course_node_infos.items(), 1):
        log.info(
            "  [%d/%d] Cross-course linking course %d (%d nodes)...",
            i, len(course_node_infos), course_id, len(node_infos),
        )
        try:
            count = await link_cross_course(
                new_nodes=node_infos,
                new_course_id=course_id,
            )
            total_edges += count
            log.info("    -> %d new cross-course edges", count)
        except Exception as exc:
            log.warning("    Failed for course %d: %s", course_id, exc)

    log.info("  Total cross-course edges created: %d", total_edges)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate knowledge graph to Neo4j")
    parser.add_argument("--dry-run",           action="store_true",
                        help="Count rows only, don't write to Neo4j")
    parser.add_argument("--skip-cross-course", action="store_true",
                        help="Skip LLM cross-course linking step")
    parser.add_argument("--course-id",         type=int, default=None,
                        help="Only migrate a specific course")
    args = parser.parse_args()

    asyncio.run(migrate(
        dry_run=args.dry_run,
        skip_cross_course=args.skip_cross_course,
        course_id_filter=args.course_id,
    ))


if __name__ == "__main__":
    main()