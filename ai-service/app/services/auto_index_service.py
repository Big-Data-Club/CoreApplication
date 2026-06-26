"""
ai-service/app/services/auto_index_service.py

Changes vs. previous version (pgvector):
  - Node deduplication reads vectors from Qdrant (scroll_nodes_for_course)
    instead of querying the description_embedding column in PostgreSQL.
    This eliminates ~50 MB per course of PG->Python data transfer.
  - _create_knowledge_nodes_batch upserts node vectors to Qdrant
    in addition to inserting metadata into PG.
  - _batch_insert_chunks delegates to rag_service (which handles the
    Qdrant/pgvector routing internally).
  - _build_graph_edges uses vectors from Qdrant instead of AI PG.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.llm import chat_complete_json, create_embeddings_batch
from app.core.llm_gateway import TASK_NODE_EXTRACT
from app.services.chunker import (
    PDFChunker,
    DocxChunker,
    PptxChunker,
    ExcelChunker,
    MarkdownChunker,
    ImageChunker,
    VideoTranscriptChunker,
    DocumentChunk,
    detect_language,
    sanitize_text,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Tuning constants ──────────────────────────────────────────────────────────
RELATION_SIMILARITY_THRESHOLD = 0.62
MAX_NODES_PER_BATCH = 5
MIN_NODES_PER_BATCH = 2
EMBED_BATCH_SIZE = 16
MAX_EXCERPT_CHARS = 9000
MAX_EXISTING_NODES_FOR_GRAPH = 200

# Cross-document dedup: aggressively merge to prevent node explosion
DEDUP_HARD_THRESHOLD = 0.88   # was 0.92 — reuse nodes more aggressively
DEDUP_SOFT_THRESHOLD = 0.72   # was 0.80 — wider merge window

# Within the same indexing run, collapse near-duplicate nodes from different
# batches before comparing against the DB. This is the #1 fix for node
# explosion: batches A and B both extracting "System Call" as separate nodes.
INTRA_RUN_DEDUP_THRESHOLD = 0.85

# Minimum characters of real content a chunk must have to be worth sending
# to the LLM for node extraction. Prevents wasting calls on boilerplate.
MIN_CHUNK_CONTENT_CHARS = 100


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ExtractedNode:
    name: str
    name_vi: str
    name_en: str
    description: str
    keywords: list[str]
    order_index: int


@dataclass
class ExtractedRelation:
    source_index: int
    target_index: int
    relation_type: str
    reason: str
    strength: float = 0.85


# ── LLM prompts ───────────────────────────────────────────────────────────────

NODE_EXTRACTION_SYSTEM = """\
You are an expert curriculum analyst and learning experience designer.
Your task is to identify core knowledge concepts (nodes) that appear DIRECTLY in the document to design bite-sized learning pathways (micro-lessons).

Important principles for micro-learning optimization:
1. HIGH SEMANTIC STANDARD: Extract only topics with specific theoretical content, definitions, formulas, or technical methods.
   - DO NOT create nodes for generic or vague sections like "Introduction", "Overview", "Basic Concepts", "Preface", "Conclusion", "Examples", "Exercises", "References", etc.
   - Instead of a generic "Introduction" node, create a node describing the primary concept being introduced (e.g., "Concept and Role of Operating Systems").
2. REASONABLE GRANULARITY (No Fragmented Nodes): Avoid overly small or fragmented concepts to prevent shallow, disjointed learning.
   - Group closely related topics into a single comprehensive node (e.g., instead of creating separate nodes for "If Statement", "Else Statement", and "Elif Statement", group them into "Conditional Structures (If-Else) in Python").
   - A node must contain enough substance to support a ~5-minute reading lesson (~700-1100 words) and allow for 3-5 distinct test questions.
3. NO DUPLICATION: Ensure the extracted nodes do not overlap semantically with each other.
4. FILTER BOILERPLATE & METADATA: Disregard copyright info (©), page numbers, publisher names, university logos, author names, etc. If the text only contains metadata or lacks academic substance, return an empty structure: {"nodes": [], "prerequisites": []}.

Return ONLY valid JSON according to the requested schema. No conversational text.\
"""


def build_node_extraction_prompt(
    document_excerpt: str,
    file_type: str,
    language: str,
    doc_title: Optional[str],
    detected_headings: list[str],
    max_nodes: int,
) -> str:
    lang_output_hint = (
        "Output requirements: Always provide both 'name_vi' (Vietnamese) and 'name_en' (English) topic names. "
        "Write the 'description' and 'reason' fields in Vietnamese."
        if language == "vi" else
        "Output requirements: Always provide both 'name_vi' (Vietnamese) and 'name_en' (English) topic names. "
        "Write the 'description' and 'reason' fields in English."
    )
    
    file_hint_map = {
        "pdf":   "PDF document",
        "docx":  "Word document",
        "pptx":  "PowerPoint presentation",
        "xlsx":  "Excel spreadsheet",
        "text":  "Markdown text",
        "image": "Described image",
        "video": "Lecture video transcript",
        "txt":   "Plain text file",
    }
    file_hint = file_hint_map.get(file_type, "learning material")

    heading_context = ""
    if detected_headings:
        heading_context = "\nDETECTED HEADINGS IN DOCUMENT:\n" + "\n".join(
            f"  - {h}" for h in detected_headings[:20]
        ) + "\n"
    title_context = f"\nDOCUMENT TITLE: {doc_title}\n" if doc_title else ""

    schema = """{
  "nodes": [
    {
      "name_vi": "Vietnamese topic name (highly accurate, academic style)",
      "name_en": "English topic name (highly accurate, corresponding to name_vi)",
      "description": "A 2-3 sentence description of the specific knowledge concept covered in the document",
      "keywords": ["keyword 1", "keyword 2", "keyword 3"]
    }
  ],
  "prerequisites": [
    {
      "source_index": 0,
      "target_index": 2,
      "relation_type": "prerequisite", // Logical relation type: prerequisite, extends, equivalent, contrasts_with, or related
      "reason": "Brief explanation of why this relation exists",
      "strength": 0.9
    }
  ]
}"""
    return f"""\
Document Type: {file_hint}
{title_context}{heading_context}
TASK: Identify exactly {max_nodes} most important knowledge topics (nodes) from the source document.
{lang_output_hint}

DOCUMENT CONTENT:
{document_excerpt}

