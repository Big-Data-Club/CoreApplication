"""
ai-service/app/core/multilingual.py

Cross-lingual retrieval strategy — two modes:

NATIVE MODE  (settings.use_native_multilingual = True, default with bge-m3)

  BAAI/bge-m3 maps Vietnamese and English text into the same vector space.
  A Vietnamese query finds English chunks directly — no translation needed.
  This eliminates ~100 ms of Groq latency and saves token quota entirely.

TRANSLATION MODE  (settings.use_native_multilingual = False, nomic-ai)

  The original dual-search + RRF pipeline (kept for backward compatibility
  and as a fallback when the bge-m3 model is unavailable):
    1. Detect language of query (VI / EN)
    2. Translate to the other language via LLM (fast, cached)
    3. Run both searches in parallel
    4. Merge with Reciprocal Rank Fusion (RRF)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Callable, TypeVar

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

T = TypeVar("T")

# Translation cache (used only in translation mode) 
_translation_cache: dict[str, str] = {}


# Language detection 

def detect_query_language(text: str) -> str:
    from app.services.chunker import detect_language
    return detect_language(text)


# Translation (translation mode only) 

async def translate_query(text: str, target_lang: str) -> str:
    text = text.strip()
    if not text:
        return text

    cache_key = f"{target_lang}:{hashlib.md5(text.encode()).hexdigest()}"
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    prompt = (
        "Dịch đoạn văn sau sang tiếng Việt học thuật, chỉ trả về bản dịch:\n\n" + text
        if target_lang == "vi"
        else "Translate the following to academic English. Return only the translation:\n\n" + text
    )

    try:
        from app.core.llm import chat_complete
        from app.core.llm_gateway import TASK_LANGUAGE_DETECT
        result = (await chat_complete(
            messages=[{"role": "user", "content": prompt}],
            model=settings.chat_model,
            temperature=0.05,
            max_tokens=300,
            task=TASK_LANGUAGE_DETECT,
        )).strip()

        if result and result.lower() != text.lower():
            _translation_cache[cache_key] = result
            return result
        return text
    except Exception as exc:
        logger.warning(f"translate_query failed: {exc}")
        return text


async def expand_query_bilingual(query: str) -> tuple[str, str]:
    src = detect_query_language(query)
    tgt = "en" if src == "vi" else "vi"
    translated = await translate_query(query, tgt)
    return query, translated


# Reciprocal Rank Fusion 

def reciprocal_rank_fusion(
    result_lists: list[list[T]],
    id_fn: Callable[[T], Any],
    k: int = 60,
) -> list[T]:
    scores: dict[Any, float] = {}
    items: dict[Any, T] = {}

    for result_list in result_lists:
        for rank, item in enumerate(result_list):
            item_id = id_fn(item)
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
            if item_id not in items:
                items[item_id] = item
            else:
                existing = items[item_id]
                if (
                    hasattr(item, "similarity")
                    and hasattr(existing, "similarity")
                    and item.similarity > existing.similarity
                ):
                    items[item_id] = item

    return [items[i] for i in sorted(scores, key=lambda x: scores[x], reverse=True)]


# High-level search wrapper 

async def multilingual_search(
    search_fn,
    query: str,
    top_k: int,
    id_fn: Callable,
    min_similarity: float = 0.25,
    **search_kwargs,
) -> list:
    """
    Route to native mode or translation mode based on settings.

    Native mode (bge-m3):
      Single search — the model handles cross-lingual natively.
      ~2x faster, no LLM translation cost.

    Translation mode (nomic-ai):
      Translate -> dual search -> RRF merge.
    """
    if settings.use_native_multilingual:
        # Native bge-m3 path 
        return await search_fn(
            query=query,
            top_k=top_k,
            min_similarity=min_similarity,
            **search_kwargs,
        )

    # Translation + RRF path (nomic-ai fallback) 
    fetch_k = top_k * 2
    original_query, translated_query = await expand_query_bilingual(query)

    if translated_query.lower() == original_query.lower():
        return await search_fn(
            query=original_query,
            top_k=top_k,
            min_similarity=min_similarity,
            **search_kwargs,
        )

    original_results, translated_results = await asyncio.gather(
        search_fn(query=original_query, top_k=fetch_k,
                  min_similarity=min_similarity, **search_kwargs),
        search_fn(query=translated_query, top_k=fetch_k,
                  min_similarity=min_similarity - 0.05, **search_kwargs),
    )

    logger.debug(
        "Multilingual RRF: orig=%d translated=%d | '%s' -> '%s'",
        len(original_results), len(translated_results),
        original_query[:50], translated_query[:50],
    )

    if not translated_results:
        return original_results[:top_k]

    merged = reciprocal_rank_fusion(
        [original_results, translated_results], id_fn=id_fn
    )
    return merged[:top_k]