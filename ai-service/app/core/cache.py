"""
ai-service/app/core/cache.py

Centralised Redis cache for the AI service.
Three named caches, each with its own TTL and key prefix:

  EmbeddingCache   - stores computed embedding vectors
                     key: emb:{model_prefix}:{sha256(text)[:16]}
                     TTL: 7 days (embeddings are deterministic)

  DiagnosisCache   - stores LLM diagnosis results per (question, wrong_answer)
                     key: diag:{question_id}:{md5(wrong_answer)[:8]}
                     TTL: 24 hours

  GraphCache       - stores full knowledge graph per course
                     key: graph:course:{course_id}
                     TTL: 5 minutes (invalidated on new node insert)

Usage:
    from app.core.cache import embedding_cache, diagnosis_cache, graph_cache

    # Embedding
    vec = await embedding_cache.get(text)
    if vec is None:
        vec = compute(text)
        await embedding_cache.set(text, vec)

    # Diagnosis
    result = await diagnosis_cache.get(question_id, wrong_answer)
    if result is None:
        result = await run_llm(...)
        await diagnosis_cache.set(question_id, wrong_answer, result)

    # Graph
    graph = await graph_cache.get(course_id)
    if graph is None:
        graph = await fetch_graph(course_id)
        await graph_cache.set(course_id, graph)

    # Invalidate graph when new nodes are added
    await graph_cache.invalidate(course_id)
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# TTLs in seconds
_TTL_EMBEDDING  = 7 * 24 * 3600   # 7 days
_TTL_DIAGNOSIS  = 24 * 3600        # 24 hours
_TTL_GRAPH      = 5 * 60           # 5 minutes

_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
    return _redis_client


async def close_cache() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# ── Embedding cache ───────────────────────────────────────────────────────────

class EmbeddingCache:
    """
    Cache computed embedding vectors.
    Embeddings are deterministic for a given text + model, so TTL can be long.
    """

    def _key(self, text: str) -> str:
        model_prefix = settings.embedding_model.split("/")[-1].lower()[:8]
        text_hash    = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"emb:{model_prefix}:{text_hash}"

    async def get(self, text: str) -> Optional[list[float]]:
        try:
            raw = await _get_redis().get(self._key(text))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Embedding cache GET failed: %s", exc)
            return None

    async def set(self, text: str, vector: list[float]) -> None:
        try:
            await _get_redis().setex(
                self._key(text), _TTL_EMBEDDING, json.dumps(vector)
            )
        except Exception as exc:
            logger.debug("Embedding cache SET failed: %s", exc)

    async def get_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        if not texts:
            return []
        try:
            keys = [self._key(t) for t in texts]
            raws = await _get_redis().mget(keys)
            return [json.loads(r) if r else None for r in raws]
        except Exception as exc:
            logger.debug("Embedding cache MGET failed: %s", exc)
            return [None] * len(texts)

    async def set_batch(self, texts: list[str], vectors: list[list[float]]) -> None:
        if not texts:
            return
        try:
            pipe = _get_redis().pipeline()
            for text, vec in zip(texts, vectors):
                pipe.setex(self._key(text), _TTL_EMBEDDING, json.dumps(vec))
            await pipe.execute()
        except Exception as exc:
            logger.debug("Embedding cache MSET failed: %s", exc)


# ── Diagnosis cache ───────────────────────────────────────────────────────────

class DiagnosisCache:
    """
    Cache LLM diagnosis results. Key includes question_id + wrong_answer hash
    so different wrong answers for the same question each get their own entry.
    """

    def _key(self, question_id: int, wrong_answer: str) -> str:
        answer_hash = hashlib.md5(wrong_answer.encode()).hexdigest()[:8]
        return f"diag:{question_id}:{answer_hash}"

    async def get(self, question_id: int, wrong_answer: str) -> Optional[dict]:
        try:
            raw = await _get_redis().get(self._key(question_id, wrong_answer))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Diagnosis cache GET failed: %s", exc)
            return None

    async def set(self, question_id: int, wrong_answer: str, result: dict) -> None:
        try:
            await _get_redis().setex(
                self._key(question_id, wrong_answer),
                _TTL_DIAGNOSIS,
                json.dumps(result, ensure_ascii=False),
            )
        except Exception as exc:
            logger.debug("Diagnosis cache SET failed: %s", exc)

    async def invalidate_question(self, question_id: int) -> None:
        """Remove all cached diagnoses for a question (e.g. after content re-index)."""
        try:
            pattern = f"diag:{question_id}:*"
            keys    = await _get_redis().keys(pattern)
            if keys:
                await _get_redis().delete(*keys)
                logger.debug("Invalidated %d diagnosis cache entries for question %d", len(keys), question_id)
        except Exception as exc:
            logger.debug("Diagnosis cache invalidate failed: %s", exc)


# ── Graph cache ───────────────────────────────────────────────────────────────

class GraphCache:
    """
    Cache full knowledge graph per course.
    Invalidated whenever new knowledge nodes are inserted for that course.
    Short TTL (5 min) as a safety net even without explicit invalidation.
    """

    def _key(self, course_id: int) -> str:
        return f"graph:course:{course_id}"

    async def get(self, course_id: int) -> Optional[dict]:
        try:
            raw = await _get_redis().get(self._key(course_id))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Graph cache GET failed: %s", exc)
            return None

    async def set(self, course_id: int, graph: dict) -> None:
        try:
            await _get_redis().setex(
                self._key(course_id), _TTL_GRAPH,
                json.dumps(graph, ensure_ascii=False, default=str),
            )
        except Exception as exc:
            logger.debug("Graph cache SET failed: %s", exc)

    async def invalidate(self, course_id: int) -> None:
        """
        Call this after inserting new knowledge nodes for a course
        so the next graph request reflects the updated structure.
        """
        try:
            deleted = await _get_redis().delete(self._key(course_id))
            if deleted:
                logger.debug("Graph cache invalidated for course_id=%d", course_id)
        except Exception as exc:
            logger.debug("Graph cache invalidate failed: %s", exc)


# ── Singletons ─────────────────────────────────────────────────────────────────
embedding_cache  = EmbeddingCache()
diagnosis_cache  = DiagnosisCache()
graph_cache      = GraphCache()