Return ONLY valid JSON matching the schema (no markdown wrapper or extra text):
{schema}"""



# ── File type detection ────────────────────────────────────────────────────────

def _detect_file_type(file_url: str, content_type: str) -> str:
    from app.services.youtube_service import is_youtube_url
    if is_youtube_url(file_url):
        return "youtube"
    url_lower = file_url.lower()
    ct_lower  = content_type.lower()
    if "/image/" in url_lower or "/images/" in url_lower:
        return "image"
    if url_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")):
        return "image"
    if url_lower.endswith(".pdf"):
        return "pdf"
    if url_lower.endswith((".docx", ".doc")):
        return "docx"
    if url_lower.endswith((".pptx", ".ppt")):
        return "pptx"
    if url_lower.endswith((".xlsx", ".xls")):
        return "xlsx"
    if url_lower.endswith((".mp4", ".webm", ".mov", ".avi")):
        return "video"
    if url_lower.endswith((".md", ".markdown")):
        return "text"
    if "pdf" in ct_lower:
        return "pdf"
    if "word" in ct_lower:
        return "docx"
    if "presentation" in ct_lower:
        return "pptx"
    if "spreadsheet" in ct_lower or "excel" in ct_lower:
        return "xlsx"
    if "video" in ct_lower:
        return "video"
    if "text" in ct_lower or "markdown" in ct_lower:
        return "text"
    if "image" in ct_lower:
        return "image"
    return "txt"


def _get_image_mime(file_url: str, content_type: str) -> str:
    url_lower = file_url.lower()
    if url_lower.endswith(".png"):
        return "image/png"
    if url_lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if url_lower.endswith(".gif"):
        return "image/gif"
    if url_lower.endswith(".webp"):
        return "image/webp"
    if content_type.startswith("image/"):
        return content_type
    return "image/jpeg"


# ── Text helpers ──────────────────────────────────────────────────────────────

def _extract_headings(text: str, max_headings: int = 30) -> list[str]:
    import re
    headings: list[str] = []
    for m in re.finditer(r"^(#{1,6})\s+(.+)$", text, flags=re.MULTILINE):
        headings.append(m.group(2).strip())
        if len(headings) >= max_headings:
            break
    if not headings:
        pat = re.compile(r"^(?:\d+[\.\)]\s+|[IVXivx]+[\.\)]\s+|[A-ZÀÁẠẢÃ])")
        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) > 80 or line.endswith("."):
                continue
            if pat.match(line) or (line.isupper() and len(line) > 3):
                headings.append(line)
                if len(headings) >= max_headings:
                    break
    return headings


def _extract_doc_title(text: str) -> Optional[str]:
    import re
    m = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    if m:
        return m.group(1).strip()
    for line in text.split("\n")[:10]:
        line = line.strip()
        if line and 5 < len(line) < 120:
            return line
    return None


def _smart_excerpt(text: str, max_chars: int = MAX_EXCERPT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    n_parts, part_size = 5, max_chars // 5
    total_len, step = len(text), len(text) // 5
    parts = []
    for i in range(n_parts):
        start = i * step
        snippet = text[start: min(start + part_size, total_len)].strip()
        if snippet:
            parts.append(snippet)
    return "\n\n[...]\n\n".join(parts)


# ── Embedding batch helper ─────────────────────────────────────────────────────

async def _batch_embed(texts: list[str]) -> list[list[float]]:
    results: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = await create_embeddings_batch(texts[i: i + EMBED_BATCH_SIZE])
        results.extend(batch)
    return results


# ── MinIO presigned URL helper ────────────────────────────────────────────────

def _get_minio_presigned_url(path_key: str, expires_in_seconds: int = 3600) -> Optional[str]:
    try:
        import httpx
        lms_base = settings.lms_service_url.rstrip("/")
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{lms_base}/api/v1/files/presigned/{path_key}",
                params={"expires": expires_in_seconds},
                headers={"X-API-Secret": settings.ai_service_secret},
            )
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("presigned_url")
            logger.warning("Presigned URL: %d for %s", resp.status_code, path_key[:50])
    except Exception as exc:
        logger.warning("Presigned URL error for %s: %s", path_key[:50], exc)
    return None


# ── Main service ───────────────────────────────────────────────────────────────

class AutoIndexService:

    # ─ Public entry points ────────────────────────────────────────────────────

    async def auto_index(
        self,
        content_id: int,
        course_id: int,
        file_url: str,
        content_type: str,
        file_bytes: Optional[bytes] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        logger.info("AutoIndex start: content_id=%d type=%s", content_id, content_type)

        from app.services.youtube_service import is_youtube_url
        is_yt = is_youtube_url(file_url)

        if not file_bytes and not is_yt:
            logger.error("AutoIndex: empty file_bytes for content_id=%d", content_id)
            await self._update_content_status(content_id, "failed", "Empty file bytes")
            return {"ok": False, "error": "Empty file bytes"}

        def _progress(stage: str, pct: int):
            logger.debug("AutoIndex [%d] %s: %d%%", content_id, stage, pct)
            if progress_callback:
                progress_callback(stage, pct)

        try:
            _progress("extract", 10)
            file_type = _detect_file_type(file_url, content_type)
            raw_text, structured_chunks = await self._extract_text_and_chunks(
                file_bytes, file_type, content_id, file_url
            )

            if not raw_text.strip():
                await self._update_content_status(content_id, "failed", "Empty document text")
                return {"ok": False, "error": "Empty document text"}

            _progress("llm_analysis", 20)
            language = detect_language(raw_text[:3000])
            nodes, relations = await self._batch_extract_nodes(
                structured_chunks, raw_text, file_type, language, file_url
            )

            if not nodes:
                logger.info("AutoIndex: no nodes extracted for content_id=%d (may be boilerplate-only)", content_id)
                await self._update_content_status(content_id, "indexed")
                return {"ok": True, "node_ids": [], "new_nodes_created": 0,
                        "nodes_reused": 0, "chunks_created": 0,
                        "language": language, "file_type": file_type}

            _progress("embed_nodes", 40)
            node_desc_texts = [
                f"{n.name_vi or n.name}: {n.description} Từ khóa: {', '.join(n.keywords)}"
                for n in nodes
            ]
            node_embeddings = await _batch_embed(node_desc_texts)

            _progress("dedup_nodes", 48)
            truly_new_nodes, truly_new_embs, idx_to_existing = \
                await self._deduplicate_nodes(nodes, node_embeddings, course_id)

            _progress("create_nodes", 52)
            new_node_ids: list[int] = []
            if truly_new_nodes:
                new_node_ids = await self._create_knowledge_nodes_batch(
                    truly_new_nodes, truly_new_embs, course_id, content_id
                )

            all_node_ids, all_node_embeddings = self._build_combined_node_list(
                nodes, node_embeddings, idx_to_existing, truly_new_nodes, new_node_ids
            )

            await self._create_llm_relations(relations, all_node_ids, course_id)

            _progress("chunk_embed", 60)
            n_chunks = await self._chunk_and_store(
                file_bytes=file_bytes, file_type=file_type,
                structured_chunks=structured_chunks,
                content_id=content_id, course_id=course_id,
                node_ids=all_node_ids, node_embeddings=all_node_embeddings,
                language=language,
            )

            _progress("build_graph", 90)
            await self._build_graph_edges(all_node_ids, all_node_embeddings, course_id)

            # ── GROUNDING GUARD: Cleanup orphaned nodes ─────────────────────
            # Only cleanup nodes created in this specific run (newly created)
            if new_node_ids:
                orphaned_ids = await self._cleanup_orphaned_nodes(new_node_ids, course_id)
                if orphaned_ids:
                    # Filter them out from the list to be synced to Neo4j
                    orphaned_set = set(orphaned_ids)
                    all_node_ids = [nid for nid in all_node_ids if nid not in orphaned_set]
            
            if settings.neo4j_enabled:
                await self._sync_to_neo4j(
                    node_ids=all_node_ids,
                    nodes=nodes,
                    node_embeddings=all_node_embeddings,
                    course_id=course_id,
                    content_id=content_id,
                    llm_relations=relations,
                )

            await self._update_content_status(content_id, "indexed")
            _progress("done", 100)

            logger.info(
                "AutoIndex done: content_id=%d new_nodes=%d reused=%d chunks=%d",
                content_id, len(new_node_ids), len(idx_to_existing), n_chunks,
            )
            return {
                "ok": True, "node_ids": all_node_ids,
                "new_nodes_created": len(new_node_ids),
                "nodes_reused":      len(idx_to_existing),
                "chunks_created":    n_chunks,
                "language":          language,
                "file_type":         file_type,
            }

        except Exception as exc:
            logger.error("AutoIndex failed content_id=%d: %s", content_id, exc, exc_info=True)
            await self._update_content_status(content_id, "failed", str(exc)[:300])
            raise

    async def auto_index_text(
        self,
        content_id: int,
        course_id: int,
        title: str,
        text_content: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        logger.info(
            "AutoIndexText start: content_id=%d title=%s len=%d",
            content_id, title, len(text_content),
        )

        def _progress(stage: str, pct: int):
            logger.debug("AutoIndexText [%d] %s: %d%%", content_id, stage, pct)
            if progress_callback:
                progress_callback(stage, pct)

        try:
            _progress("parse", 10)
            if not text_content.strip():
                await self._update_content_status(content_id, "failed", "Empty text")
                return {"ok": False, "error": "Empty text content"}

            language = detect_language(text_content[:3000])

            _progress("chunk", 15)
            from app.core.vlm import describe_image_url

            chunker = MarkdownChunker()

            async def image_describer(image_url: str, alt_text: str) -> str:
                url_to_use = await self._get_vlm_ready_url(image_url)
                return await describe_image_url(url_to_use, language=language, alt_text=alt_text)

            structured_chunks = await chunker.chunk_async(
                markdown_text=text_content, image_describer=image_describer
            )

            _progress("llm_analysis", 25)
            nodes, relations = await self._batch_extract_nodes(
                structured_chunks, text_content, "text", language, doc_title=title
            )

            if not nodes:
                logger.info("AutoIndexText: no nodes for content_id=%d (may be boilerplate-only)", content_id)
                await self._update_content_status(content_id, "indexed")
                return {"ok": True, "node_ids": [], "new_nodes_created": 0,
                        "nodes_reused": 0, "chunks_created": 0,
                        "language": language, "file_type": "text"}

            _progress("embed_nodes", 40)
            node_desc_texts = [
                f"{n.name_vi or n.name}: {n.description} Từ khóa: {', '.join(n.keywords)}"
                for n in nodes
            ]
            node_embeddings = await _batch_embed(node_desc_texts)

            _progress("dedup_nodes", 48)
            truly_new_nodes, truly_new_embs, idx_to_existing = \
                await self._deduplicate_nodes(nodes, node_embeddings, course_id)

            _progress("create_nodes", 52)
            new_node_ids: list[int] = []
            if truly_new_nodes:
                new_node_ids = await self._create_knowledge_nodes_batch(
                    truly_new_nodes, truly_new_embs, course_id, content_id
                )

            all_node_ids, all_node_embeddings = self._build_combined_node_list(
                nodes, node_embeddings, idx_to_existing, truly_new_nodes, new_node_ids
            )
            await self._create_llm_relations(relations, all_node_ids, course_id)

            _progress("chunk_embed", 60)
            n_chunks = await self._chunk_and_store(
                file_bytes=text_content.encode("utf-8"),
                file_type="text",
                structured_chunks=structured_chunks,
                content_id=content_id, course_id=course_id,
                node_ids=all_node_ids, node_embeddings=all_node_embeddings,
                language=language,
            )

            _progress("build_graph", 90)
            await self._build_graph_edges(all_node_ids, all_node_embeddings, course_id)

            # ── GROUNDING GUARD: Cleanup orphaned nodes ─────────────────────
            if new_node_ids:
                orphaned_ids = await self._cleanup_orphaned_nodes(new_node_ids, course_id)
                if orphaned_ids:
                    orphaned_set = set(orphaned_ids)
                    all_node_ids = [nid for nid in all_node_ids if nid not in orphaned_set]

            if settings.neo4j_enabled:
                await self._sync_to_neo4j(
                    node_ids=all_node_ids,
                    nodes=nodes,
                    node_embeddings=all_node_embeddings,
                    course_id=course_id,
                    content_id=content_id,
                    llm_relations=relations,
                )

            await self._update_content_status(content_id, "indexed")
            _progress("done", 100)

            return {
                "ok": True, "node_ids": all_node_ids,
                "new_nodes_created": len(new_node_ids),
                "nodes_reused":      len(idx_to_existing),
                "chunks_created":    n_chunks,
                "language":          language,
                "file_type":         "text",
            }

        except Exception as exc:
            logger.error("AutoIndexText failed content_id=%d: %s", content_id, exc, exc_info=True)
            await self._update_content_status(content_id, "failed", str(exc)[:300])
            raise

    # ─ Step 1: Download ───────────────────────────────────────────────────────

    async def _download_bytes(self, file_url: str) -> bytes:
        loop = asyncio.get_event_loop()

        def _sync_download() -> bytes:
            try:
                from minio import Minio
                # R2/S3 endpoints should not have https:// prefix for the Minio client
                endpoint = settings.minio_endpoint.replace("https://", "").replace("http://", "")
                
                client = Minio(
                    endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_use_ssl,
                )
                bucket = settings.minio_bucket
                response = client.get_object(bucket, file_url)
                try:
                    buf = io.BytesIO()
                    for chunk in response.stream(1 * 1024 * 1024):
                        buf.write(chunk)
                    return buf.getvalue()
                finally:
                    response.close()
                    response.release_conn()
            except Exception as exc:
                logger.error("Download failed %s: %s", file_url[:80], exc, exc_info=True)
                return b""

        return await loop.run_in_executor(None, _sync_download)

    # ─ Step 2: Extract text + chunks ─────────────────────────────────────────
    async def _extract_youtube(self, file_url: str) -> tuple[str, list[DocumentChunk]]:
        """Fetch YouTube transcript -> VideoTranscriptChunker -> DocumentChunks."""
        from app.services.youtube_service import youtube_fetcher
        from app.services.chunker import VideoTranscriptChunker, detect_language

        preferred_lang = "vi"

        result = await youtube_fetcher.fetch(file_url, preferred_language=preferred_lang)
        segments = result["segments"]
        language = result["language"]

        if not segments:
            raise ValueError(f"Empty transcript for YouTube URL: {file_url}")

        chunker = VideoTranscriptChunker(
            segment_duration_sec=120,
            overlap_sec=15,
        )
        chunks = chunker.chunk_whisper_json({"segments": segments})

        # Gắn language đúng từ transcript
        for chunk in chunks:
            chunk.language = language

        raw_text = " ".join(seg["text"] for seg in segments[:500])
        return raw_text, chunks

    async def _extract_text_and_chunks(
        self,
        file_bytes: bytes,
        file_type: str,
        content_id: int,
        file_url: str = "",
    ) -> tuple[str, list[DocumentChunk]]:
        if file_type == "youtube":
            return await self._extract_youtube(file_url)
        if file_type == "text":
            from app.core.vlm import describe_image_url
            text     = file_bytes.decode("utf-8", errors="replace")
            language = detect_language(text[:2000])
            chunker  = MarkdownChunker(
                chunk_size=settings.chunk_size, overlap=settings.chunk_overlap
            )

            async def image_describer_with_minio(url: str, alt_text: str) -> str:
                url_to_use = await self._get_vlm_ready_url(url)
                return await describe_image_url(url_to_use, language=language, alt_text=alt_text)

            chunks   = await chunker.chunk_async(text, image_describer=image_describer_with_minio)
            raw_text = "\n\n".join(c.text for c in chunks)
            return raw_text, chunks

        if file_type == "image":
            mime    = _get_image_mime(file_url, "image/jpeg")
            chunker = ImageChunker()
            chunks  = await chunker.chunk_async(file_bytes, mime_type=mime, language="vi")
            return (chunks[0].text if chunks else ""), chunks

        # ── Unified Markdown pipeline ──────────────────────────────────
        # Office documents (PDF/DOCX/PPTX/XLSX) are now normalised to
        # Markdown first, then run through MarkdownChunker — the same
        # chunker used for native Markdown input. Benefits:
        #   * heading-aware breadcrumbs in chunks
        #   * VLM descriptions for embedded images (via image_describer)
        #   * VLM-OCR fallback for scanned PDFs
        #   * tables get the natural-language column header prefix
        if file_type in ("pdf", "docx", "pptx", "xlsx"):
            from app.services.file_to_markdown import convert_to_markdown
            from app.core.vlm import describe_image_url

            language_guess = "vi"
            try:
                converted = await convert_to_markdown(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    storage_prefix=f"document-images/{content_id}",
                    language=language_guess,
                )
            except Exception as exc:
                logger.error("Unified Markdown convert failed (%s): %s — falling back",
                             file_type, exc, exc_info=True)
                converted = None

            if converted and converted.markdown.strip():
                language = detect_language(converted.markdown[:3000])
                chunker = MarkdownChunker(
                    chunk_size=settings.chunk_size, overlap=settings.chunk_overlap,
                )

                async def image_describer(image_url: str, alt_text: str) -> str:
                    url_to_use = await self._get_vlm_ready_url(image_url)
                    return await describe_image_url(url_to_use, language=language, alt_text=alt_text)

                chunks = await chunker.chunk_async(
                    markdown_text=converted.markdown,
                    image_describer=image_describer,
                )
                if chunks:
                    raw_text = "\n\n".join(c.text for c in chunks)
                    return raw_text, chunks

        # ── Fallback: legacy synchronous chunkers ──────────────────────
        # Triggered when the unified Markdown path produces nothing
        # (e.g. PyMuPDF missing, all pages empty, mammoth crash).
        loop = asyncio.get_event_loop()

        def _sync_extract() -> list[DocumentChunk]:
            chunker_map = {
                "pdf":  PDFChunker(chunk_size=settings.chunk_size, overlap=settings.chunk_overlap),
                "docx": DocxChunker(chunk_size=settings.chunk_size, overlap=settings.chunk_overlap),
                "pptx": PptxChunker(chunk_size=settings.chunk_size, overlap=settings.chunk_overlap),
                "xlsx": ExcelChunker(chunk_size=settings.chunk_size, overlap=settings.chunk_overlap),
            }
            if file_type in chunker_map:
                try:
                    return chunker_map[file_type].chunk_bytes(file_bytes)
                except Exception as exc:
                    logger.error("Extract %s failed: %s", file_type, exc, exc_info=True)
                    return []
            if file_type == "video":
                return []
            text = file_bytes.decode("utf-8", errors="replace")
            chunker = PDFChunker(chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
            raw = chunker._split_text(text)
            return [
                DocumentChunk(
                    text=sanitize_text(c), index=i, source_type="document",
                    page_number=1, language=detect_language(c),
                )
                for i, c in enumerate(raw)
            ]

        chunks   = await loop.run_in_executor(None, _sync_extract)
        raw_text = "\n\n".join(c.text for c in chunks)
        return raw_text, chunks

    # ─ Step 3: LLM node + relation extraction ─────────────────────────────────

    async def _batch_extract_nodes(
        self,
        structured_chunks: list[DocumentChunk],
        raw_text: str,
        file_type: str,
        language: str,
        file_url: str = "",
        doc_title: Optional[str] = None,
    ) -> tuple[list[ExtractedNode], list[ExtractedRelation]]:
        if not structured_chunks:
            return await self._extract_nodes_and_relations(raw_text, file_type, language, file_url, doc_title)

        # ── Pre-filter: discard boilerplate/thin chunks ────────────────
        from app.services.chunker import MarkdownChunker
        quality_chunks = [
            c for c in structured_chunks
            if len(c.text.strip()) >= MIN_CHUNK_CONTENT_CHARS
            and not MarkdownChunker._is_boilerplate(c.text)
        ]
        skipped = len(structured_chunks) - len(quality_chunks)
        if skipped:
            logger.info(
                "Pre-filter: skipped %d/%d boilerplate/thin chunks",
                skipped, len(structured_chunks),
            )
        if not quality_chunks:
            logger.warning("All chunks are boilerplate — no nodes to extract")
            return [], []

        BATCH_SIZE = 15
        all_nodes = []
        all_relations = []
        node_offset = 0
        
        for i in range(0, len(quality_chunks), BATCH_SIZE):
            batch_chunks = quality_chunks[i:i+BATCH_SIZE]
            batch_text = "\n\n".join(c.text for c in batch_chunks)
            if not batch_text.strip():
                continue
                
            nodes, relations = await self._extract_nodes_and_relations(
                batch_text, file_type, language, file_url, doc_title
            )
            
            for r in relations:
                r.source_index += node_offset
                r.target_index += node_offset
                all_relations.append(r)
                
            all_nodes.extend(nodes)
            node_offset += len(nodes)

        # ── Intra-run deduplication ────────────────────────────────────
        # Collapse near-identical nodes extracted from different batches
        # of the SAME document. This is the primary fix for node explosion.
        if len(all_nodes) > 1:
            all_nodes, all_relations = await self._intra_run_dedup(
                all_nodes, all_relations
            )

        return all_nodes, all_relations

    async def _extract_nodes_and_relations(
        self,
        raw_text: str,
        file_type: str,
        language: str,
        file_url: str = "",
        doc_title: Optional[str] = None,
    ) -> tuple[list[ExtractedNode], list[ExtractedRelation]]:
        n_nodes = min(MAX_NODES_PER_BATCH, max(MIN_NODES_PER_BATCH, len(raw_text) // 1500))
        if doc_title is None:
            doc_title = _extract_doc_title(raw_text)
        headings = _extract_headings(raw_text)
        excerpt  = _smart_excerpt(raw_text, MAX_EXCERPT_CHARS)

        prompt = build_node_extraction_prompt(
            document_excerpt=excerpt, file_type=file_type, language=language,
            doc_title=doc_title, detected_headings=headings, max_nodes=n_nodes,
        )
        messages = [
            {"role": "system", "content": NODE_EXTRACTION_SYSTEM},
            {"role": "user",   "content": prompt},
        ]

        try:
            result = await chat_complete_json(
                messages=messages, model=settings.quiz_model,
                temperature=0.15, max_tokens=2048,
                task=TASK_NODE_EXTRACT,
            )
        except Exception as exc:
            logger.error("LLM node extraction failed: %s", exc, exc_info=True)
            fallback_name = doc_title or "Nội dung tài liệu"
            return ([ExtractedNode(
                name=fallback_name, name_vi=fallback_name, name_en=fallback_name,
                description="", keywords=[], order_index=0,
            )], [])

        raw_nodes = result.get("nodes", [])
        nodes: list[ExtractedNode] = []
        for i, n in enumerate(raw_nodes[:MAX_NODES_PER_BATCH]):
            name_vi = n.get("name_vi") or n.get("name", "")
            name_en = n.get("name_en") or n.get("name", "")
            if not (name_vi or name_en):
                continue
            nodes.append(ExtractedNode(
                name=name_vi or name_en, name_vi=name_vi, name_en=name_en,
                description=n.get("description", "")[:500],
                keywords=n.get("keywords", [])[:8],
                order_index=i,
            ))

        raw_rels = result.get("prerequisites", [])
        relations: list[ExtractedRelation] = []
        for r in raw_rels:
            src, tgt = r.get("source_index"), r.get("target_index")
            if not (isinstance(src, int) and isinstance(tgt, int)):
                continue
            if src == tgt or src >= len(nodes) or tgt >= len(nodes):
                continue
            relations.append(ExtractedRelation(
                source_index=src, target_index=tgt,
                relation_type=r.get("relation_type", "prerequisite"),
                reason=r.get("reason", ""),
                strength=float(r.get("strength", 0.85)),
            ))

        logger.info("LLM extracted %d nodes, %d relations", len(nodes), len(relations))
        return nodes, relations

    # ─ Step 4: Node deduplication (Qdrant-backed) ─────────────────────────────

    async def _deduplicate_nodes(
        self,
        nodes: list[ExtractedNode],
        embeddings: list[list[float]],
        course_id: int,
    ) -> tuple[list[ExtractedNode], list[list[float]], dict[int, int]]:
        """
        Compare proposed nodes against existing nodes in this course.

        With USE_QDRANT=true, reads vectors from Qdrant (scroll).
        With USE_QDRANT=false, reads from AI PostgreSQL description_embedding column.

        Returns:
          truly_new_nodes   — nodes to insert
          truly_new_embs    — their embeddings
          idx_to_existing   — original index -> existing DB node ID
        """
        if settings.use_qdrant:
            return await self._dedup_qdrant(nodes, embeddings, course_id)
        return await self._dedup_pgvector(nodes, embeddings, course_id)

    async def _dedup_qdrant(
        self,
        nodes: list[ExtractedNode],
        embeddings: list[list[float]],
        course_id: int,
    ) -> tuple[list[ExtractedNode], list[list[float]], dict[int, int]]:
        from app.services.qdrant_service import qdrant_service
        existing_records = await qdrant_service.scroll_nodes_for_course(course_id)

        if not existing_records:
            return nodes, embeddings, {}

        # Validate against PG to prevent dangling node references
        exist_ids = [r.id for r in existing_records]
        async with get_ai_conn() as conn:
            rows = await conn.fetch("SELECT id FROM knowledge_nodes WHERE id = ANY($1)", exist_ids)
            valid_ids = {r["id"] for r in rows}

        # Identify dangling nodes to delete them later
        dangling_ids = [rid for rid in exist_ids if rid not in valid_ids]
        if dangling_ids:
            logger.warning("Found %d dangling nodes in Qdrant. Cleaning them up...", len(dangling_ids))
            asyncio.create_task(self.delete_nodes_bulk(dangling_ids))

        existing_records = [r for r in existing_records if r.id in valid_ids]
        if not existing_records:
            return nodes, embeddings, {}

        existing_ids   = [r.id   for r in existing_records]
        existing_names = [r.payload.get("name", "") for r in existing_records]
        existing_embs  = [r.vector for r in existing_records if r.vector is not None]

        if not existing_embs:
            return nodes, embeddings, {}

        return self._compute_dedup(
            nodes=nodes, embeddings=embeddings,
            existing_ids=existing_ids, existing_names=existing_names,
            existing_embs=existing_embs, course_id=course_id,
        )

    async def _dedup_pgvector(
        self,
        nodes: list[ExtractedNode],
        embeddings: list[list[float]],
        course_id: int,
    ) -> tuple[list[ExtractedNode], list[list[float]], dict[int, int]]:
        async with get_ai_conn() as conn:
            existing_rows = await conn.fetch(
                """SELECT id, name, description_embedding
                   FROM knowledge_nodes
                   WHERE course_id=$1 AND description_embedding IS NOT NULL
                   ORDER BY created_at DESC LIMIT 500""",
                course_id,
            )
        if not existing_rows:
            return nodes, embeddings, {}

        existing_ids, existing_names, existing_embs = [], [], []
        for row in existing_rows:
            emb_str = row["description_embedding"]
            emb = ([float(x) for x in emb_str.strip("[]").split(",")]
                   if isinstance(emb_str, str) else list(emb_str))
            existing_ids.append(row["id"])
            existing_names.append(row["name"])
            existing_embs.append(emb)

        return self._compute_dedup(
            nodes=nodes, embeddings=embeddings,
            existing_ids=existing_ids, existing_names=existing_names,
            existing_embs=existing_embs, course_id=course_id,
        )

    def _compute_dedup(
        self,
        nodes: list[ExtractedNode],
        embeddings: list[list[float]],
        existing_ids: list[int],
        existing_names: list[str],
        existing_embs: list[list[float]],
        course_id: int,
    ) -> tuple[list[ExtractedNode], list[list[float]], dict[int, int]]:
        existing_matrix = np.array(existing_embs)
        new_matrix      = np.array(embeddings)
        exist_norms = np.linalg.norm(existing_matrix, axis=1, keepdims=True) + 1e-8
        new_norms   = np.linalg.norm(new_matrix,      axis=1, keepdims=True) + 1e-8
        sims = (new_matrix / new_norms) @ (existing_matrix / exist_norms).T  # (n_new, n_exist)

        truly_new_nodes: list[ExtractedNode]  = []
        truly_new_embs:  list[list[float]]    = []
        idx_to_existing: dict[int, int]       = {}

        for i, (node, emb) in enumerate(zip(nodes, embeddings)):
            best_j   = int(sims[i].argmax())
            best_sim = float(sims[i, best_j])
            exist_id = existing_ids[best_j]

            if best_sim >= DEDUP_HARD_THRESHOLD:
                idx_to_existing[i] = exist_id
                logger.info("[dedup:hard] '%s' -> reuse node %d (sim=%.3f)", node.name, exist_id, best_sim)

            elif best_sim >= DEDUP_SOFT_THRESHOLD:
                asyncio.ensure_future(
                    self._merge_node_description(exist_id, node.description, node.keywords)
                )
                idx_to_existing[i] = exist_id
                logger.info("[dedup:soft] '%s' -> merge into node %d (sim=%.3f)", node.name, exist_id, best_sim)

            else:
                truly_new_nodes.append(node)
                truly_new_embs.append(emb)
                logger.debug("[dedup:new] '%s' (best=%.3f with '%s')", node.name, best_sim, existing_names[best_j])

        return truly_new_nodes, truly_new_embs, idx_to_existing

    async def _intra_run_dedup(
        self,
        nodes: list[ExtractedNode],
        relations: list[ExtractedRelation],
    ) -> tuple[list[ExtractedNode], list[ExtractedRelation]]:
        """
        Collapse near-identical nodes extracted from different batches of the
        SAME document.  This runs BEFORE the cross-document dedup step and
        is the primary fix for node explosion within a single document.

        Algorithm:
          1. Embed all node descriptions.
          2. Compute pairwise cosine similarity.
          3. For each pair with sim > INTRA_RUN_DEDUP_THRESHOLD, merge the
             shorter-description node into the longer-description one.
          4. Re-index relations so they point at the surviving nodes.
        """
        if len(nodes) <= 1:
            return nodes, relations

        # 1. Embed
        desc_texts = [
            f"{n.name_vi or n.name}: {n.description} {', '.join(n.keywords)}"
            for n in nodes
        ]
        embeddings = await _batch_embed(desc_texts)
        emb_matrix = np.array(embeddings)
        norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True) + 1e-8
        normed = emb_matrix / norms

        # 2. Pairwise similarity
        sims = normed @ normed.T

        # 3. Build union-find for merging
        parent = list(range(len(nodes)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            # Keep the node with the longer description as the root
            if len(nodes[ra].description) >= len(nodes[rb].description):
                parent[rb] = ra
            else:
                parent[ra] = rb

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if float(sims[i, j]) >= INTRA_RUN_DEDUP_THRESHOLD:
                    union(i, j)

        # 4. Collect surviving nodes and build old->new index mapping
        root_to_new_idx: dict[int, int] = {}
        surviving_nodes: list[ExtractedNode] = []

        for i in range(len(nodes)):
            root = find(i)
            if root not in root_to_new_idx:
                root_to_new_idx[root] = len(surviving_nodes)
                surviving_nodes.append(nodes[root])

            # Merge description/keywords from non-root nodes into root
            if i != root:
                root_node = surviving_nodes[root_to_new_idx[root]]
                merged_node = nodes[i]
                # Append keywords that aren't already present
                existing_kw = set(root_node.keywords)
                for kw in merged_node.keywords:
                    if kw not in existing_kw:
                        root_node.keywords.append(kw)
                        existing_kw.add(kw)
                # Append description if different
                if merged_node.description and merged_node.description not in root_node.description:
                    root_node.description = (
                        root_node.description + " | " + merged_node.description
                    ).strip(" |")[:800]
                logger.info(
                    "[intra-dedup] merge '%s' -> '%s' (sim=%.3f)",
                    merged_node.name, root_node.name,
                    float(sims[i, root]),
                )

        # Build old->new index mapping for ALL original indices
        old_to_new: dict[int, int] = {}
        for i in range(len(nodes)):
            old_to_new[i] = root_to_new_idx[find(i)]

        # 5. Re-index relations
        surviving_relations: list[ExtractedRelation] = []
        seen_rel_pairs: set[tuple[int, int, str]] = set()
        for r in relations:
            new_src = old_to_new.get(r.source_index)
            new_tgt = old_to_new.get(r.target_index)
            if new_src is None or new_tgt is None or new_src == new_tgt:
                continue
            key = (new_src, new_tgt, r.relation_type)
            if key in seen_rel_pairs:
                continue
            seen_rel_pairs.add(key)
            surviving_relations.append(ExtractedRelation(
                source_index=new_src,
                target_index=new_tgt,
                relation_type=r.relation_type,
                reason=r.reason,
                strength=r.strength,
            ))

        merged_count = len(nodes) - len(surviving_nodes)
        if merged_count > 0:
            logger.info(
                "[intra-dedup] collapsed %d -> %d nodes (%d merged)",
                len(nodes), len(surviving_nodes), merged_count,
            )

        return surviving_nodes, surviving_relations

    async def _merge_node_description(
        self, node_id: int, new_description: str, new_keywords: list[str]
    ) -> None:
        if not new_description:
            return
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT description FROM knowledge_nodes WHERE id=$1", node_id
            )
            existing = (row["description"] or "") if row else ""
            if new_description not in existing:
                merged = (existing + " | " + new_description).strip(" |")[:800]
            else:
                merged = existing
            await conn.execute(
                "UPDATE knowledge_nodes SET description=$1, updated_at=NOW() WHERE id=$2",
                merged, node_id,
            )
        # Update Qdrant payload too
        if settings.use_qdrant:
            from app.services.qdrant_service import qdrant_service
            await qdrant_service.update_node_payload(node_id, {"description": merged})

    def _build_combined_node_list(
        self,
        original_nodes: list[ExtractedNode],
        original_embeddings: list[list[float]],
        idx_to_existing: dict[int, int],
        truly_new_nodes: list[ExtractedNode],
        new_node_ids: list[int],
    ) -> tuple[list[int], list[list[float]]]:
        truly_new_original_indices = [
            i for i in range(len(original_nodes)) if i not in idx_to_existing
        ]
        all_node_ids:        list[int]         = []
        all_node_embeddings: list[list[float]] = []
        new_cursor = 0
        for i, (node, emb) in enumerate(zip(original_nodes, original_embeddings)):
            if i in idx_to_existing:
                all_node_ids.append(idx_to_existing[i])
                all_node_embeddings.append(emb)
            else:
                if new_cursor < len(new_node_ids):
                    all_node_ids.append(new_node_ids[new_cursor])
                    all_node_embeddings.append(emb)
                    new_cursor += 1
        return all_node_ids, all_node_embeddings

    # ─ Step 5: Create nodes in DB + Qdrant ───────────────────────────────────

    async def _create_knowledge_nodes_batch(
        self,
        nodes: list[ExtractedNode],
        embeddings: list[list[float]],
        course_id: int,
        content_id: int,
        content_title: str = "",
    ) -> list[int]:
        if not nodes:
            return []

        node_ids: list[int] = []
        async with get_ai_conn() as conn:
            async with conn.transaction():
                for node, embedding in zip(nodes, embeddings):
                    if settings.use_qdrant:
                        # PG stores metadata only, no embedding column
                        row = await conn.fetchrow(
                            """
                            INSERT INTO knowledge_nodes
                                (course_id, name, name_vi, name_en, description,
                                 level, order_index, source_content_id, source_content_title, auto_generated)
                            VALUES ($1,$2,$3,$4,$5,0,$6,$7,$8,true)
                            RETURNING id
                            """,
                            course_id, node.name, node.name_vi, node.name_en,
                            node.description, node.order_index, content_id, content_title,
                        )
                    else:
                        # Legacy: embedding in PG
                        emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
                        row = await conn.fetchrow(
                            """
                            INSERT INTO knowledge_nodes
                                (course_id, name, name_vi, name_en, description,
                                 description_embedding, level, order_index,
                                 source_content_id, source_content_title, auto_generated)
                            VALUES ($1,$2,$3,$4,$5,$6::vector,0,$7,$8,$9,true)
                            RETURNING id
                            """,
                            course_id, node.name, node.name_vi, node.name_en,
                            node.description, emb_str, node.order_index, content_id, content_title,
                        )
                    node_ids.append(row["id"])

        # Batch upsert to Qdrant
        if settings.use_qdrant:
            from app.services.qdrant_service import qdrant_service
            qdrant_points = [
                {
                    "id":     node_id,
                    "vector": emb,
                    "payload": {
                        "course_id":         course_id,
                        "source_content_id": content_id,
                        "name":              node.name,
                        "name_vi":           node.name_vi or "",
                        "name_en":           node.name_en or "",
                        "description":       node.description or "",
                        "level":             0,
                        "auto_generated":    True,
                    },
                }
                for node_id, node, emb in zip(node_ids, nodes, embeddings)
            ]
            await qdrant_service.upsert_nodes_batch(qdrant_points)

        logger.info("Created %d knowledge nodes", len(node_ids))
        return node_ids

    # ─ Step 6: LLM relations ──────────────────────────────────────────────────

    async def _create_llm_relations(
        self,
        relations: list[ExtractedRelation],
        node_ids: list[int],
        course_id: int,
    ) -> None:
        if not relations:
            return
        async with get_ai_conn() as conn:
            async with conn.transaction():
                for rel in relations:
                    if rel.source_index >= len(node_ids) or rel.target_index >= len(node_ids):
                        continue
                    await conn.execute(
                        """
                        INSERT INTO knowledge_node_relations
                            (course_id, source_node_id, target_node_id,
                             relation_type, strength, auto_generated)
                        VALUES ($1,$2,$3,$4,$5,true)
                        ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE
                            SET strength = GREATEST(knowledge_node_relations.strength, EXCLUDED.strength)
                        """,
                        course_id,
                        node_ids[rel.source_index],
                        node_ids[rel.target_index],
                        rel.relation_type,
                        round(rel.strength, 3),
                    )

    # ─ Step 7: Chunk + embed + assign ────────────────────────────────────────

    async def _chunk_and_store(
        self,
        file_bytes: bytes,
        file_type: str,
        structured_chunks: list[DocumentChunk],
        content_id: int,
        course_id: int,
        node_ids: list[int],
        node_embeddings: list[list[float]],
        language: str,
    ) -> int:
        if not structured_chunks:
            return 0

        chunk_texts       = [c.text for c in structured_chunks]
        chunk_embeddings  = await _batch_embed(chunk_texts)

        # Vectorized chunk->node assignment
        node_emb_matrix  = np.array(node_embeddings)
        chunk_emb_matrix = np.array(chunk_embeddings)
        node_norms  = np.linalg.norm(node_emb_matrix,  axis=1, keepdims=True) + 1e-8
        chunk_norms = np.linalg.norm(chunk_emb_matrix, axis=1, keepdims=True) + 1e-8
        sims = (chunk_emb_matrix / chunk_norms) @ (node_emb_matrix / node_norms).T
        best_node_local  = sims.argmax(axis=1)
        assigned_node_ids = [node_ids[i] for i in best_node_local.tolist()]

        stored = await self._batch_insert_chunks(
            content_id=content_id, course_id=course_id,
            chunks=structured_chunks, embeddings=chunk_embeddings,
            assigned_node_ids=assigned_node_ids,
        )
        logger.info("Stored %d chunks for content_id=%d", stored, content_id)

        # ── Build parent chunks for retrieval-time hydration ──────────
        # Parent rows live in PG only — they're never embedded or indexed
        # in Qdrant. After ANN search returns child hits, RAGService
        # `hydrate_parents` swaps the child text for the wider parent
        # passage so the LLM gets coherent context.
        if settings.use_hierarchical_chunks and stored:
            try:
                await self._build_and_link_parents(
                    content_id=content_id, course_id=course_id,
                    chunks=structured_chunks,
                )
            except Exception as exc:
                logger.warning("Parent linking failed content=%d: %s", content_id, exc)
        
        return stored

    async def _build_and_link_parents(
        self,
        content_id: int,
        course_id: int,
        chunks: list[DocumentChunk],
    ) -> None:
        """
        Group the just-stored children into parent windows, INSERT each
        parent row, then UPDATE every child's `parent_chunk_id` to point
        at its parent. We only need to look up child IDs by chunk_hash
        (same hash function as `_batch_insert_chunks_qdrant`).
        """
        from app.services.chunker import build_hierarchical_chunks
        from app.services.rag_service import _sanitize

        pairs = build_hierarchical_chunks(
            chunks, parent_max_chars=settings.parent_chunk_max_chars,
        )
        if not pairs:
            return

        # Compute child hashes once
        def _child_hash(chunk: DocumentChunk) -> str:
            text = _sanitize(chunk.text)
            return hashlib.sha256(f"{content_id}:{chunk.index}:{text}".encode()).hexdigest()

        async with get_ai_conn() as conn:
            # Resolve child IDs
            child_hashes = [_child_hash(c) for pair in pairs for c in pair.children]
            rows = await conn.fetch(
                "SELECT id, chunk_hash FROM document_chunks "
                "WHERE chunk_hash = ANY($1) AND chunk_level = 'child'",
                child_hashes,
            )
            hash_to_id = {r["chunk_hash"]: r["id"] for r in rows}

            parents_made = 0
            updates: list[tuple[int, int]] = []

            for parent_idx, pair in enumerate(pairs):
                # Skip when the parent would just duplicate the only child.
                child_dicts = [(c, _child_hash(c)) for c in pair.children]
                child_dicts = [(c, h) for c, h in child_dicts if h in hash_to_id]
                if not child_dicts:
                    continue

                parent_text = _sanitize(pair.parent_text)
                if len(child_dicts) == 1 and child_dicts[0][0].text.strip() == parent_text.strip():
                    continue

                parent_hash = hashlib.sha256(
                    f"parent:{content_id}:{parent_idx}:{len(parent_text)}:{parent_text[:200]}".encode()
                ).hexdigest()

                row = await conn.fetchrow(
                    """
                    INSERT INTO document_chunks
                        (content_id, course_id, chunk_text, chunk_index,
                         chunk_hash, source_type, page_number,
                         start_time_sec, end_time_sec, language, status,
                         embedding_model, chunk_level, parent_chunk_id)
                    VALUES ($1,$2,$3,$4,$5,'document',$6,$7,$8,$9,'ready',
                            $10,'parent',NULL)
                    ON CONFLICT (chunk_hash) DO UPDATE
                        SET chunk_text = EXCLUDED.chunk_text,
                            status     = 'ready'
                    RETURNING id
                    """,
                    content_id, course_id, parent_text,
                    -(parent_idx + 1),  # negative index to avoid colliding with child indices
                    parent_hash,
                    pair.parent_page_number,
                    pair.parent_start_time_sec, pair.parent_end_time_sec,
                    pair.parent_language,
                    settings.embedding_model,
                )
                parent_id = row["id"]
                parents_made += 1
                for _, child_hash in child_dicts:
                    cid = hash_to_id.get(child_hash)
                    if cid is not None:
                        updates.append((parent_id, cid))

            if updates:
                async with conn.transaction():
                    await conn.executemany(
                        "UPDATE document_chunks SET parent_chunk_id = $1 WHERE id = $2",
                        updates,
                    )
            logger.info(
                "Hierarchical parents: content=%d parents=%d links=%d",
                content_id, parents_made, len(updates),
            )

    async def _batch_insert_chunks(
        self,
        content_id: int,
        course_id: int,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        assigned_node_ids: list[int],
    ) -> int:
        from app.services.rag_service import _sanitize

        if settings.use_qdrant:
            return await self._batch_insert_chunks_qdrant(
                content_id=content_id, course_id=course_id,
                chunks=chunks, embeddings=embeddings,
                assigned_node_ids=assigned_node_ids,
            )

        # ── Legacy pgvector path ──────────────────────────────────────────────
        return await self._batch_insert_chunks_pgvector(
            content_id=content_id, course_id=course_id,
            chunks=chunks, embeddings=embeddings,
            assigned_node_ids=assigned_node_ids,
        )

    async def _batch_insert_chunks_qdrant(
        self,
        content_id: int,
        course_id: int,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        assigned_node_ids: list[int],
    ) -> int:
        from app.services.rag_service import _sanitize, RAGService
        from app.services.qdrant_service import qdrant_service

        valid_chunks, valid_embs, valid_node_ids = [], [], []
        hashes = []
        for chunk, emb, node_id in zip(chunks, embeddings, assigned_node_ids):
            text = _sanitize(chunk.text)
            if not text.strip():
                continue
            h = hashlib.sha256(f"{content_id}:{chunk.index}:{text}".encode()).hexdigest()
            valid_chunks.append((chunk, text, node_id))
            valid_embs.append(emb)
            hashes.append(h)

        if not valid_chunks:
            return 0

        # 1. Bulk insert metadata into PG
        sql = """
            INSERT INTO document_chunks
                (content_id, course_id, node_id, chunk_text, chunk_index,
                 chunk_hash, source_type, page_number,
                 start_time_sec, end_time_sec, language, status, embedding_model)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'ready',$12)
            ON CONFLICT (chunk_hash) DO UPDATE
                SET node_id=EXCLUDED.node_id, status='ready',
                    embedding_model=EXCLUDED.embedding_model
            RETURNING id, chunk_hash
        """
        records = [
            (
                content_id, course_id, node_id,
                text, chunk.index, h,
                chunk.source_type, chunk.page_number,
                chunk.start_time_sec, chunk.end_time_sec,
                chunk.language, settings.embedding_model,
            )
            for (chunk, text, node_id), h in zip(valid_chunks, hashes)
        ]

        async with get_ai_conn() as conn:
            async with conn.transaction():
                await conn.executemany(sql, records)
            rows = await conn.fetch(
                "SELECT id, chunk_hash FROM document_chunks WHERE chunk_hash = ANY($1)", hashes
            )

        hash_to_id = {r["chunk_hash"]: r["id"] for r in rows}

        # 2. Batch upsert to Qdrant
        qdrant_points = []
        for (chunk, text, node_id), emb, h in zip(valid_chunks, valid_embs, hashes):
            chunk_id = hash_to_id.get(h)
            if chunk_id is None:
                continue
            qdrant_points.append({
                "id":     chunk_id,
                "vector": emb,
                "payload": {
                    "chunk_text":    text,
                    "chunk_index":   chunk.index,
                    "chunk_hash":    h,
                    "content_id":    content_id,
                    "course_id":     course_id,
                    "node_id":       node_id,
                    "source_type":   chunk.source_type,
                    "language":      chunk.language,
                    "status":        "ready",
                    **({"page_number":    chunk.page_number}    if chunk.page_number    is not None else {}),
                    **({"start_time_sec": chunk.start_time_sec} if chunk.start_time_sec is not None else {}),
                    **({"end_time_sec":   chunk.end_time_sec}   if chunk.end_time_sec   is not None else {}),
                },
            })

        await qdrant_service.upsert_chunks_batch(qdrant_points)
        return len(qdrant_points)

    async def _batch_insert_chunks_pgvector(
        self,
        content_id: int,
        course_id: int,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        assigned_node_ids: list[int],
    ) -> int:
        from app.services.rag_service import _sanitize
        stored = 0
        async with get_ai_conn() as conn:
            async with conn.transaction():
                for chunk, embedding, node_id in zip(chunks, embeddings, assigned_node_ids):
                    chunk_text = _sanitize(chunk.text)
                    if not chunk_text.strip():
                        continue
                    chunk_hash = hashlib.sha256(
                        f"{content_id}:{chunk.index}:{chunk_text}".encode()
                    ).hexdigest()
                    emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
                    await conn.execute(
                        """
                        INSERT INTO document_chunks
                            (content_id, course_id, node_id, chunk_text, chunk_index,
                             chunk_hash, embedding, source_type, page_number,
                             start_time_sec, end_time_sec, language, status)
                        VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,$9,$10,$11,$12,'ready')
                        ON CONFLICT (chunk_hash) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            node_id   = EXCLUDED.node_id,
                            status    = 'ready'
                        """,
                        content_id, course_id, node_id, chunk_text, chunk.index,
                        chunk_hash, emb_str, chunk.source_type, chunk.page_number,
                        chunk.start_time_sec, chunk.end_time_sec, chunk.language,
                    )
                    stored += 1
        return stored

    # ─ Step 8: Graph edges ────────────────────────────────────────────────────

    async def _build_graph_edges(
        self,
        new_node_ids: list[int],
        new_node_embeddings: list[list[float]],
        course_id: int,
    ) -> None:
        if not new_node_ids:
            return

        if settings.use_qdrant:
            await self._build_graph_edges_qdrant(
                new_node_ids, new_node_embeddings, course_id
            )
        else:
            await self._build_graph_edges_pgvector(
                new_node_ids, new_node_embeddings, course_id
            )

    async def _sync_to_neo4j(
        self,
        node_ids: list[int],
        nodes: list,                       # list[ExtractedNode]
        node_embeddings: list[list[float]],
        course_id: int,
        content_id: int,
        llm_relations: list,               # list[ExtractedRelation]
    ) -> None:
        """
        Sync newly created nodes + edges to Neo4j.
        Then trigger cross-course smart linking.
        """
        from app.services.neo4j_service import neo4j_service, RELATIONSHIP_TYPES
        from app.services.graph_linker import (
            NodeInfo, link_intra_course, link_cross_course
        )

        # 1. Upsert nodes to Neo4j
        neo4j_nodes = [
            {
                "id":               node_id,
                "course_id":        course_id,
                "name":             node.name,
                "name_vi":          node.name_vi or "",
                "name_en":          node.name_en or "",
                "description":      node.description or "",
                "auto_generated":   True,
                "source_content_id": content_id,
            }
            for node_id, node in zip(node_ids, nodes)
        ]
        await neo4j_service.upsert_nodes_batch(neo4j_nodes)

        # 2. Build NodeInfo list for linker
        new_node_infos = [
            NodeInfo(
                id=nid, course_id=course_id,
                name=node.name,
                description=node.description or "",
                embedding=emb,
            )
            for nid, node, emb in zip(node_ids, nodes, node_embeddings)
        ]

        # 3. Intra-course edges (LLM relations + similarity-based)
        # Get existing nodes for this course from Qdrant to compare against
        existing_node_infos = await self._fetch_existing_node_infos(
            course_id=course_id,
            exclude_ids=set(node_ids),
        )
        intra_count = await link_intra_course(
            new_nodes=new_node_infos,
            existing_nodes=existing_node_infos,
            course_id=course_id,
            llm_relations=[
                {
                    "source_index": r.source_index,
                    "target_index": r.target_index,
                    "relation_type": r.relation_type,
                    "strength": r.strength,
                    "reason": r.reason,
                }
                for r in llm_relations
            ],
        )
        logger.info("Neo4j intra-course edges created: %d", intra_count)

        # 4. Cross-course smart linking (async, non-blocking)
        asyncio.create_task(
            self._cross_course_linking_task(new_node_infos)
        )

    async def _cross_course_linking_task(
        self, new_node_infos: list
    ) -> None:
        """Wrapped in task so it doesn't block the main indexing pipeline."""
        try:
            from app.services.graph_linker import link_cross_course
            cross_count = await link_cross_course(
                new_nodes=new_node_infos,
                new_course_id=new_node_infos[0].course_id if new_node_infos else 0,
            )
            logger.info("Neo4j cross-course edges created: %d", cross_count)
        except Exception as exc:
            logger.warning("Cross-course linking failed (non-fatal): %s", exc)

    async def _fetch_existing_node_infos(
        self,
        course_id: int,
        exclude_ids: set[int],
    ) -> list:
        """Fetch existing nodes for this course from Qdrant for intra-course comparison."""
        from app.services.neo4j_service import neo4j_service
        from app.services.qdrant_service import qdrant_service
        from app.services.graph_linker import NodeInfo

        try:
            records = await qdrant_service.scroll_nodes_for_course(course_id)
            if not records:
                return []

            # Validate against PG to prevent dangling node references
            exist_ids = [r.id for r in records]
            async with get_ai_conn() as conn:
                rows = await conn.fetch("SELECT id FROM knowledge_nodes WHERE id = ANY($1)", exist_ids)
                valid_ids = {r["id"] for r in rows}

            # Identify dangling nodes to delete them later
            dangling_ids = [rid for rid in exist_ids if rid not in valid_ids]
            if dangling_ids:
                logger.warning("Found %d dangling nodes in Qdrant. Cleaning them up...", len(dangling_ids))
                asyncio.create_task(self.delete_nodes_bulk(dangling_ids))

            result = []
            for r in records:
                if int(r.id) in exclude_ids:
                    continue
                if r.id not in valid_ids:
                    continue
                if r.vector is None:
                    continue
                payload = r.payload or {}
                result.append(NodeInfo(
                    id=int(r.id),
                    course_id=course_id,
                    name=payload.get("name", ""),
                    description=payload.get("description", ""),
                    embedding=r.vector,
                ))
            return result
        except Exception as exc:
            logger.warning("_fetch_existing_node_infos failed: %s", exc)
            return []

    async def _build_graph_edges_qdrant(
        self,
        new_node_ids: list[int],
        new_node_embeddings: list[list[float]],
        course_id: int,
    ) -> None:
        from app.services.qdrant_service import qdrant_service

        # Fetch all existing nodes for this course from Qdrant
        existing_records = await qdrant_service.scroll_nodes_for_course(course_id)
        if existing_records:
            # Validate against PG to prevent dangling node references
            exist_ids = [r.id for r in existing_records]
            async with get_ai_conn() as conn:
                rows = await conn.fetch("SELECT id FROM knowledge_nodes WHERE id = ANY($1)", exist_ids)
                valid_ids = {r["id"] for r in rows}

            # Identify dangling nodes to delete them later
            dangling_ids = [rid for rid in exist_ids if rid not in valid_ids]
            if dangling_ids:
                logger.warning("Found %d dangling nodes in Qdrant. Cleaning them up...", len(dangling_ids))
                asyncio.create_task(self.delete_nodes_bulk(dangling_ids))

            existing_records = [r for r in existing_records if r.id in valid_ids]

        existing_ids  = [r.id for r in existing_records if r.id not in new_node_ids]
        existing_embs = [r.vector for r in existing_records
                         if r.id not in new_node_ids and r.vector is not None]
        existing_ids  = existing_ids[:MAX_EXISTING_NODES_FOR_GRAPH]
        existing_embs = existing_embs[:MAX_EXISTING_NODES_FOR_GRAPH]

        await self._create_similarity_edges(
            new_node_ids=new_node_ids, new_node_embeddings=new_node_embeddings,
            existing_ids=existing_ids, existing_embs=existing_embs,
            course_id=course_id,
        )

    async def _build_graph_edges_pgvector(
        self,
        new_node_ids: list[int],
        new_node_embeddings: list[list[float]],
        course_id: int,
    ) -> None:
        async with get_ai_conn() as conn:
            existing_rows = await conn.fetch(
                """SELECT id, description_embedding
                   FROM knowledge_nodes
                   WHERE course_id=$1 AND id != ALL($2::bigint[])
                     AND description_embedding IS NOT NULL
                   ORDER BY created_at DESC LIMIT $3""",
                course_id, new_node_ids, MAX_EXISTING_NODES_FOR_GRAPH,
            )

        existing_ids, existing_embs = [], []
        for r in existing_rows:
            emb_str = r["description_embedding"]
            emb = ([float(x) for x in emb_str.strip("[]").split(",")]
                   if isinstance(emb_str, str) else list(emb_str))
            existing_ids.append(r["id"])
            existing_embs.append(emb)

        await self._create_similarity_edges(
            new_node_ids=new_node_ids, new_node_embeddings=new_node_embeddings,
            existing_ids=existing_ids, existing_embs=existing_embs,
            course_id=course_id,
        )

    async def _create_similarity_edges(
        self,
        new_node_ids: list[int],
        new_node_embeddings: list[list[float]],
        existing_ids: list[int],
        existing_embs: list[list[float]],
        course_id: int,
    ) -> None:
        new_matrix = np.array(new_node_embeddings)
        new_norms  = np.linalg.norm(new_matrix, axis=1, keepdims=True) + 1e-8
        new_norm   = new_matrix / new_norms

        edges: list[tuple[int, int, float]] = []

        if existing_embs:
            exist_matrix = np.array(existing_embs)
            exist_norms  = np.linalg.norm(exist_matrix, axis=1, keepdims=True) + 1e-8
            cross_sims   = new_norm @ (exist_matrix / exist_norms).T
            for i, new_id in enumerate(new_node_ids):
                for j, exist_id in enumerate(existing_ids):
                    sim = float(cross_sims[i, j])
                    if sim >= RELATION_SIMILARITY_THRESHOLD:
                        edges.append((new_id, exist_id, sim))

        intra_sims = new_norm @ new_norm.T
        for i in range(len(new_node_ids)):
            for j in range(i + 1, len(new_node_ids)):
                sim = float(intra_sims[i, j])
                if sim >= RELATION_SIMILARITY_THRESHOLD:
                    edges.append((new_node_ids[i], new_node_ids[j], sim))

        if not edges:
            return

        from app.services.neo4j_service import EQUIVALENT_THRESHOLD

        async with get_ai_conn() as conn:
            async with conn.transaction():
                for src, tgt, strength in edges:
                    rel_type = 'equivalent' if strength >= EQUIVALENT_THRESHOLD else 'related'
                    await conn.execute(
                        """
                        INSERT INTO knowledge_node_relations
                            (course_id, source_node_id, target_node_id,
                             relation_type, strength, auto_generated)
                        VALUES ($1,$2,$3,$4,$5,true)
                        ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE
                            SET strength = GREATEST(knowledge_node_relations.strength, EXCLUDED.strength)
                        """,
                        course_id, src, tgt, rel_type, round(strength, 3),
                    )
        logger.info("Created/updated %d graph edges for course_id=%d", len(edges), course_id)

    # ─ Utility ────────────────────────────────────────────────────────────────

    async def _cleanup_orphaned_nodes(self, node_ids: list[int], course_id: int) -> list[int]:
        """
        Identify and delete nodes that have 0 chunks assigned to them.
        Optimized to use batch queries.
        """
        if not node_ids:
            return []

        async with get_ai_conn() as conn:
            # Count chunks for these nodes
            rows = await conn.fetch(
                """
                SELECT kn.id, COUNT(dc.id) as chunk_count
                FROM knowledge_nodes kn
                LEFT JOIN document_chunks dc ON dc.node_id = kn.id
                WHERE kn.id = ANY($1)
                GROUP BY kn.id
                """,
                node_ids
            )
            
            orphaned_ids = [r["id"] for r in rows if r["chunk_count"] == 0]
            
            if orphaned_ids:
                logger.info(f"Grounding Guard: Deleting {len(orphaned_ids)} orphaned nodes in course {course_id}")
                await self.delete_nodes_bulk(orphaned_ids)
            
            return orphaned_ids

    async def delete_nodes_bulk(self, node_ids: list[int]) -> None:
        """
        Delete nodes from PG, Qdrant, and Neo4j in bulk.
        """
        if not node_ids:
            return

        # 1. PostgreSQL deletion (Cascades to relations, progress, etc.)
        async with get_ai_conn() as conn:
            await conn.execute("DELETE FROM knowledge_nodes WHERE id = ANY($1)", node_ids)
            
        # 2. Qdrant deletion
        if settings.use_qdrant:
            try:
                from app.services.qdrant_service import qdrant_service
                from qdrant_client.http.models import PointIdsList
                client = qdrant_service._get_client()
                await client.delete(
                    collection_name="knowledge_nodes",
                    points_selector=PointIdsList(points=node_ids),
                    wait=True
                )
            except Exception as e:
                logger.error(f"Failed to delete nodes from Qdrant: {e}")

        # 3. Neo4j deletion
        if settings.neo4j_enabled:
            try:
                from app.services.neo4j_service import neo4j_service
                driver = neo4j_service._get_driver()
                async with driver.session() as s:
                    await s.run(
                        "UNWIND $ids AS id MATCH (n:KnowledgeNode {id: id}) DETACH DELETE n",
                        ids=node_ids
                    )
            except Exception as e:
                logger.error(f"Failed to delete nodes from Neo4j: {e}")

    async def delete_content_data(self, content_id: int) -> None:
        """
        Delete all chunks and nodes created by a specific content ID from PG, Qdrant, and Neo4j.
        """
        logger.info(f"Deleting content data for content_id={content_id}")
        
        # 1. Get all nodes created by this content from PG
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                "SELECT id FROM knowledge_nodes WHERE source_content_id = $1",
                content_id
            )
            node_ids = [r["id"] for r in rows]
            
        # 2. Delete chunks for content (handles PG and Qdrant chunks)
        from app.services.rag_service import rag_service
        await rag_service.delete_chunks_for_content(content_id)
        
        # 3. Delete nodes (handles PG, Qdrant, and Neo4j nodes)
        if node_ids:
            await self.delete_nodes_bulk(node_ids)

    async def delete_course_data(self, course_id: int) -> None:
        """
        Delete all chunks and nodes belonging to a course from PG, Qdrant, and Neo4j.
        """
        logger.info(f"Deleting course data for course_id={course_id}")
        
        # 1. Delete Qdrant vectors
        if settings.use_qdrant:
            try:
                from app.services.qdrant_service import qdrant_service
                await qdrant_service.delete_by_course(course_id)
            except Exception as e:
                logger.error(f"Failed to delete course data from Qdrant: {e}")
                
        # 2. Delete Neo4j nodes/edges
        if settings.neo4j_enabled:
            try:
                from app.services.neo4j_service import neo4j_service
                driver = neo4j_service._get_driver()
                async with driver.session() as s:
                    await s.run(
                        "MATCH (n:KnowledgeNode {course_id: $course_id}) DETACH DELETE n",
                        course_id=course_id
                    )
            except Exception as e:
                logger.error(f"Failed to delete course data from Neo4j: {e}")
                
        # 3. PostgreSQL cleanup (deletes chunks, nodes, status, jobs, sessions)
        async with get_ai_conn() as conn:
            async with conn.transaction():
                # Delete chunks first because they reference nodes (with SET NULL, but let's delete them anyway)
                await conn.execute("DELETE FROM document_chunks WHERE course_id = $1", course_id)
                await conn.execute("DELETE FROM knowledge_nodes WHERE course_id = $1", course_id)
                await conn.execute("DELETE FROM content_index_status WHERE course_id = $1", course_id)
                await conn.execute("DELETE FROM embedding_reindex_jobs WHERE course_id = $1", course_id)
                await conn.execute("DELETE FROM agent_sessions WHERE course_id = $1", course_id)

    # ─ Utility ────────────────────────────────────────────────────────────────
    async def _update_content_status(
        self, content_id: int, status: str, error_msg: Optional[str] = None,
    ) -> None:
        # Persist to AI DB
        try:
            async with get_ai_conn() as conn:
                await conn.execute(
                    """INSERT INTO content_index_status (content_id, course_id, status, error, updated_at)
                       VALUES ($1, 0, $2, $3, NOW())
                       ON CONFLICT (content_id) DO UPDATE
                           SET status = $2, error = $3, updated_at = NOW()""",
                    content_id, status, error_msg,
                )
        except Exception as e:
            logger.error("Failed to update content_index_status: %s", e)

        # Publish Kafka event to LMS
        try:
            from app.worker.kafka_producer import publish_status_event
            await publish_status_event(content_id, status, error=error_msg or "")
            if error_msg:
                logger.warning("content_id=%d -> %s: %s", content_id, status, error_msg)
        except Exception as e:
            logger.error(f"Failed to publish to kafka: {e}")

    async def _get_vlm_ready_url(self, url: str) -> str:
        """
        Helper to convert a relative path (e.g. /files/image/...) into a full URL
        suitable for VLM fetch. It tries to get a presigned URL first, and falls back
        to the public serve endpoint if that fails.
        """
        # If it's already a full URL, return it
        if url.startswith("http"):
            return url

        # Normalize relative path
        path_key = url.lstrip("/")
        
        # CRITICAL: Strip 'files/' prefix if present. 
        # In this system, '/files/' is a routing prefix, but MinIO keys are like 'image/...'
        if path_key.startswith("files/"):
            path_key = path_key[len("files/"):]

        presigned = _get_minio_presigned_url(path_key)
        if presigned:
            return presigned

        # Fallback to full public URL if presigned fails
        from app.core.config import get_settings
        settings = get_settings()
        lms_base = settings.lms_service_url.rstrip("/")
        
        # Use the internal path_key (e.g. image/...) with the public serve route
        return f"{lms_base}/api/v1/files/serve/{path_key}"

auto_index_service = AutoIndexService()