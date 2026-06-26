"""
ai-service/app/services/rag_service.py

Retrieval-Augmented Generation storage & search layer.

Storage strategy (controlled by USE_QDRANT feature flag):
  Qdrant path  (USE_QDRANT=true, default):
    - Embeddings live in Qdrant; chunk_text + metadata in AI PostgreSQL.
    - Search: Qdrant ANN -> payload contains all fields needed for response
      (no secondary PG round-trip on the hot path).
    - Write: INSERT into PG -> get chunk_id -> upsert vector+payload to Qdrant.

  Legacy pgvector path  (USE_QDRANT=false):
    - Embeddings stored in document_chunks.embedding (VECTOR column).
    - Kept for safe rollback; can be removed once Qdrant is stable.

The public API (`search`, `store_chunk`, `delete_chunks_for_content`, etc.)
is identical regardless of which backend is active.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.database import get_ai_conn

logger   = logging.getLogger(__name__)
settings = get_settings()


def _sanitize(text: str) -> str:
    import re
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    chunk_id: int
    chunk_text: str
    similarity: float
    source_type: str
    page_number: int | None
    start_time_sec: int | None
    end_time_sec: int | None
    content_id: int | None
    node_id: int | None
    language: str


# ── Column helpers (pgvector legacy path) ─────────────────────────────────────

_IS_BGE     = "bge" in settings.embedding_model.lower()
_SEARCH_COL = "embedding"
_SEARCH_OP  = f"{_SEARCH_COL} <=> $1::vector"


# ── RAG Service ───────────────────────────────────────────────────────────────

class RAGService:

    # ── Storage ───────────────────────────────────────────────────────────────

    async def store_chunk(
        self,
        content_id: int,
        course_id: int,
        chunk_text: str,
        chunk_index: int,
        node_id: int | None = None,
        source_type: str = "document",
        page_number: int | None = None,
        start_time_sec: int | None = None,
        end_time_sec: int | None = None,
        language: str = "vi",
    ) -> int:
        from app.core.embeddings import create_passage_embedding
        chunk_text = _sanitize(chunk_text)
        chunk_hash = hashlib.sha256(
            f"{content_id}:{chunk_index}:{chunk_text}".encode()
        ).hexdigest()
        embedding = await create_passage_embedding(chunk_text)

        if settings.use_qdrant:
            chunk_id = await self._insert_chunk_pg(
                content_id=content_id, course_id=course_id, node_id=node_id,
                chunk_text=chunk_text, chunk_index=chunk_index,
                chunk_hash=chunk_hash, source_type=source_type,
                page_number=page_number, start_time_sec=start_time_sec,
                end_time_sec=end_time_sec, language=language,
            )
            from app.services.qdrant_service import qdrant_service
            await qdrant_service.upsert_chunk(
                chunk_id=chunk_id,
                embedding=embedding,
                payload=self._build_chunk_payload(
                    chunk_text=chunk_text, chunk_index=chunk_index,
                    chunk_hash=chunk_hash, content_id=content_id,
                    course_id=course_id, node_id=node_id,
                    source_type=source_type, page_number=page_number,
                    start_time_sec=start_time_sec, end_time_sec=end_time_sec,
                    language=language,
                ),
            )
            return chunk_id

        # ── Legacy pgvector path ──────────────────────────────────────────────
        emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO document_chunks
                    (content_id, course_id, node_id, chunk_text, chunk_index,
                     chunk_hash, {_SEARCH_COL}, source_type, page_number,
                     start_time_sec, end_time_sec, language, status, embedding_model)
                VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,$9,$10,$11,$12,'ready',$13)
                ON CONFLICT (chunk_hash) DO UPDATE
                    SET {_SEARCH_COL}    = EXCLUDED.{_SEARCH_COL},
                        embedding_model  = EXCLUDED.embedding_model,
                        status           = 'ready'
                RETURNING id
                """,
                content_id, course_id, node_id, chunk_text, chunk_index,
                chunk_hash, emb_str, source_type, page_number,
                start_time_sec, end_time_sec, language,
                settings.embedding_model,
            )
        return row["id"]

    async def store_chunks_batch(
        self,
        content_id: int,
        course_id: int,
        chunks: list[dict],
        node_id: int | None = None,
    ) -> list[int]:
        from app.core.embeddings import create_passage_embeddings_batch

        if not chunks:
            return []

        for c in chunks:
            c["text"] = _sanitize(c["text"])

        texts = [c["text"] for c in chunks]
        EMBED_BATCH = 32
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = await create_passage_embeddings_batch(texts[i: i + EMBED_BATCH])
            embeddings.extend(batch)

        hashes: list[str] = []
        for chunk in chunks:
            h = hashlib.sha256(
                f"{content_id}:{chunk['index']}:{chunk['text']}".encode()
            ).hexdigest()
            hashes.append(h)

        if settings.use_qdrant:
            return await self._store_batch_qdrant(
                content_id=content_id, course_id=course_id, node_id=node_id,
                chunks=chunks, embeddings=embeddings, hashes=hashes,
            )

        # ── Legacy pgvector path ──────────────────────────────────────────────
        return await self._store_batch_pgvector(
            content_id=content_id, course_id=course_id, node_id=node_id,
            chunks=chunks, embeddings=embeddings, hashes=hashes,
        )

    async def _store_batch_qdrant(
        self,
        content_id: int,
        course_id: int,
        node_id: int | None,
        chunks: list[dict],
        embeddings: list[list[float]],
        hashes: list[str],
    ) -> list[int]:
        from app.services.qdrant_service import qdrant_service

        # 1. Bulk insert metadata into PG -> get chunk IDs back
        chunk_ids = await self._bulk_insert_pg_no_embedding(
            content_id=content_id, course_id=course_id, node_id=node_id,
            chunks=chunks, hashes=hashes,
        )

        # 2. Build Qdrant points
        qdrant_points: list[dict] = []
        for chunk, emb, chunk_id, chunk_hash in zip(chunks, embeddings, chunk_ids, hashes):
            qdrant_points.append({
                "id":     chunk_id,
                "vector": emb,
                "payload": self._build_chunk_payload(
                    chunk_text=chunk["text"],
                    chunk_index=chunk["index"],
                    chunk_hash=chunk_hash,
                    content_id=content_id,
                    course_id=course_id,
                    node_id=node_id,
                    source_type=chunk.get("source_type", "document"),
                    page_number=chunk.get("page_number"),
                    start_time_sec=chunk.get("start_time_sec"),
                    end_time_sec=chunk.get("end_time_sec"),
                    language=chunk.get("language", "vi"),
                ),
            })

        await qdrant_service.upsert_chunks_batch(qdrant_points)
        return chunk_ids

    async def _bulk_insert_pg_no_embedding(
        self,
        content_id: int,
        course_id: int,
        node_id: int | None,
        chunks: list[dict],
        hashes: list[str],
    ) -> list[int]:
        """
        Insert chunk metadata into PostgreSQL WITHOUT the embedding column.
        Returns list of chunk IDs in the same order as input chunks.
        """
        sql = """
            INSERT INTO document_chunks
                (content_id, course_id, node_id, chunk_text, chunk_index,
                 chunk_hash, source_type, page_number,
                 start_time_sec, end_time_sec, language, status, embedding_model)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'ready',$12)
            ON CONFLICT (chunk_hash) DO UPDATE
                SET node_id        = EXCLUDED.node_id,
                    status         = 'ready',
                    embedding_model = EXCLUDED.embedding_model
            RETURNING id, chunk_hash
        """
        records = [
            (
                content_id, course_id, node_id,
                chunk["text"], chunk["index"], h,
                chunk.get("source_type", "document"),
                chunk.get("page_number"),
                chunk.get("start_time_sec"),
                chunk.get("end_time_sec"),
                chunk.get("language", "vi"),
                settings.embedding_model,
            )
            for chunk, h in zip(chunks, hashes)
        ]

        async with get_ai_conn() as conn:
            async with conn.transaction():
                await conn.executemany(sql, records)
            # Fetch IDs in insertion order using hashes
            rows = await conn.fetch(
                "SELECT id, chunk_hash FROM document_chunks WHERE chunk_hash = ANY($1)", hashes
            )

        hash_to_id = {r["chunk_hash"]: r["id"] for r in rows}
        return [hash_to_id[h] for h in hashes if h in hash_to_id]

    async def _store_batch_pgvector(
        self,
        content_id: int,
        course_id: int,
        node_id: int | None,
        chunks: list[dict],
        embeddings: list[list[float]],
        hashes: list[str],
    ) -> list[int]:
        sql = f"""
            INSERT INTO document_chunks
                (content_id, course_id, node_id, chunk_text, chunk_index,
                 chunk_hash, {_SEARCH_COL}, source_type, page_number,
                 start_time_sec, end_time_sec, language, status, embedding_model)
            VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,$9,$10,$11,$12,'ready',$13)
            ON CONFLICT (chunk_hash) DO UPDATE
                SET {_SEARCH_COL}   = EXCLUDED.{_SEARCH_COL},
                    embedding_model = EXCLUDED.embedding_model,
                    status          = 'ready'
        """
        records = [
            (
                content_id, course_id, node_id,
                chunk["text"], chunk["index"], h,
                "[" + ",".join(str(v) for v in emb) + "]",
                chunk.get("source_type", "document"),
                chunk.get("page_number"),
                chunk.get("start_time_sec"),
                chunk.get("end_time_sec"),
                chunk.get("language", "vi"),
                settings.embedding_model,
            )
            for chunk, emb, h in zip(chunks, embeddings, hashes)
        ]

        async with get_ai_conn() as conn:
            async with conn.transaction():
                await conn.executemany(sql, records)
            rows = await conn.fetch(
                "SELECT id FROM document_chunks WHERE chunk_hash = ANY($1)", hashes
            )
        return [r["id"] for r in rows]

    # ── Single chunk PG insert (used by store_chunk) ──────────────────────────

    async def _insert_chunk_pg(
        self, *, content_id, course_id, node_id, chunk_text,
        chunk_index, chunk_hash, source_type, page_number,
        start_time_sec, end_time_sec, language,
    ) -> int:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO document_chunks
                    (content_id, course_id, node_id, chunk_text, chunk_index,
                     chunk_hash, source_type, page_number,
                     start_time_sec, end_time_sec, language, status, embedding_model)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'ready',$12)
                ON CONFLICT (chunk_hash) DO UPDATE
                    SET node_id         = EXCLUDED.node_id,
                        status          = 'ready',
                        embedding_model = EXCLUDED.embedding_model
                RETURNING id
                """,
                content_id, course_id, node_id, chunk_text, chunk_index,
                chunk_hash, source_type, page_number,
                start_time_sec, end_time_sec, language,
                settings.embedding_model,
            )
        return row["id"]

    # ── Payload builder ────────────────────────────────────────────────────────

    @staticmethod
    def _build_chunk_payload(
        *,
        chunk_text: str,
        chunk_index: int,
        chunk_hash: str,
        content_id: int | None,
        course_id: int,
        node_id: int | None,
        source_type: str,
        page_number: int | None,
        start_time_sec: int | None,
        end_time_sec: int | None,
        language: str,
    ) -> dict:
        payload = {
            "chunk_text":   chunk_text,
            "chunk_index":  chunk_index,
            "chunk_hash":   chunk_hash,
            "course_id":    course_id,
            "source_type":  source_type,
            "language":     language,
            "status":       "ready",
        }
        if content_id is not None:
            payload["content_id"] = content_id
        if node_id is not None:
            payload["node_id"] = node_id
        if page_number is not None:
            payload["page_number"] = page_number
        if start_time_sec is not None:
            payload["start_time_sec"] = start_time_sec
        if end_time_sec is not None:
            payload["end_time_sec"] = end_time_sec
        return payload

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        course_id: int | None = None,
        node_id: int | None = None,
        content_id: int | None = None,
        top_k: int | None = None,
        min_similarity: float = 0.30,
    ) -> list[RetrievedChunk]:
        from app.core.embeddings import create_embedding
        top_k        = top_k or settings.top_k_chunks
        fetch_k      = settings.rerank_fetch_k if settings.use_reranker else top_k
        query_vector = await create_embedding(query)

        if settings.use_qdrant:
            from app.services.qdrant_service import qdrant_service
            scored = await qdrant_service.search_chunks(
                query_vector=query_vector,
                course_id=course_id,
                node_id=node_id,
                content_id=content_id,
                top_k=fetch_k,
                score_threshold=min_similarity,
            )
            return [self._scored_point_to_chunk(p) for p in scored]

        # ── Legacy pgvector ───────────────────────────────────────────────────
        return await self._pgvector_search(
            query_vector=query_vector,
            course_id=course_id, node_id=node_id, content_id=content_id,
            top_k=fetch_k, min_similarity=min_similarity,
        )

    @staticmethod
    def _scored_point_to_chunk(point) -> RetrievedChunk:
        p = point.payload or {}
        return RetrievedChunk(
            chunk_id=int(point.id),
            chunk_text=p.get("chunk_text", ""),
            similarity=float(point.score),
            source_type=p.get("source_type", "document"),
            page_number=p.get("page_number"),
            start_time_sec=p.get("start_time_sec"),
            end_time_sec=p.get("end_time_sec"),
            content_id=p.get("content_id"),
            node_id=p.get("node_id"),
            language=p.get("language", "vi"),
        )

    async def _pgvector_search(
        self,
        query_vector: list[float],
        course_id: int | None,
        node_id: int | None,
        content_id: int | None,
        top_k: int,
        min_similarity: float,
    ) -> list[RetrievedChunk]:
        emb_str    = "[" + ",".join(str(v) for v in query_vector) + "]"
        conditions = [f"status = 'ready'", f"{_SEARCH_COL} IS NOT NULL"]
        params: list = [emb_str, top_k]
        idx = 3

        if course_id is not None:
            conditions.append(f"course_id = ${idx}"); params.append(course_id); idx += 1
        if node_id is not None:
            conditions.append(f"node_id = ${idx}"); params.append(node_id); idx += 1
        if content_id is not None:
            conditions.append(f"content_id = ${idx}"); params.append(content_id); idx += 1

        where = " AND ".join(conditions)
        sql = f"""
            SELECT id, chunk_text, content_id, node_id,
                   source_type, page_number, start_time_sec, end_time_sec, language,
                   1 - ({_SEARCH_OP}) AS similarity
            FROM document_chunks
            WHERE {where}
              AND 1 - ({_SEARCH_OP}) >= {min_similarity}
            ORDER BY {_SEARCH_COL} <=> $1::vector
            LIMIT $2
        """
        async with get_ai_conn() as conn:
            rows = await conn.fetch(sql, *params)

        return [
            RetrievedChunk(
                chunk_id=r["id"], chunk_text=r["chunk_text"],
                similarity=float(r["similarity"]),
                source_type=r["source_type"], page_number=r["page_number"],
                start_time_sec=r["start_time_sec"], end_time_sec=r["end_time_sec"],
                content_id=r["content_id"], node_id=r["node_id"],
                language=r["language"],
            )
            for r in rows
        ]

    async def _search_and_rerank(
        self, query: str, top_k: int, **kw
    ) -> list[RetrievedChunk]:
        candidates = await self.search(query=query, **kw)
        if not candidates or not settings.use_reranker:
            return candidates[:top_k]
        from app.core.embeddings import rerank_chunks
        return await rerank_chunks(
            query=query, chunks=candidates,
            text_fn=lambda c: c.chunk_text, top_k=top_k,
        )

    async def search_multilingual(
        self,
        query: str,
        course_id: int | None = None,
        node_id: int | None = None,
        content_id: int | None = None,
        top_k: int | None = None,
        min_similarity: float = 0.25,
    ) -> list[RetrievedChunk]:
        from app.core.multilingual import multilingual_search
        top_k = top_k or settings.top_k_chunks
        candidates = await multilingual_search(
            search_fn=self.search,
            query=query,
            top_k=top_k if not settings.use_reranker else settings.rerank_fetch_k,
            id_fn=lambda c: c.chunk_id,
            min_similarity=min_similarity,
            course_id=course_id, node_id=node_id, content_id=content_id,
        )
        # Determine final ranked chunks
        if not candidates or not settings.use_reranker:
            final_chunks = candidates[:top_k]
        else:
            from app.core.embeddings import rerank_chunks
            final_chunks = await rerank_chunks(
                query=query, chunks=candidates,
                text_fn=lambda c: c.chunk_text, top_k=top_k,
            )

        # 1. Hydrate parent passages if hierarchical chunking is active
        if final_chunks and settings.use_hierarchical_chunks:
            try:
                final_chunks = await self.hydrate_parents(final_chunks)
            except Exception as exc:
                logger.warning("Parent hydration failed in search_multilingual: %s", exc)

        # 2. Enrich with Knowledge Graph context (prerequisites and related nodes)
        if final_chunks:
            try:
                final_chunks = await self.enrich_chunks_with_graph_context(final_chunks)
            except Exception as exc:
                logger.warning("Graph context enrichment failed in search_multilingual: %s", exc)

        return final_chunks

    async def search_for_question(
        self,
        question_text: str,
        course_id: int,
        node_id: int | None = None,
        reference_chunk_id: int | None = None,
        top_k: int = 3,
    ) -> list[RetrievedChunk]:
        """Search for chunks relevant to a quiz question.

        All question data is passed as parameters (no LMS DB access).
        """
        if not question_text:
            return []

        pinned: list[RetrievedChunk] = []
        if reference_chunk_id:
            pinned_chunk = await self.get_chunk(reference_chunk_id)
            if pinned_chunk:
                pinned = [RetrievedChunk(
                    chunk_id=pinned_chunk["id"],
                    chunk_text=pinned_chunk["chunk_text"],
                    similarity=1.0,
                    source_type=pinned_chunk["source_type"],
                    page_number=pinned_chunk["page_number"],
                    start_time_sec=pinned_chunk["start_time_sec"],
                    end_time_sec=pinned_chunk["end_time_sec"],
                    content_id=pinned_chunk["content_id"],
                    node_id=pinned_chunk["node_id"],
                    language=pinned_chunk["language"],
                )]

        semantic = await self.search_multilingual(
            query=question_text,
            course_id=course_id,
            node_id=node_id,
            top_k=top_k,
        )

        seen   = {c.chunk_id for c in pinned}
        result = list(pinned)
        for chunk in semantic:
            if chunk.chunk_id not in seen:
                result.append(chunk)
                seen.add(chunk.chunk_id)

        return result[:top_k]

    # ── Hierarchical (parent + child) storage ─────────────────────────────────

    async def store_hierarchical_pairs(
        self,
        content_id: int,
        course_id: int,
        pairs: list,            # list[HierarchicalChunkPair] from chunker
        node_id: int | None = None,
    ) -> dict:
        """
        Insert parent + child rows for a hierarchical chunking run.

        Storage rules:
          * Parent rows (`chunk_level='parent'`) live in PG only - no
            embedding, never indexed in Qdrant. They exist purely so the
            search path can hydrate matched children with their full
            surrounding section.
          * Child rows (`chunk_level='child'`) embed and index as before;
            they carry `parent_chunk_id` pointing at the corresponding
            parent.
          * If a "parent" only has one child whose text equals the parent
            (i.e. single-chunk section), we skip the parent insert and
            store the child as a flat row with parent_chunk_id NULL.

        Returns {"parents_created": int, "children_created": int}.
        """
        if not pairs:
            return {"parents_created": 0, "children_created": 0}

        parents_created = 0
        children_created = 0
        flat_children_only: list[dict] = []
        per_parent_children: list[tuple[int, list[dict]]] = []

        # First pass: create parent rows (no embedding) and collect the
        # children that should reference them.
        async with get_ai_conn() as conn:
            for pair in pairs:
                parent_text = _sanitize(pair.parent_text)
                child_dicts = [self._chunk_to_dict(c) for c in pair.children]
                if not child_dicts:
                    continue

                # Skip parent insert if it would just duplicate the only child.
                if len(child_dicts) == 1 and child_dicts[0]["text"].strip() == parent_text.strip():
                    flat_children_only.append(child_dicts[0])
                    continue

                parent_hash = hashlib.sha256(
                    f"parent:{content_id}:{parent_text[:200]}:{len(parent_text)}".encode()
                ).hexdigest()

                row = await conn.fetchrow(
                    """
                    INSERT INTO document_chunks
                        (content_id, course_id, node_id, chunk_text, chunk_index,
                         chunk_hash, source_type, page_number,
                         start_time_sec, end_time_sec, language, status,
                         embedding_model, chunk_level, parent_chunk_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'ready',$12,'parent',NULL)
                    ON CONFLICT (chunk_hash) DO UPDATE
                        SET status = 'ready'
                    RETURNING id
                    """,
                    content_id, course_id, node_id, parent_text,
                    parents_created, parent_hash,
                    "document",
                    pair.parent_page_number,
                    pair.parent_start_time_sec, pair.parent_end_time_sec,
                    pair.parent_language,
                    settings.embedding_model,
                )
                parent_id = row["id"]
                parents_created += 1
                per_parent_children.append((parent_id, child_dicts))

        # Second pass: insert children + embed + push to Qdrant. Reuse
        # the existing batch path then patch the parent_chunk_id column.
        all_children: list[dict] = list(flat_children_only)
        parent_id_per_index: list[int | None] = [None] * len(all_children)
        for parent_id, kids in per_parent_children:
            for k in kids:
                all_children.append(k)
                parent_id_per_index.append(parent_id)

        if all_children:
            child_ids = await self.store_chunks_batch(
                content_id=content_id, course_id=course_id,
                chunks=all_children, node_id=node_id,
            )
            children_created = len(child_ids)

            # Apply parent links.
            updates = [
                (parent_id_per_index[i], child_id)
                for i, child_id in enumerate(child_ids)
                if i < len(parent_id_per_index) and parent_id_per_index[i] is not None
            ]
            if updates:
                async with get_ai_conn() as conn:
                    await conn.executemany(
                        "UPDATE document_chunks SET parent_chunk_id = $1 WHERE id = $2",
                        updates,
                    )

        logger.info(
            "Hierarchical store: content=%d parents=%d children=%d (flat=%d)",
            content_id, parents_created, children_created, len(flat_children_only),
        )
        return {"parents_created": parents_created, "children_created": children_created}

    @staticmethod
    def _chunk_to_dict(chunk) -> dict:
        return {
            "text":            chunk.text,
            "index":           chunk.index,
            "source_type":     chunk.source_type,
            "page_number":     chunk.page_number,
            "start_time_sec":  chunk.start_time_sec,
            "end_time_sec":    chunk.end_time_sec,
            "language":        chunk.language,
        }

    # ── Parent hydration helper for retrieval consumers ───────────────────────

    async def hydrate_parents(
        self,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """
        For each retrieved child chunk that has a parent, replace its
        chunk_text with the parent's chunk_text. Useful for LLM context
        windows where you want a wider, more coherent passage than the
        embedding-sized child.

        Pure metadata (page_number, etc.) is preserved from the child so
        deep-link / citation behaviour is unchanged.
        """
        if not chunks:
            return chunks

        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT child.id        AS child_id,
                       parent.chunk_text AS parent_text
                FROM document_chunks child
                JOIN document_chunks parent ON parent.id = child.parent_chunk_id
                WHERE child.id = ANY($1)
                """,
                [c.chunk_id for c in chunks],
            )
        parent_text_by_child = {r["child_id"]: r["parent_text"] for r in rows}
        if not parent_text_by_child:
            return chunks

        for c in chunks:
            pt = parent_text_by_child.get(c.chunk_id)
            if pt:
                c.chunk_text = pt
        return chunks

    async def enrich_chunks_with_graph_context(
        self,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """
        Enriches a list of retrieved chunks with their Knowledge Graph context
        (node description, prerequisites, and related nodes).
        This helps the LLM understand the conceptual relationships and context.
        """
        if not chunks:
            return chunks

        # Collect unique node_ids
        node_ids = list({c.node_id for c in chunks if c.node_id})
        if not node_ids:
            return chunks

        # Fetch node info and relationships
        node_info = {}
        prereqs = {}
        related = {}

        # 1. Fetch Node Info
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, name_vi, description
                FROM knowledge_nodes
                WHERE id = ANY($1)
                """,
                node_ids,
            )
            for r in rows:
                node_info[r["id"]] = {
                    "name": r["name_vi"] or r["name"],
                    "description": r["description"] or "",
                }

            # 2. Fetch Relationships (Prerequisites and Related)
            # source -> target (PREREQUISITE: source is prerequisite of target)
            rel_rows = await conn.fetch(
                """
                SELECT r.source_node_id, r.target_node_id, r.relation_type,
                       src.name AS src_name, src.name_vi AS src_name_vi,
                       tgt.name AS tgt_name, tgt.name_vi AS tgt_name_vi
                FROM knowledge_node_relations r
                JOIN knowledge_nodes src ON src.id = r.source_node_id
                JOIN knowledge_nodes tgt ON tgt.id = r.target_node_id
                WHERE r.source_node_id = ANY($1) OR r.target_node_id = ANY($1)
                """,
                node_ids,
            )

            for r in rel_rows:
                src_id, tgt_id = r["source_node_id"], r["target_node_id"]
                rel_type = r["relation_type"]
                src_name = r["src_name_vi"] or r["src_name"]
                tgt_name = r["tgt_name_vi"] or r["tgt_name"]

                # If current node is the target, then source is its prerequisite
                if rel_type == "PREREQUISITE":
                    if tgt_id in node_ids:
                        if tgt_id not in prereqs:
                            prereqs[tgt_id] = []
                        prereqs[tgt_id].append(src_name)
                else:
                    # Other relations are treated as related concepts
                    for nid, other_name in [(src_id, tgt_name), (tgt_id, src_name)]:
                        if nid in node_ids:
                            if nid not in related:
                                related[nid] = []
                            if other_name not in related[nid]:
                                related[nid].append(other_name)

        # 3. Append Graph Context to chunk texts
        for c in chunks:
            if not c.node_id or c.node_id not in node_info:
                continue

            info = node_info[c.node_id]
            node_name = info["name"]
            node_desc = info["description"]

            graph_lines = [f"\n\n[Ngữ cảnh Đồ thị Kiến thức (Khóa học):"]
            graph_lines.append(f" - Khái niệm: {node_name}")
            if node_desc:
                graph_lines.append(f"   Mô tả: {node_desc}")

            node_prereqs = prereqs.get(c.node_id)
            if node_prereqs:
                graph_lines.append(f" - Khái niệm tiên quyết cần học trước: {', '.join(node_prereqs)}")

            node_related = related.get(c.node_id)
            if node_related:
                graph_lines.append(f" - Khái niệm liên quan/mở rộng: {', '.join(node_related)}")

            graph_lines.append("]")
            
            # Enrich chunk text
            c.chunk_text += "\n" + "\n".join(graph_lines)

        return chunks

    # ── Deletion ──────────────────────────────────────────────────────────────

    async def delete_chunks_for_content(self, content_id: int) -> int:
        """Delete chunks from both Qdrant (vectors) and PG (metadata)."""
        if settings.use_qdrant:
            from app.services.qdrant_service import qdrant_service
            await qdrant_service.delete_chunks_by_content(content_id)

        async with get_ai_conn() as conn:
            result = await conn.execute(
                "DELETE FROM document_chunks WHERE content_id = $1", content_id
            )
        deleted = int(result.split()[-1])
        logger.info("Deleted %d chunks for content_id=%d", deleted, content_id)
        return deleted

    # ── Read helpers ──────────────────────────────────────────────────────────

    async def get_chunk(self, chunk_id: int) -> dict | None:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """SELECT id, chunk_text, content_id, node_id,
                          source_type, page_number, start_time_sec, end_time_sec, language
                   FROM document_chunks WHERE id = $1""",
                chunk_id,
            )
        return dict(row) if row else None


rag_service = RAGService()