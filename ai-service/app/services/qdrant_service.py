"""
ai-service/app/services/qdrant_service.py

Purpose-built vector store replacing pgvector for semantic search.

Design decisions:
  - Two collections: document_chunks (RAG) and knowledge_nodes (dedup/graph)
  - Point ID = PostgreSQL row ID -> no additional mapping table needed
  - Full payload stored in Qdrant -> search returns complete result without
    secondary PG round-trip (critical for sub-100ms p99 latency)
  - Payload indexes on course_id, content_id, node_id -> O(log n) filtering
  - HNSW m=16, ef_construct=128 matches current pgvector tuning
  - gRPC preferred when qdrant_prefer_grpc=True (significantly faster batches)
  - Feature flag USE_QDRANT=true enables safe cutover; false keeps pgvector path
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchAny,
    MatchValue,
    OptimizersConfigDiff,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Collection constants ───────────────────────────────────────────────────────

CHUNK_COLLECTION = "document_chunks"
NODE_COLLECTION  = "knowledge_nodes"
VECTOR_SIZE      = 1024          # bge-m3 output dimension
DISTANCE         = Distance.COSINE


class QdrantService:
    """
    Async Qdrant client wrapper.

    Lifecycle:
      - Call `init_collections()` once at application startup.
      - Use `close()` at shutdown.
      - All other methods are safe to call concurrently.
    """

    _client: AsyncQdrantClient | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            if settings.qdrant_url:
                # Cloud/Serverless mode
                self._client = AsyncQdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                    timeout=30,
                )
                logger.info("Qdrant connected via URL (Serverless mode)")
            else:
                # Local/Docker mode
                self._client = AsyncQdrantClient(
                    host=settings.qdrant_host,
                    port=settings.qdrant_grpc_port if settings.qdrant_prefer_grpc else settings.qdrant_port,
                    grpc_port=settings.qdrant_grpc_port,
                    prefer_grpc=settings.qdrant_prefer_grpc,
                    api_key=settings.qdrant_api_key or None,
                    timeout=30,
                )
                logger.info("Qdrant connected via host:port (Local mode)")
        return self._client

    async def init_collections(self) -> None:
        """Idempotent: create collections + payload indexes if they don't exist."""
        client = self._get_client()
        for name, index_fn in [
            (CHUNK_COLLECTION, self._create_chunk_indexes),
            (NODE_COLLECTION,  self._create_node_indexes),
        ]:
            exists = await client.collection_exists(name)
            if not exists:
                await client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=VECTOR_SIZE,
                        distance=DISTANCE,
                        # Vectors stored on disk; HNSW graph stays in RAM
                        on_disk=True,
                    ),
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=128,
                        # Below this threshold, brute-force search is used
                        # (fast for small collections at startup)
                        full_scan_threshold=10_000,
                        on_disk=False,
                    ),
                    optimizers_config=OptimizersConfigDiff(
                        # Don't build HNSW until we have enough vectors;
                        # avoids expensive rebuilds during initial bulk load.
                        indexing_threshold=20_000,
                    ),
                )
                await index_fn()
                logger.info("Created Qdrant collection: %s", name)
            else:
                logger.debug("Qdrant collection already exists: %s", name)

    async def _create_chunk_indexes(self) -> None:
        client = self._get_client()
        int_fields   = ["course_id", "content_id", "node_id", "page_number"]
        kw_fields    = ["status", "language", "source_type", "chunk_hash"]
        for f in int_fields:
            await client.create_payload_index(CHUNK_COLLECTION, f, PayloadSchemaType.INTEGER)
        for f in kw_fields:
            await client.create_payload_index(CHUNK_COLLECTION, f, PayloadSchemaType.KEYWORD)

    async def _create_node_indexes(self) -> None:
        client = self._get_client()
        await client.create_payload_index(NODE_COLLECTION, "course_id",      PayloadSchemaType.INTEGER)
        await client.create_payload_index(NODE_COLLECTION, "auto_generated",  PayloadSchemaType.BOOL)
        await client.create_payload_index(NODE_COLLECTION, "source_content_id", PayloadSchemaType.INTEGER)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    # ── Document Chunk Operations ──────────────────────────────────────────────

    async def upsert_chunk(
        self,
        chunk_id: int,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Upsert a single chunk. Prefer `upsert_chunks_batch` for bulk work."""
        client = self._get_client()
        await client.upsert(
            collection_name=CHUNK_COLLECTION,
            points=[PointStruct(id=chunk_id, vector=embedding, payload=payload)],
            wait=True,
        )

    async def upsert_chunks_batch(self, points: list[dict[str, Any]]) -> None:
        """
        Batch upsert chunks.

        Args:
            points: list of {"id": int, "vector": list[float], "payload": dict}
        """
        if not points:
            return
        client = self._get_client()
        structs = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        # Qdrant recommends batches ≤ 512 points for optimal throughput
        batch_size = 256
        for i in range(0, len(structs), batch_size):
            await client.upsert(
                collection_name=CHUNK_COLLECTION,
                points=structs[i : i + batch_size],
                wait=True,
            )
        logger.debug("Upserted %d chunks to Qdrant", len(points))

    async def search_chunks(
        self,
        query_vector: list[float],
        course_id: int | None = None,
        node_id: int | None = None,
        content_id: int | None = None,
        top_k: int = 10,
        score_threshold: float = 0.25,
        content_ids: list[int] | None = None,
    ) -> list[ScoredPoint]:
        """
        ANN search over document_chunks with optional payload filtering.

        Returns ScoredPoints whose `.payload` contains all metadata needed
        to build a `RetrievedChunk` - no secondary DB query required.
        """
        client = self._get_client()
        query_filter = self._build_chunk_filter(course_id, node_id, content_id, content_ids)
        return await client.search(
            collection_name=CHUNK_COLLECTION,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )

    def _build_chunk_filter(
        self,
        course_id: int | None,
        node_id: int | None,
        content_id: int | None,
        content_ids: list[int] | None = None,
    ) -> Filter | None:
        must: list[FieldCondition] = [
            FieldCondition(key="status", match=MatchValue(value="ready")),
        ]
        if course_id is not None:
            must.append(FieldCondition(key="course_id",  match=MatchValue(value=course_id)))
        if node_id is not None:
            must.append(FieldCondition(key="node_id",    match=MatchValue(value=node_id)))
        if content_id is not None:
            must.append(FieldCondition(key="content_id", match=MatchValue(value=content_id)))
        elif content_ids:
            must.append(FieldCondition(key="content_id", match=MatchAny(any=content_ids)))
        return Filter(must=must)

    async def delete_chunks_by_content(self, content_id: int) -> None:
        """Delete all chunk vectors for a content item (called before re-index)."""
        client = self._get_client()
        await client.delete(
            collection_name=CHUNK_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="content_id", match=MatchValue(value=content_id))]
            ),
            wait=True,
        )
        logger.debug("Deleted Qdrant chunks for content_id=%d", content_id)

    async def delete_chunk(self, chunk_id: int) -> None:
        client = self._get_client()
        await client.delete(
            collection_name=CHUNK_COLLECTION,
            points_selector=PointIdsList(points=[chunk_id]),
            wait=True,
        )

    async def count_chunks(
        self,
        course_id: int | None = None,
        content_id: int | None = None,
    ) -> int:
        client = self._get_client()
        must: list[FieldCondition] = []
        if course_id is not None:
            must.append(FieldCondition(key="course_id",  match=MatchValue(value=course_id)))
        if content_id is not None:
            must.append(FieldCondition(key="content_id", match=MatchValue(value=content_id)))
        result = await client.count(
            collection_name=CHUNK_COLLECTION,
            count_filter=Filter(must=must) if must else None,
            exact=True,
        )
        return result.count

    # ── Knowledge Node Operations ──────────────────────────────────────────────

    async def upsert_node(
        self,
        node_id: int,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        client = self._get_client()
        await client.upsert(
            collection_name=NODE_COLLECTION,
            points=[PointStruct(id=node_id, vector=embedding, payload=payload)],
            wait=True,
        )

    async def upsert_nodes_batch(self, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        client = self._get_client()
        structs = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        for i in range(0, len(structs), 256):
            await client.upsert(
                collection_name=NODE_COLLECTION,
                points=structs[i : i + 256],
                wait=True,
            )
        logger.debug("Upserted %d nodes to Qdrant", len(points))

    async def search_nodes(
        self,
        query_vector: list[float],
        course_id: int,
        top_k: int = 20,
        score_threshold: float = 0.60,
    ) -> list[ScoredPoint]:
        client = self._get_client()
        return await client.search(
            collection_name=NODE_COLLECTION,
            query_vector=query_vector,
            query_filter=Filter(
                must=[FieldCondition(key="course_id", match=MatchValue(value=course_id))]
            ),
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )

    async def search_nodes_batch(
        self,
        query_vectors: list[list[float]],
        exclude_course_id: int | None = None,
        top_k: int = 5,
        score_threshold: float = 0.70,
    ) -> list[list[ScoredPoint]]:
        """
        Perform high-performance batch search across all nodes.
        Used for global linking optimization.
        """
        client = self._get_client()
        from qdrant_client.http.models import SearchRequest

        query_filter = None
        if exclude_course_id is not None:
            query_filter = Filter(
                must_not=[FieldCondition(key="course_id", match=MatchValue(value=exclude_course_id))]
            )

        requests = [
            SearchRequest(
                vector=v,
                filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True,
            )
            for v in query_vectors
        ]
        
        return await client.search_batch(
            collection_name=NODE_COLLECTION,
            requests=requests,
        )

    async def scroll_nodes_for_course(self, course_id: int) -> list[Any]:
        """
        Fetch all node vectors for a course.
        Used by deduplication logic in auto_index_service.
        Returns list of Record objects (id, vector, payload).
        """
        client = self._get_client()
        all_points: list[Any] = []
        offset = None

        while True:
            records, next_offset = await client.scroll(
                collection_name=NODE_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="course_id", match=MatchValue(value=course_id))]
                ),
                limit=256,
                offset=offset,
                with_vectors=True,
                with_payload=True,
            )
            all_points.extend(records)
            if next_offset is None or not records:
                break
            offset = next_offset

        return all_points

    async def delete_node(self, node_id: int) -> None:
        client = self._get_client()
        await client.delete(
            collection_name=NODE_COLLECTION,
            points_selector=PointIdsList(points=[node_id]),
            wait=True,
        )

    async def update_node_payload(self, node_id: int, payload_patch: dict[str, Any]) -> None:
        """Patch specific payload fields without re-uploading the vector."""
        client = self._get_client()
        await client.set_payload(
            collection_name=NODE_COLLECTION,
            payload=payload_patch,
            points=PointIdsList(points=[node_id]),
            wait=True,
        )

    async def delete_by_course(self, course_id: int) -> None:
        """Delete all chunks and nodes belonging to a course from Qdrant."""
        client = self._get_client()
        # Delete document chunks for the course
        await client.delete(
            collection_name=CHUNK_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="course_id", match=MatchValue(value=course_id))]
            ),
            wait=True,
        )
        logger.debug("Deleted Qdrant chunks for course_id=%d", course_id)
        # Delete knowledge nodes for the course
        await client.delete(
            collection_name=NODE_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="course_id", match=MatchValue(value=course_id))]
            ),
            wait=True,
        )
        logger.debug("Deleted Qdrant nodes for course_id=%d", course_id)

    # ── Health / Diagnostics ───────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        client = self._get_client()
        try:
            info = await client.get_collections()
            chunk_count = await self.count_chunks()
            return {
                "status": "ok",
                "collections": [c.name for c in info.collections],
                "chunk_count": chunk_count,
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    async def collection_info(self, name: str) -> dict[str, Any]:
        client = self._get_client()
        info = await client.get_collection(name)
        return {
            "name":          name,
            "vectors_count": info.vectors_count,
            "points_count":  info.points_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status":        info.status.value,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
qdrant_service = QdrantService()