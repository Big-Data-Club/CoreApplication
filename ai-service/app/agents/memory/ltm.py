"""
ai-service/app/agents/memory/ltm.py

Long-Term Memory (LTM) — Qdrant + PostgreSQL episodic memory.

When a session is compressed (or explicitly ended), an "episode" summary
is created and stored:
  - Vector embedding in Qdrant (collection: agent_episodes)
  - Metadata row in PostgreSQL (agent_episodes table)

Later, the agent can semantically search past episodes to recall
relevant historical context about a user's learning journey.

Collection: agent_episodes
  - Dimensions: 1024 (bge-m3)
  - Distance: Cosine
  - Payload: {user_id, agent_type, session_id, summary, created_at}
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)
settings = get_settings()

EPISODE_COLLECTION = "agent_episodes"
EPISODE_VECTOR_SIZE = 1024  # bge-m3

FACTS_COLLECTION = "student_facts"
FACTS_VECTOR_SIZE = 1024  # bge-m3


class LTMemory:
    """Long-Term Memory using Qdrant + PostgreSQL."""

    # ── Qdrant collection lifecycle ────────────────────────────────────────────

    async def ensure_collection(self) -> None:
        """Create the agent_episodes Qdrant collection if it doesn't exist."""
        if not settings.use_qdrant:
            logger.info("LTM: Qdrant disabled, skipping collection init")
            return

        from app.services.qdrant_service import qdrant_service
        from qdrant_client.http.models import (
            Distance, VectorParams, HnswConfigDiff,
        )

        client = qdrant_service._get_client()
        exists = await client.collection_exists(EPISODE_COLLECTION)
        if not exists:
            await client.create_collection(
                collection_name=EPISODE_COLLECTION,
                vectors_config=VectorParams(
                    size=EPISODE_VECTOR_SIZE,
                    distance=Distance.COSINE,
                    on_disk=True,
                ),
                hnsw_config=HnswConfigDiff(
                    m=16,
                    ef_construct=100,
                    full_scan_threshold=5_000,
                    on_disk=False,
                ),
            )
            # Create payload indexes for filtering
            from qdrant_client.http.models import PayloadSchemaType
            await client.create_payload_index(
                EPISODE_COLLECTION, "user_id", PayloadSchemaType.INTEGER,
            )
            await client.create_payload_index(
                EPISODE_COLLECTION, "agent_type", PayloadSchemaType.KEYWORD,
            )
            await client.create_payload_index(
                EPISODE_COLLECTION, "course_id", PayloadSchemaType.INTEGER,
            )
            logger.info("Created Qdrant collection: %s", EPISODE_COLLECTION)
        else:
            # Best-effort: ensure the course_id payload index exists for
            # collections created before V006. Idempotent on most servers.
            try:
                from qdrant_client.http.models import PayloadSchemaType
                await client.create_payload_index(
                    EPISODE_COLLECTION, "course_id", PayloadSchemaType.INTEGER,
                )
            except Exception:  # noqa: BLE001 — index may already exist
                pass
            logger.debug("Qdrant collection already exists: %s", EPISODE_COLLECTION)

    async def ensure_facts_collection(self) -> None:
        """Create the student_facts Qdrant collection if it doesn't exist."""
        if not settings.use_qdrant:
            return

        from app.services.qdrant_service import qdrant_service
        from qdrant_client.http.models import Distance, VectorParams, HnswConfigDiff, PayloadSchemaType

        client = qdrant_service._get_client()
        exists = await client.collection_exists(FACTS_COLLECTION)
        if not exists:
            await client.create_collection(
                collection_name=FACTS_COLLECTION,
                vectors_config=VectorParams(
                    size=FACTS_VECTOR_SIZE,
                    distance=Distance.COSINE,
                    on_disk=True,
                ),
                hnsw_config=HnswConfigDiff(
                    m=16,
                    ef_construct=100,
                    full_scan_threshold=5_000,
                    on_disk=False,
                ),
            )
            await client.create_payload_index(
                FACTS_COLLECTION, "user_id", PayloadSchemaType.INTEGER,
            )
            await client.create_payload_index(
                FACTS_COLLECTION, "category", PayloadSchemaType.KEYWORD,
            )
            await client.create_payload_index(
                FACTS_COLLECTION, "course_id", PayloadSchemaType.INTEGER,
            )
            logger.info("Created Qdrant collection: %s", FACTS_COLLECTION)
        else:
            logger.debug("Qdrant collection already exists: %s", FACTS_COLLECTION)

    # ── Store episode ─────────────────────────────────────────────────────────

    async def store_episode(
        self,
        session_id: str,
        user_id: int,
        agent_type: str,
        summary_text: str,
        course_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Create a new episodic memory entry.

        1. Embed the summary text
        2. Upsert to Qdrant (payload includes optional course_id)
        3. Save metadata to PostgreSQL

        `course_id` is the dominant course of the session (e.g. the most
        recent CURRENT ANCHOR at compression time). It is OPTIONAL — pass
        None for cross-course episodes. Stored both in the Qdrant payload
        and the PG row so recall can filter or union by course.

        Returns the episode UUID, or None if storage failed.
        """
        if not summary_text.strip():
            return None

        try:
            from app.core.embeddings import create_passage_embedding

            # 1. Create embedding
            embedding = await create_passage_embedding(summary_text)

            # 2. Generate a positive int64 point ID for Qdrant
            point_id = uuid.uuid4().int >> 64  # positive int64

            # 3. Upsert to Qdrant
            if settings.use_qdrant:
                from app.services.qdrant_service import qdrant_service
                from qdrant_client.http.models import PointStruct

                client = qdrant_service._get_client()
                payload: dict = {
                    "user_id": user_id,
                    "agent_type": agent_type,
                    "session_id": session_id,
                    "summary": summary_text,
                    "created_at": int(time.time()),
                }
                if course_id is not None:
                    payload["course_id"] = course_id
                await client.upsert(
                    collection_name=EPISODE_COLLECTION,
                    points=[PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload,
                    )],
                    wait=True,
                )

            # 4. Save metadata to PostgreSQL
            async with get_ai_conn() as conn:
                row = await conn.fetchrow(
                    """INSERT INTO agent_episodes
                           (session_id, user_id, agent_type, summary,
                            course_id, qdrant_point_id)
                       VALUES ($1, $2, $3, $4, $5, $6)
                       RETURNING id""",
                    session_id, user_id, agent_type, summary_text,
                    course_id, point_id,
                )

            episode_id = str(row["id"]) if row else None
            logger.info(
                "LTM episode stored: user=%d agent=%s course=%s episode=%s point=%d",
                user_id, agent_type, course_id, episode_id, point_id,
            )
            return episode_id

        except Exception as exc:
            logger.error("Failed to store LTM episode: %s", exc)
            return None

    # ── Recall episodes ───────────────────────────────────────────────────────

    async def recall(
        self,
        user_id: int,
        agent_type: str,
        query: str,
        top_k: int = 3,
        min_score: float = 0.40,
        course_ids: Optional[list[int]] = None,
    ) -> list[dict]:
        """
        Semantically search past episodes for this user.

        Args:
            course_ids: Optional course filter. When supplied, recall is
                restricted to episodes tagged with one of these course_ids
                PLUS episodes with no course tag (cross-course episodes
                are always relevant). When None, all episodes are eligible.

        Returns a list of episode summaries sorted by relevance.
        """
        if not settings.use_qdrant:
            # Fallback: return recent episodes from PostgreSQL
            return await self._recall_from_pg(
                user_id, agent_type, top_k, course_ids=course_ids,
            )

        try:
            from app.core.embeddings import create_embedding
            from app.services.qdrant_service import qdrant_service
            from qdrant_client.http.models import (
                Filter, FieldCondition, MatchValue, MatchAny, IsNullCondition,
                PayloadField,
            )

            query_vector = await create_embedding(query)
            client = qdrant_service._get_client()

            must = [
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                ),
                FieldCondition(
                    key="agent_type",
                    match=MatchValue(value=agent_type),
                ),
            ]

            qfilter: Filter
            if course_ids:
                # Match (course_id IN [...] OR course_id is missing).
                qfilter = Filter(
                    must=must,
                    should=[
                        FieldCondition(
                            key="course_id",
                            match=MatchAny(any=list(course_ids)),
                        ),
                        IsNullCondition(
                            is_null=PayloadField(key="course_id"),
                        ),
                    ],
                )
            else:
                qfilter = Filter(must=must)

            results = await client.search(
                collection_name=EPISODE_COLLECTION,
                query_vector=query_vector,
                query_filter=qfilter,
                limit=top_k,
                score_threshold=min_score,
                with_payload=True,
                with_vectors=False,
            )

            return [
                {
                    "summary": r.payload.get("summary", ""),
                    "session_id": r.payload.get("session_id", ""),
                    "course_id": r.payload.get("course_id"),
                    "created_at": r.payload.get("created_at", 0),
                }
                for r in results
            ]


        except Exception as exc:
            logger.error("LTM recall failed: %s", exc)
            return await self._recall_from_pg(
                user_id, agent_type, top_k, course_ids=course_ids,
            )

    async def _recall_from_pg(
        self,
        user_id: int,
        agent_type: str,
        limit: int = 3,
        course_ids: Optional[list[int]] = None,
    ) -> list[dict]:
        """Fallback: return the most recent episodes from PostgreSQL."""
        try:
            async with get_ai_conn() as conn:
                if course_ids:
                    rows = await conn.fetch(
                        """SELECT summary, session_id::TEXT, course_id, created_at
                           FROM agent_episodes
                           WHERE user_id = $1 AND agent_type = $2
                             AND (course_id IS NULL OR course_id = ANY($3::BIGINT[]))
                           ORDER BY created_at DESC
                           LIMIT $4""",
                        user_id, agent_type, list(course_ids), limit,
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT summary, session_id::TEXT, course_id, created_at
                           FROM agent_episodes
                           WHERE user_id = $1 AND agent_type = $2
                           ORDER BY created_at DESC
                           LIMIT $3""",
                        user_id, agent_type, limit,
                    )
            return [
                {
                    "summary": r["summary"],
                    "session_id": r["session_id"],
                    "course_id": r["course_id"],
                    "score": 1.0,  # no relevance score from PG
                    "created_at": r["created_at"].isoformat()
                        if r["created_at"] else "",
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("LTM PG fallback failed: %s", exc)
            return []



    # ── Student Facts (Unified Agentic Memory) ────────────────────────────────

    async def save_fact(
        self,
        user_id: int,
        fact: str,
        category: str,
        course_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Save a long-term fact about a student (Postgres-first, dual-write).
        Returns the Postgres row ID if successful.
        """
        if not fact.strip():
            return None

        # 1. Postgres First
        try:
            async with get_ai_conn() as conn:
                row = await conn.fetchrow(
                    """INSERT INTO student_facts
                           (user_id, fact, category, course_id, qdrant_synced)
                       VALUES ($1, $2, $3, $4, FALSE)
                       RETURNING id""",
                    user_id, fact.strip(), category, course_id,
                )
            fact_id = row["id"] if row else None
            if not fact_id:
                return None
        except Exception as exc:
            logger.error("LTM save_fact PG insert failed: %s", exc)
            return None

        # 2. Embed and Upsert to Qdrant
        qdrant_point_id = None
        try:
            from app.core.embeddings import create_passage_embedding
            embedding = await create_passage_embedding(fact)
            
            qdrant_point_id = uuid.uuid4().int >> 64
            
            if settings.use_qdrant:
                from app.services.qdrant_service import qdrant_service
                from qdrant_client.http.models import PointStruct

                client = qdrant_service._get_client()
                payload = {
                    "user_id": user_id,
                    "category": category,
                    "fact": fact,
                    "created_at": int(time.time()),
                }
                if course_id is not None:
                    payload["course_id"] = course_id

                await client.upsert(
                    collection_name=FACTS_COLLECTION,
                    points=[PointStruct(
                        id=qdrant_point_id,
                        vector=embedding,
                        payload=payload,
                    )],
                    wait=True,
                )
        except Exception as exc:
            logger.warning("LTM save_fact Qdrant upsert failed (will be synced later): %s", exc)

        # 3. Mark as synced if Qdrant was successful
        if qdrant_point_id is not None and settings.use_qdrant:
            try:
                async with get_ai_conn() as conn:
                    await conn.execute(
                        """UPDATE student_facts
                           SET qdrant_point_id = $1, qdrant_synced = TRUE
                           WHERE id = $2""",
                        qdrant_point_id, fact_id,
                    )
            except Exception as exc:
                logger.error("LTM save_fact PG sync-update failed: %s", exc)
                
        logger.info("LTM fact stored: user=%d category=%s course=%s id=%d point=%s", 
                    user_id, category, course_id, fact_id, qdrant_point_id)
        return fact_id

    async def search_facts(
        self,
        user_id: int,
        query: str,
        top_k: int = 3,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        Semantically search past facts for a user.
        """
        if not settings.use_qdrant:
            return await self._search_facts_from_pg(user_id, top_k, category)

        try:
            from app.core.embeddings import create_embedding
            from app.services.qdrant_service import qdrant_service
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue

            query_vector = await create_embedding(query)
            client = qdrant_service._get_client()

            must = [
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                )
            ]
            
            if category:
                must.append(
                    FieldCondition(
                        key="category",
                        match=MatchValue(value=category),
                    )
                )

            qfilter = Filter(must=must)

            results = await client.search(
                collection_name=FACTS_COLLECTION,
                query_vector=query_vector,
                query_filter=qfilter,
                limit=top_k,
                score_threshold=0.35,
                with_payload=True,
                with_vectors=False,
            )

            return [
                {
                    "fact": r.payload.get("fact", ""),
                    "category": r.payload.get("category", ""),
                    "course_id": r.payload.get("course_id"),
                    "created_at": r.payload.get("created_at", 0),
                    "score": round(r.score, 3),
                }
                for r in results
            ]

        except Exception as exc:
            logger.error("LTM search_facts failed: %s", exc)
            return await self._search_facts_from_pg(user_id, top_k, category)

    async def _search_facts_from_pg(
        self,
        user_id: int,
        limit: int = 3,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Fallback for facts search using PostgreSQL (most recent)."""
        try:
            async with get_ai_conn() as conn:
                if category:
                    rows = await conn.fetch(
                        """SELECT fact, category, course_id, created_at
                           FROM student_facts
                           WHERE user_id = $1 AND category = $2
                           ORDER BY created_at DESC
                           LIMIT $3""",
                        user_id, category, limit,
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT fact, category, course_id, created_at
                           FROM student_facts
                           WHERE user_id = $1
                           ORDER BY created_at DESC
                           LIMIT $2""",
                        user_id, limit,
                    )
            return [
                {
                    "fact": r["fact"],
                    "category": r["category"],
                    "course_id": r["course_id"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    "score": 1.0,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("LTM facts PG fallback failed: %s", exc)
            return []

# Singleton
ltm = LTMemory()
