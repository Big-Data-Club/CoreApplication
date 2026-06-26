"""
ai-service/scripts/migrate_ai_data.py

Phase 1 data migration: copies AI-domain tables from the shared LMS PostgreSQL
instance to the new isolated AI PostgreSQL instance.

Usage:
    python scripts/migrate_ai_data.py [--dry-run] [--tables TABLE ...]

Options:
    --dry-run     Verify connectivity and count rows without copying data.
    --tables      Space-separated list of tables to migrate (default: all).
    --batch-size  Rows per INSERT batch (default: 500).

The script is idempotent: re-running it will not duplicate rows because each
table uses ON CONFLICT DO NOTHING based on the primary key.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Table definitions ─────────────────────────────────────────────────────────

@dataclass
class TableSpec:
    name: str
    pk: str = "id"
    # Columns that reference LMS entities become plain BIGINTs in AI DB -
    # no FK constraint, just data copy. List them here for documentation.
    soft_refs: list[str] = field(default_factory=list)


# Ordered so that FK-dependency is respected within the AI domain:
#   knowledge_nodes -> knowledge_node_relations
#   knowledge_nodes -> document_chunks
#   document_chunks -> ai_quiz_generations
#   knowledge_nodes -> student_knowledge_progress / spaced_repetitions / flashcards
#   ai_diagnoses    -> flashcards
TABLES: list[TableSpec] = [
    TableSpec("knowledge_nodes",           soft_refs=["course_id", "source_content_id"]),
    TableSpec("knowledge_node_relations",  soft_refs=["course_id"]),
    TableSpec("document_chunks",           soft_refs=["content_id", "course_id"]),
    TableSpec("document_processing_jobs",  soft_refs=["content_id", "course_id"]),
    TableSpec("ai_diagnoses",              soft_refs=["student_id", "attempt_id", "question_id"]),
    TableSpec("student_knowledge_progress",soft_refs=["student_id", "course_id"]),
    TableSpec("spaced_repetitions",        soft_refs=["student_id", "question_id", "course_id"]),
    TableSpec("ai_quiz_generations",       soft_refs=["course_id", "created_by", "reviewed_by", "quiz_question_id"]),
    TableSpec("flashcards",                soft_refs=["course_id", "student_id"]),
    TableSpec("flashcard_repetitions",     soft_refs=["student_id", "course_id"]),
    TableSpec("embedding_reindex_jobs",    soft_refs=["course_id", "content_id"]),
]

TABLE_BY_NAME = {t.name: t for t in TABLES}


# ── DB connection helpers ─────────────────────────────────────────────────────

def _pg_conn(prefix: str) -> psycopg2.extensions.connection:
    """Build a psycopg2 connection from environment variables."""
    host     = os.environ[f"{prefix}_DB_HOST"]
    port     = os.environ.get(f"{prefix}_DB_PORT", "5432")
    user     = os.environ[f"{prefix}_DB_USER"]
    password = os.environ[f"{prefix}_DB_PASSWORD"]
    dbname   = os.environ[f"{prefix}_DB_NAME"]

    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=dbname
    )
    conn.autocommit = False
    return conn


# ── Column introspection ──────────────────────────────────────────────────────

def get_columns(cur, table: str) -> list[str]:
    """Return column names present in BOTH source and destination tables."""
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row["column_name"] for row in cur.fetchall()]


# ── Core migration ────────────────────────────────────────────────────────────

def migrate_table(
    src_cur: psycopg2.extensions.cursor,
    dst_cur: psycopg2.extensions.cursor,
    dst_conn: psycopg2.extensions.connection,
    spec: TableSpec,
    batch_size: int,
    dry_run: bool,
) -> dict[str, Any]:
    """
    Copy one table from source to destination.

    Returns a summary dict: {table, rows_read, rows_inserted, rows_skipped, elapsed_s}.
    """
    t0 = time.perf_counter()

    # Count source rows
    src_cur.execute(f"SELECT COUNT(*) AS n FROM {spec.name}")
    total = src_cur.fetchone()["n"]
    log.info("  %s - %d rows to migrate", spec.name, total)

    if dry_run or total == 0:
        return {"table": spec.name, "rows_read": total,
                "rows_inserted": 0, "rows_skipped": 0,
                "elapsed_s": time.perf_counter() - t0}

    # Discover columns that exist in BOTH databases
    src_cols = get_columns(src_cur, spec.name)
    dst_cols = get_columns(dst_cur, spec.name)
    common   = [c for c in src_cols if c in set(dst_cols)]

    col_list   = ", ".join(common)
    placeholders = ", ".join(["%s"] * len(common))
    # Skip rows that already exist (idempotent re-runs)
    upsert_sql = (
        f"INSERT INTO {spec.name} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({spec.pk}) DO NOTHING"
    )

    rows_inserted = 0
    rows_skipped  = 0
    offset        = 0

    while True:
        src_cur.execute(
            f"SELECT {col_list} FROM {spec.name} ORDER BY {spec.pk} "
            f"LIMIT %s OFFSET %s",
            (batch_size, offset),
        )
        rows = src_cur.fetchall()
        if not rows:
            break

        batch_values = [
            tuple(
                json.dumps(row[c], ensure_ascii=False)
                if isinstance(row[c], (dict, list)) else row[c]
                for c in common
            )
            for row in rows
        ]
        psycopg2.extras.execute_batch(dst_cur, upsert_sql, batch_values)
        dst_conn.commit()

        # Count actual inserts vs skips
        inserted_in_batch = sum(
            1 for row in rows
            if _row_was_inserted(dst_cur, spec, row[spec.pk])
        )
        rows_inserted += dst_cur.rowcount if dst_cur.rowcount >= 0 else len(rows)
        rows_skipped  += len(rows) - max(0, dst_cur.rowcount)
        offset        += len(rows)
        pct = min(100, round(offset / total * 100))
        log.info("    %s - %d%% (%d/%d)", spec.name, pct, offset, total)

    elapsed = time.perf_counter() - t0
    return {
        "table":        spec.name,
        "rows_read":    total,
        "rows_inserted": rows_inserted,
        "rows_skipped": rows_skipped,
        "elapsed_s":    round(elapsed, 2),
    }


def _row_was_inserted(cur, spec: TableSpec, pk_value: Any) -> bool:
    """Quick existence check - used only for accurate counting, not hot path."""
    try:
        cur.execute(
            f"SELECT 1 FROM {spec.name} WHERE {spec.pk} = %s", (pk_value,)
        )
        return cur.fetchone() is not None
    except Exception:
        return False


# ── Reset sequences after bulk copy ──────────────────────────────────────────

def reset_sequences(cur, conn, tables: list[str]) -> None:
    """
    After bulk COPY the serial sequences may be behind the max ID.
    Reset each to max(id)+1 so future INSERTs don't collide.
    """
    for table in tables:
        try:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 1)) FROM {table}"
            )
            conn.commit()
            log.info("  Sequence reset: %s", table)
        except Exception as exc:
            log.warning("  Could not reset sequence for %s: %s", table, exc)
            conn.rollback()


# ── Connectivity checks ───────────────────────────────────────────────────────

def verify_connectivity(src_conn, dst_conn) -> None:
    with src_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT version()")
        log.info("Source DB: %s", cur.fetchone()["version"][:60])
    with dst_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT version()")
        log.info("Dest   DB: %s", cur.fetchone()["version"][:60])
        # Verify pgvector installed
        cur.execute("SELECT 1 FROM pg_extension WHERE extname='vector'")
        if not cur.fetchone():
            raise RuntimeError("pgvector is not installed in the destination DB")
        log.info("Dest   DB: pgvector ✓")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate AI tables LMS PG -> AI PG")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Count rows only, do not copy data")
    parser.add_argument("--tables",     nargs="*", metavar="TABLE",
                        help="Tables to migrate (default: all)")
    parser.add_argument("--batch-size", type=int, default=500, metavar="N",
                        help="INSERT batch size (default: 500)")
    args = parser.parse_args()

    # Resolve table list
    selected_names = args.tables or [t.name for t in TABLES]
    unknown = set(selected_names) - set(TABLE_BY_NAME)
    if unknown:
        log.error("Unknown table(s): %s", ", ".join(sorted(unknown)))
        return 1
    selected = [TABLE_BY_NAME[n] for n in selected_names]

    log.info("=== AI Data Migration%s ===", " (DRY RUN)" if args.dry_run else "")
    log.info("Tables: %s", ", ".join(t.name for t in selected))

    # Connect
    try:
        src_conn = _pg_conn("LMS")
        dst_conn = _pg_conn("AI")
    except KeyError as exc:
        log.error("Missing environment variable: %s", exc)
        log.error(
            "Required: LMS_DB_HOST, LMS_DB_PORT, LMS_DB_USER, LMS_DB_PASSWORD, LMS_DB_NAME"
            " and AI_DB_HOST, AI_DB_PORT, AI_DB_USER, AI_DB_PASSWORD, AI_DB_NAME"
        )
        return 1
    except psycopg2.OperationalError as exc:
        log.error("DB connection failed: %s", exc)
        return 1

    try:
        verify_connectivity(src_conn, dst_conn)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    src_cur = src_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    dst_cur = dst_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Migrate
    results: list[dict] = []
    errors:  list[str]  = []

    for spec in selected:
        log.info("── Migrating: %s ──", spec.name)
        try:
            result = migrate_table(src_cur, dst_cur, dst_conn, spec, args.batch_size, args.dry_run)
            results.append(result)
        except Exception as exc:
            log.error("  FAILED %s: %s", spec.name, exc)
            dst_conn.rollback()
            errors.append(f"{spec.name}: {exc}")

    # Reset sequences (skip in dry-run)
    if not args.dry_run:
        log.info("── Resetting sequences ──")
        reset_sequences(dst_cur, dst_conn, [r["table"] for r in results])

    # Summary
    log.info("\n=== Migration Summary ===")
    total_rows = 0
    for r in results:
        log.info(
            "  %-35s  read=%d  inserted=%d  skipped=%d  %.1fs",
            r["table"], r["rows_read"], r["rows_inserted"], r["rows_skipped"], r["elapsed_s"],
        )
        total_rows += r["rows_read"]

    log.info("Total rows read: %d", total_rows)
    if errors:
        log.error("Errors (%d):", len(errors))
        for e in errors:
            log.error("  %s", e)
        return 1

    log.info("Done.%s", " (dry run - no data written)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())