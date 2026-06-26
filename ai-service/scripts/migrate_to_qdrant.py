#!/usr/bin/env python3
"""
ai-service/scripts/migrate_to_qdrant.py

One-shot migration: copy all existing embeddings from AI PostgreSQL (pgvector)
to Qdrant collections.

Safety properties:
  - Idempotent: re-running skips points already in Qdrant (upsert semantics).
  - Non-destructive: does NOT drop the pgvector columns. Once verified, you
    can remove them manually with the SQL snippet printed at the end.
  - Dry-run mode: --dry-run counts rows and tests connectivity without writing.
  - Progress bar via tqdm (optional, falls back to plain logging).

Usage:
  python scripts/migrate_to_qdrant.py [--dry-run] [--batch-size 256] [--course-id 42]

Environment variables (same as .env):
  AI_DB_HOST, AI_DB_PORT, AI_DB_USER, AI_DB_PASSWORD, AI_DB_NAME
  QDRANT_HOST, QDRANT_PORT, QDRANT_GRPC_PORT, QDRANT_PREFER_GRPC, QDRANT_API_KEY
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── DB + Qdrant helpers ───────────────────────────────────────────────────────

def _pg_conn(host, port, user, password, dbname):
    import psycopg2
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
    conn.autocommit = True
    return conn


def _qdrant_client(host, port, grpc_port, prefer_grpc, api_key):
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=host,
        port=grpc_port if prefer_grpc else port,
        grpc_port=grpc_port,
        prefer_grpc=prefer_grpc,
        api_key=api_key or None,
        timeout=60,
    )


VECTOR_SIZE      = 1024
CHUNK_COLLECTION = "document_chunks"
NODE_COLLECTION  = "knowledge_nodes"


def _ensure_collection(client, name: str) -> None:
    from qdrant_client.http.models import Distance, VectorParams, HnswConfigDiff, OptimizersConfigDiff
    if client.collection_exists(name):
        log.info("Collection already exists: %s", name)
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE, on_disk=True),
        hnsw_config=HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10_000, on_disk=False),
        optimizers_config=OptimizersConfigDiff(indexing_threshold=20_000),
    )
    log.info("Created collection: %s", name)


# ── Chunk migration ───────────────────────────────────────────────────────────

def migrate_chunks(
    pg_conn,
    qdrant,
    batch_size: int,
    dry_run: bool,
    course_id: Optional[int],
) -> dict:
    import psycopg2.extras
    from qdrant_client.http.models import PointStruct

    cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = "WHERE embedding IS NOT NULL AND status='ready'"
    params: list = []
    if course_id is not None:
        where += " AND course_id = %s"
        params.append(course_id)

    cur.execute(f"SELECT COUNT(*) AS n FROM document_chunks {where}", params)
    total = cur.fetchone()["n"]
    log.info("document_chunks to migrate: %d", total)

    if dry_run or total == 0:
        return {"collection": CHUNK_COLLECTION, "total": total, "migrated": 0}

    sql = f"""
        SELECT id, chunk_text, chunk_index, chunk_hash,
               content_id, course_id, node_id,
               source_type, page_number, start_time_sec, end_time_sec,
               language, status, embedding::text AS embedding_text
        FROM document_chunks {where}
        ORDER BY id
        LIMIT %s OFFSET %s
    """

    migrated = 0
    offset   = 0
    t0       = time.perf_counter()

    while True:
        cur.execute(sql, params + [batch_size, offset])
        rows = cur.fetchall()
        if not rows:
            break

        points = []
        for row in rows:
            emb_text = row["embedding_text"]
            if not emb_text:
                continue
            emb = [float(x) for x in emb_text.strip("[]").split(",")]

            payload: dict = {
                "chunk_text":  row["chunk_text"],
                "chunk_index": row["chunk_index"],
                "chunk_hash":  row["chunk_hash"],
                "course_id":   row["course_id"],
                "source_type": row["source_type"],
                "language":    row["language"] or "vi",
                "status":      row["status"] or "ready",
            }
            if row["content_id"]    is not None: payload["content_id"]    = row["content_id"]
            if row["node_id"]       is not None: payload["node_id"]       = row["node_id"]
            if row["page_number"]   is not None: payload["page_number"]   = row["page_number"]
            if row["start_time_sec"] is not None: payload["start_time_sec"] = row["start_time_sec"]
            if row["end_time_sec"]  is not None: payload["end_time_sec"]  = row["end_time_sec"]

            points.append(PointStruct(id=row["id"], vector=emb, payload=payload))

        if points:
            qdrant.upsert(collection_name=CHUNK_COLLECTION, points=points, wait=True)
            migrated += len(points)

        offset += len(rows)
        elapsed = time.perf_counter() - t0
        rate    = migrated / elapsed if elapsed > 0 else 0
        log.info("  chunks: %d/%d (%.0f pts/s)", migrated, total, rate)

    cur.close()
    return {"collection": CHUNK_COLLECTION, "total": total, "migrated": migrated}


# ── Node migration ────────────────────────────────────────────────────────────

def migrate_nodes(
    pg_conn,
    qdrant,
    batch_size: int,
    dry_run: bool,
    course_id: Optional[int],
) -> dict:
    import psycopg2.extras
    from qdrant_client.http.models import PointStruct

    cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = "WHERE description_embedding IS NOT NULL"
    params: list = []
    if course_id is not None:
        where += " AND course_id = %s"
        params.append(course_id)

    cur.execute(f"SELECT COUNT(*) AS n FROM knowledge_nodes {where}", params)
    total = cur.fetchone()["n"]
    log.info("knowledge_nodes to migrate: %d", total)

    if dry_run or total == 0:
        return {"collection": NODE_COLLECTION, "total": total, "migrated": 0}

    sql = f"""
        SELECT id, course_id, name, name_vi, name_en, description,
               level, auto_generated, source_content_id,
               description_embedding::text AS embedding_text
        FROM knowledge_nodes {where}
        ORDER BY id
        LIMIT %s OFFSET %s
    """

    migrated = 0
    offset   = 0

    while True:
        cur.execute(sql, params + [batch_size, offset])
        rows = cur.fetchall()
        if not rows:
            break

        points = []
        for row in rows:
            emb_text = row["embedding_text"]
            if not emb_text:
                continue
            emb = [float(x) for x in emb_text.strip("[]").split(",")]

            payload: dict = {
                "course_id":      row["course_id"],
                "name":           row["name"],
                "name_vi":        row["name_vi"] or "",
                "name_en":        row["name_en"] or "",
                "description":    row["description"] or "",
                "level":          row["level"] or 0,
                "auto_generated": bool(row["auto_generated"]),
            }
            if row["source_content_id"] is not None:
                payload["source_content_id"] = row["source_content_id"]

            points.append(PointStruct(id=row["id"], vector=emb, payload=payload))

        if points:
            qdrant.upsert(collection_name=NODE_COLLECTION, points=points, wait=True)
            migrated += len(points)

        offset += len(rows)
        log.info("  nodes: %d/%d", migrated, total)

    cur.close()
    return {"collection": NODE_COLLECTION, "total": total, "migrated": migrated}


# ── Verification ──────────────────────────────────────────────────────────────

def verify(qdrant, pg_conn, course_id: Optional[int]) -> bool:
    import psycopg2.extras
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue

    cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    ok = True
    for table, collection in [
        ("document_chunks WHERE embedding IS NOT NULL AND status='ready'", CHUNK_COLLECTION),
        ("knowledge_nodes WHERE description_embedding IS NOT NULL",         NODE_COLLECTION),
    ]:
        where = table
        params: list = []
        if course_id is not None:
            where += " AND course_id = %s"
            params.append(course_id)

        cur.execute(f"SELECT COUNT(*) AS n FROM {where}", params)
        pg_count = cur.fetchone()["n"]

        count_filter = None
        if course_id is not None:
            count_filter = Filter(
                must=[FieldCondition(key="course_id", match=MatchValue(value=course_id))]
            )
        q_result = qdrant.count(collection_name=collection, count_filter=count_filter, exact=True)
        q_count  = q_result.count

        match = "✓" if q_count >= pg_count else "✗"
        log.info("%s %s -> PG=%d Qdrant=%d", match, collection, pg_count, q_count)

        if q_count < pg_count:
            log.warning("  Missing %d vectors in Qdrant!", pg_count - q_count)
            ok = False

    cur.close()
    return ok


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate pgvector embeddings to Qdrant")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--course-id",  type=int, default=None)
    parser.add_argument("--skip-chunks", action="store_true")
    parser.add_argument("--skip-nodes",  action="store_true")
    args = parser.parse_args()

    # ── Read config from environment ──────────────────────────────────────────
    ai_host  = os.getenv("AI_DB_HOST",     "postgres-ai")
    ai_port  = int(os.getenv("AI_DB_PORT", "5432"))
    ai_user  = os.getenv("AI_DB_USER",     "ai_user")
    ai_pass  = os.getenv("AI_DB_PASSWORD", "ai_password")
    ai_db    = os.getenv("AI_DB_NAME",     "ai_db")

    q_host      = os.getenv("QDRANT_HOST",         "qdrant")
    q_port      = int(os.getenv("QDRANT_PORT",      "6333"))
    q_grpc_port = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
    q_prefer_grpc = os.getenv("QDRANT_PREFER_GRPC", "true").lower() == "true"
    q_api_key   = os.getenv("QDRANT_API_KEY", "")

    log.info("=== Qdrant Migration%s ===", " (DRY RUN)" if args.dry_run else "")

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        pg = _pg_conn(ai_host, ai_port, ai_user, ai_pass, ai_db)
        log.info("Connected to AI PostgreSQL at %s:%d/%s", ai_host, ai_port, ai_db)
    except Exception as exc:
        log.error("PG connection failed: %s", exc)
        return 1

    try:
        qd = _qdrant_client(q_host, q_port, q_grpc_port, q_prefer_grpc, q_api_key)
        log.info("Connected to Qdrant at %s", q_host)
    except Exception as exc:
        log.error("Qdrant connection failed: %s", exc)
        return 1

    # ── Ensure collections exist ──────────────────────────────────────────────
    if not args.dry_run:
        _ensure_collection(qd, CHUNK_COLLECTION)
        _ensure_collection(qd, NODE_COLLECTION)

    # ── Migrate ───────────────────────────────────────────────────────────────
    results = []
    t_start = time.perf_counter()

    if not args.skip_chunks:
        log.info("── Migrating document_chunks ──")
        r = migrate_chunks(pg, qd, args.batch_size, args.dry_run, args.course_id)
        results.append(r)

    if not args.skip_nodes:
        log.info("── Migrating knowledge_nodes ──")
        r = migrate_nodes(pg, qd, args.batch_size, args.dry_run, args.course_id)
        results.append(r)

    elapsed = time.perf_counter() - t_start

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("\n=== Migration Summary (%.1fs) ===", elapsed)
    total_migrated = 0
    for r in results:
        log.info("  %-25s total=%-8d migrated=%d", r["collection"], r["total"], r["migrated"])
        total_migrated += r["migrated"]
    log.info("  Total migrated: %d", total_migrated)

    # ── Verify ────────────────────────────────────────────────────────────────
    if not args.dry_run and total_migrated > 0:
        log.info("\n── Verification ──")
        ok = verify(qd, pg, args.course_id)
        if ok:
            log.info("\n✓ Migration verified successfully!")
            log.info(
                "\nOnce you are satisfied with Qdrant performance, you can "
                "reclaim disk space from AI PostgreSQL by running:\n\n"
                "  ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding;\n"
                "  ALTER TABLE knowledge_nodes DROP COLUMN IF EXISTS description_embedding;\n"
                "  ALTER TABLE knowledge_nodes DROP COLUMN IF EXISTS description_embedding_v2;\n\n"
                "NOTE: Only do this after setting USE_QDRANT=true in production "
                "and verifying for at least 24 hours."
            )
        else:
            log.error("\n✗ Verification failed - some vectors are missing. Re-run migration.")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())