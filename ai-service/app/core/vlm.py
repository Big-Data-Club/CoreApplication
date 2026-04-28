from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory LRU-style cache (image hash -> description)
# Survives the process lifetime; prevents re-calling VLM for the same image
_vlm_cache: dict[str, str] = {}
_MAX_CACHE = 2000

VLM_MODEL = settings.vlm_model
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB safety limit

# Global concurrency limiter for VLM calls — prevents rate-limit storms
# when processing PDFs with many embedded images (95+ images → 95 parallel
# VLM requests → instant 429 from Groq's 30k TPM quota).
_VLM_SEMAPHORE = asyncio.Semaphore(3)

# Rate-limit retry config
_VLM_MAX_RETRIES = 3
_VLM_BASE_BACKOFF = 2.0  # seconds

# ── System prompts ────────────────────────────────────────────────────────────

_SYSTEM_VI = (
    "Bạn là chuyên gia mô tả hình ảnh học thuật. "
    "Nhiệm vụ: mô tả hình ảnh một cách chi tiết, súc tích để phục vụ tìm kiếm ngữ nghĩa. "
    "Không bắt đầu bằng 'Hình ảnh này...' — đi thẳng vào nội dung."
)

_SYSTEM_EN = (
    "You are an expert at describing academic images. "
    "Task: describe the image concisely yet completely for semantic search indexing. "
    "Do not begin with 'This image...' — go straight to content."
)

_PROMPT_VI = """\
Mô tả hình ảnh này cho mục đích lập chỉ mục tìm kiếm. Bao gồm:

1. Loại hình ảnh (biểu đồ, sơ đồ, ảnh chụp màn hình, ảnh chụp thực tế, công thức, v.v.)
2. Nội dung chính — mọi văn bản, nhãn, số liệu, trục, chú thích có trong ảnh
3. Xu hướng / mối quan hệ nếu là biểu đồ hoặc bảng số liệu
4. Ý nghĩa kỹ thuật / học thuật ngắn gọn

Trả lời bằng tiếng Việt, tối đa 200 từ.\
"""

_PROMPT_EN = """\
Describe this image for search indexing purposes. Include:

1. Image type (chart, diagram, screenshot, photo, formula, etc.)
2. Main content — all visible text, labels, numbers, axes, captions
3. Trends / relationships if it is a chart or data table
4. Brief technical / academic significance

Reply in English, max 200 words.\
"""


# ── Public API ────────────────────────────────────────────────────────────────

async def describe_image_url(
    image_url: str,
    language: str = "vi",
    alt_text: str = "",
) -> str:
    """
    Describe an image from a URL (MinIO presigned URL or any HTTP URL).
    Falls back gracefully to alt_text if the image cannot be fetched or VLM fails.
    Results are cached by URL hash.
    """
    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set; skipping VLM for image description.")
        return alt_text or f"[Hình ảnh: {image_url}]"

    cache_key = _cache_key("url", image_url)
    if cache_key in _vlm_cache:
        return _vlm_cache[cache_key]

    try:
        image_b64, mime_type = await _fetch_image_base64(image_url)
        if not image_b64:
            return alt_text or f"[Hình ảnh không thể tải: {image_url}]"

        description = await _call_vlm(image_b64, mime_type, language)
        if description:
            _store_cache(cache_key, description)
            logger.debug("VLM described image url=%s...", image_url[:60])
            return description
    except Exception as exc:
        logger.warning("VLM failed for url=%s: %s", image_url[:60], exc)

    return alt_text or f"[Hình ảnh: {image_url}]"


async def describe_image_bytes(
    image_bytes: bytes,
    language: str = "vi",
    mime_type: str = "image/jpeg",
) -> str:
    """
    Describe an image from raw bytes (e.g. IMAGE content type downloaded from MinIO).
    """
    if not settings.groq_api_key:
        return "[Hình ảnh chưa được mô tả (thiếu API key)]"

    if len(image_bytes) > _MAX_IMAGE_BYTES:
        logger.warning("Image too large (%d bytes); skipping VLM.", len(image_bytes))
        return "[Hình ảnh quá lớn để xử lý]"

    cache_key = _cache_key("bytes", hashlib.sha256(image_bytes[:4096]).hexdigest())
    if cache_key in _vlm_cache:
        return _vlm_cache[cache_key]

    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        description = await _call_vlm(image_b64, mime_type, language)
        if description:
            _store_cache(cache_key, description)
            return description
    except Exception as exc:
        logger.warning("VLM bytes description failed: %s", exc)

    return "[Hình ảnh không thể mô tả]"


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _fetch_image_base64(url: str) -> tuple[Optional[str], str]:
    """
    Fetch image from URL, return (base64_string, mime_type).
    Returns (None, '') on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10),
        ) as client:
            response = await client.get(url)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
                # Guard size
                if len(response.content) > _MAX_IMAGE_BYTES:
                    logger.warning("Image at %s is too large (%d bytes)", url[:60], len(response.content))
                    return None, ""
                b64 = base64.b64encode(response.content).decode("utf-8")
                return b64, content_type
            else:
                logger.warning("Image fetch failed status=%d url=%s", response.status_code, url[:60])
    except Exception as exc:
        logger.warning("Failed to fetch image %s: %s", url[:60], exc)
    return None, ""


async def _call_vlm(image_b64: str, mime_type: str, language: str = "vi") -> str:
    """
    Call Groq vision API and return the text description.

    Guarded by _VLM_SEMAPHORE to cap concurrency and includes exponential
    backoff for 429 rate-limit errors.
    """
    from groq import AsyncGroq

    async with _VLM_SEMAPHORE:
        client = AsyncGroq(api_key=settings.groq_api_key)
        system = _SYSTEM_VI if language == "vi" else _SYSTEM_EN
        prompt = _PROMPT_VI if language == "vi" else _PROMPT_EN

        # Groq vision expects data URL format
        data_url = f"data:{mime_type};base64,{image_b64}"

        last_exc: Exception | None = None
        for attempt in range(_VLM_MAX_RETRIES + 1):
            try:
                response = await client.chat.completions.create(
                    model=VLM_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": data_url}},
                                {"type": "text", "text": prompt},
                            ],
                        },
                    ],
                    temperature=0.1,
                    max_tokens=512,
                )
                return response.choices[0].message.content.strip()
            except Exception as exc:
                last_exc = exc
                # Check for rate-limit (429) error
                status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
                if status == 429 and attempt < _VLM_MAX_RETRIES:
                    wait = _VLM_BASE_BACKOFF * (2 ** attempt)
                    logger.warning(
                        "VLM rate limited (429), retrying in %.1fs (attempt %d/%d)",
                        wait, attempt + 1, _VLM_MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        raise last_exc  # type: ignore[misc]


def _cache_key(prefix: str, value: str) -> str:
    h = hashlib.md5(value.encode()).hexdigest()
    return f"{prefix}:{h}"


def _store_cache(key: str, value: str) -> None:
    if len(_vlm_cache) >= _MAX_CACHE:
        # Evict oldest 10%
        for k in list(_vlm_cache.keys())[: _MAX_CACHE // 10]:
            _vlm_cache.pop(k, None)
    _vlm_cache[key] = value