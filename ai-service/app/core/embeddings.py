from __future__ import annotations

import asyncio
import logging
import os
from typing import TypeVar

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_embed_model    = None
_reranker_model = None
T = TypeVar("T")

_CACHE_DIR = os.getenv("SENTENCE_TRANSFORMERS_HOME", "/app/.cache/models")


# ── Model loaders ─────────────────────────────────────────────────────────────

def get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _embed_model = SentenceTransformer(
            settings.embedding_model,
            cache_folder=_CACHE_DIR,
        )
        logger.info("Embedding model ready.")
    return _embed_model


def get_reranker():
    global _reranker_model
    if _reranker_model is None:
        try:
            from sentence_transformers.cross_encoder import CrossEncoder
            logger.info("Loading reranker: %s", settings.reranker_model)
            _reranker_model = CrossEncoder(
                settings.reranker_model,
                cache_dir=_CACHE_DIR,
            )
            logger.info("Reranker ready.")
        except Exception as exc:
            logger.warning("Reranker load failed (%s). Reranking disabled.", exc)
            _reranker_model = None
    return _reranker_model


def warm_up_models() -> None:
    """Called once at startup in a background thread."""
    get_embed_model()
    if settings.use_reranker:
        get_reranker()
    logger.info("All models warmed up.")


# ── Prefix helper ─────────────────────────────────────────────────────────────

def _apply_prefix(text: str, role: str) -> str:
    """BGE convention: 'query: ...' for search, 'passage: ...' for indexing."""
    mode = getattr(settings, "embedding_prefix_mode", "none")
    if mode in ("bge", "e5"):
        return f"{role}: {text}"
    return text


# ── Sync compute (runs in thread pool, never blocks the event loop) ───────────

def _embed_sync(texts: list[str]) -> list[list[float]]:
    model = get_embed_model()
    vecs  = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]


async def _run_in_thread(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


# ── Public API (with Redis cache layer) ───────────────────────────────────────

async def create_embedding(text: str) -> list[float]:
    """
    Create a query embedding for the given text.
    Checks Redis cache first; computes and stores if missing.
    """
    from app.core.cache import embedding_cache

    clean = _apply_prefix(text.replace("\n", " ").strip() or " ", "query")

    cached = await embedding_cache.get(clean)
    if cached is not None:
        return cached

    result = await _run_in_thread(_embed_sync, [clean])
    vec = result[0]
    await embedding_cache.set(clean, vec)
    return vec


async def create_passage_embedding(text: str) -> list[float]:
    """
    Create a passage (indexing) embedding.
    Checks Redis cache first; computes and stores if missing.
    """
    from app.core.cache import embedding_cache

    clean = _apply_prefix(text.replace("\n", " ").strip() or " ", "passage")

    cached = await embedding_cache.get(clean)
    if cached is not None:
        return cached

    result = await _run_in_thread(_embed_sync, [clean])
    vec = result[0]
    await embedding_cache.set(clean, vec)
    return vec


async def create_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Batch query embeddings with cache.
    Only computes vectors for cache misses, stores all results.
    """
    from app.core.cache import embedding_cache

    cleans  = [_apply_prefix(t.replace("\n", " ").strip() or " ", "query") for t in texts]
    cached  = await embedding_cache.get_batch(cleans)

    miss_indices = [i for i, c in enumerate(cached) if c is None]
    if miss_indices:
        miss_texts = [cleans[i] for i in miss_indices]
        computed   = await _run_in_thread(_embed_sync, miss_texts)
        await embedding_cache.set_batch(miss_texts, computed)
        for idx, vec in zip(miss_indices, computed):
            cached[idx] = vec

    return cached  # type: ignore[return-value]


async def create_passage_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Batch passage embeddings with cache.
    """
    from app.core.cache import embedding_cache

    cleans  = [_apply_prefix(t.replace("\n", " ").strip() or " ", "passage") for t in texts]
    cached  = await embedding_cache.get_batch(cleans)

    miss_indices = [i for i, c in enumerate(cached) if c is None]
    if miss_indices:
        miss_texts = [cleans[i] for i in miss_indices]
        computed   = await _run_in_thread(_embed_sync, miss_texts)
        await embedding_cache.set_batch(miss_texts, computed)
        for idx, vec in zip(miss_indices, computed):
            cached[idx] = vec

    return cached  # type: ignore[return-value]


# ── Reranking ─────────────────────────────────────────────────────────────────

def _rerank_sync(query: str, passages: list[str]) -> list[float]:
    reranker = get_reranker()
    if reranker is None:
        return [0.0] * len(passages)
    try:
        pairs  = [(query, p) for p in passages]
        scores = reranker.predict(pairs, show_progress_bar=False)
        return [float(s) for s in scores]
    except Exception as exc:
        logger.warning("Reranking failed (%s), using original order.", exc)
        return [0.0] * len(passages)


async def rerank_chunks(
    query: str,
    chunks: list[T],
    text_fn,
    top_k: int,
) -> list[T]:
    if not chunks:
        return chunks
    # Lazy model loading belongs in _rerank_sync's executor too. Loading here
    # blocks the event loop and prevents retrieval deadlines from firing.
    if not settings.use_reranker:
        return chunks[:top_k]
    passages = [text_fn(c) for c in chunks]
    scores   = await _run_in_thread(_rerank_sync, query, passages)
    ranked   = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:top_k]]
