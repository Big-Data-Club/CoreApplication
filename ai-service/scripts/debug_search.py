"""
Layer-by-layer RAG debug probe.

Answers "why does query X return nothing?" by printing each stage:
  1. PG chunk inventory for the scope (status / level / counts)
  2. content_index_status rows
  3. Keyword-only search (AND leg + OR fallback)
  4. Vector-only search with threshold DISABLED (top raw scores)
  5. The full pipeline result (multilingual + rerank + thresholds)

Usage (inside the ai-service environment):
    python scripts/debug_search.py --query "phương pháp ra quyết định" [--course-id 12]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _head(text: str, n: int = 140) -> str:
    text = " ".join((text or "").split())
    return text[:n] + ("…" if len(text) > n else "")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--course-id", type=int, default=None)
    ap.add_argument("--content-id", type=int, default=None)
    args = ap.parse_args()

    from app.core.database import get_ai_conn
    from app.services.rag_service import rag_service

    print(f"═══ RAG DEBUG: {args.query!r} (course={args.course_id}, content={args.content_id}) ═══\n")

    # ── 1. Chunk inventory ────────────────────────────────────────────────
    async with get_ai_conn() as conn:
        conds, params = ["1=1"], []
        if args.course_id is not None:
            conds.append("course_id = $1"); params.append(args.course_id)
        if args.content_id is not None:
            conds.append(f"content_id = ${len(params)+1}"); params.append(args.content_id)
        where = " AND ".join(conds)

        rows = await conn.fetch(
            f"""SELECT status, chunk_level, count(*) AS n
                FROM document_chunks WHERE {where}
                GROUP BY status, chunk_level ORDER BY status, chunk_level""",
            *params,
        )
        print("[1] document_chunks inventory:")
        if not rows:
            print("    ⚠️ NO CHUNKS AT ALL for this scope → data was never indexed here.")
        for r in rows:
            print(f"    status={r['status']:<8} level={r['chunk_level']:<7} n={r['n']}")

        like = f"%{args.query}%"
        hits = await conn.fetch(
            f"""SELECT content_id, page_number,
                       left(replace(chunk_text, E'\\n', ' '), 100) AS head
                FROM document_chunks
                WHERE {where} AND chunk_text ILIKE {f"${len(params)+1}"}
                LIMIT 5""",
            *params, like,
        )
        print(f"\n[1b] ILIKE substring hits: {len(hits)}")
        for h in hits:
            print(f"    c{h['content_id']} p{h['page_number']}: {_head(h['head'], 90)}")

        idx_rows = await conn.fetch(
            f"""SELECT content_id, status, node_id, updated_at
                FROM content_index_status
                WHERE ($1::int IS NULL OR course_hint = $1)
                   OR ($2::int IS NULL OR content_id = $2)
                LIMIT 10""",
            args.course_id, args.content_id,
        )
        try:
            pass
        except Exception:
            pass
        # column names may differ across deployments - tolerate failures
        if idx_rows:
            print("\n[2] content_index_status:")
            for r in idx_rows:
                print(f"    content={r['content_id']} status={r['status']} updated={r['updated_at']}")

    # ── 3. Keyword-only ───────────────────────────────────────────────────
    kw = await rag_service._keyword_search(
        query=args.query, course_id=args.course_id,
        content_id=args.content_id, top_k=10,
    )
    print(f"\n[3] Keyword leg: {len(kw)} results")
    for c in kw[:5]:
        print(f"    score={c.similarity:.3f} c{c.content_id}: {_head(c.chunk_text)}")

    # ── 4. Vector-only, NO threshold ──────────────────────────────────────
    vec = await rag_service.search(
        query=args.query, course_id=args.course_id,
        content_id=args.content_id, top_k=10, min_similarity=0.0,
    )
    print(f"\n[4] Vector leg (threshold OFF), top scores:")
    for c in vec[:8]:
        mark = "✅" if c.similarity >= 0.25 else ("🟡" if c.similarity >= 0.15 else "❌")
        print(f"    {mark} {c.similarity:.3f} c{c.content_id}: {_head(c.chunk_text)}")

    # ── 5. Full pipeline as production runs it ────────────────────────────
    final = await rag_service.search_multilingual(
        query=args.query, course_id=args.course_id,
        content_id=args.content_id, top_k=5, min_similarity=0.25,
    )
    print(f"\n[5] Full pipeline result: {len(final)} chunks")
    for c in final[:5]:
        print(f"    {c.similarity:.3f} c{c.content_id}: {_head(c.chunk_text)}")

    print("\n═══ Diagnosis hints ═══")
    if not vec:
        print("• Vector empty even with threshold OFF → embeddings missing for this")
        print("  scope (wrong course_id payload? indexing job failed? Qdrant collection mismatch).")
    elif all(c.similarity < 0.25 for c in vec):
        top = max(vec, key=lambda c: c.similarity)
        print(f"• Vector has data but best score is only {top.similarity:.3f} (<0.25 threshold).")
        print("  Content exists but phrasing differs — either rephrase, or lower")
        print("  min_similarity via the planner's retrieval_strategy.")
    if not kw:
        print("• Keyword leg returned nothing even after OR-fallback → wording truly absent.")
    if vec and kw:
        print("• Both legs have candidates → if full pipeline still fails, check reranker.")


if __name__ == "__main__":
    asyncio.run(main())
