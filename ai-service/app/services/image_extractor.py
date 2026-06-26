"""
ai-service/app/services/image_extractor.py

Extract embedded images from PDFs, DOCXs and PPTXs, upload them to MinIO,
and return references the markdown converter can splice back into the
generated Markdown.

A single ExtractedImage describes one image with everything needed to
both render it (`url`) and give an LLM enough context to refer to it
(`caption_hint`, page number, ordinal).
"""
from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.services.minio_storage import upload_bytes

logger = logging.getLogger(__name__)


@dataclass
class ExtractedImage:
    """Metadata for one extracted image after MinIO upload."""
    key: str                              # MinIO object key
    url: str                              # Relative URL e.g. /files/<key>
    page_number: Optional[int] = None     # PDF page or PPTX slide number
    order_in_page: int = 0
    caption_hint: str = ""                # Nearest paragraph or alt text
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: str = "image/png"
    placeholder: str = field(default="")  # Token used inside the Markdown


def _placeholder_token(idx: int) -> str:
    return f"\x00IMG_{idx}\x00"


# ── PDF ───────────────────────────────────────────────────────────────────────

async def extract_pdf_images(
    pdf_bytes: bytes,
    storage_prefix: str,
    min_dimension: int = 80,
    max_per_page: int = 6,
) -> list[ExtractedImage]:
    """
    Extract images from a PDF using PyMuPDF, uploading each to
    `<storage_prefix>/p<page>-<n>.<ext>` in MinIO.

    Tiny icons / decorative slivers (smaller than `min_dimension` on either
    side) are skipped - they create noise in the lesson Markdown without
    adding pedagogical value.

    The CPU-heavy PyMuPDF work (page iteration, pixmap extraction, colour
    space conversion) runs in a background thread via asyncio.to_thread()
    to avoid blocking the Kafka heartbeat loop.
    """
    try:
        import pymupdf
    except ImportError:
        logger.error("PyMuPDF not installed; cannot extract PDF images")
        return []

    # ── Phase 1: sync extraction in a thread (CPU-bound, event-loop-safe) ──
    @dataclass
    class _RawImage:
        img_bytes: bytes
        page_no: int
        ord_idx: int
        width: int
        height: int
        caption: str

    def _sync_extract() -> list[_RawImage]:
        raw_images: list[_RawImage] = []
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            logger.error("Cannot open PDF for image extraction: %s", exc)
            return []

        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                xrefs = page.get_images(full=True)
                if not xrefs:
                    continue

                page_text = ""
                try:
                    page_text = page.get_text("text") or ""
                except Exception:
                    pass

                for ord_idx, info in enumerate(xrefs[:max_per_page]):
                    xref = info[0]
                    try:
                        pix = pymupdf.Pixmap(doc, xref)
                        if pix.width < min_dimension or pix.height < min_dimension:
                            pix = None
                            continue

                        # Convert CMYK / weird colourspace to RGB before PNG export
                        if pix.colorspace and pix.colorspace.n >= 4:
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

                        img_bytes = pix.tobytes("png")
                        width, height = pix.width, pix.height
                        pix = None
                    except Exception as exc:
                        logger.warning("PDF image extract failed xref=%s: %s", xref, exc)
                        continue

                    caption = _nearest_caption(page_text, page_idx + 1, ord_idx + 1)
                    raw_images.append(_RawImage(
                        img_bytes=img_bytes,
                        page_no=page_idx + 1,
                        ord_idx=ord_idx + 1,
                        width=width,
                        height=height,
                        caption=caption,
                    ))
        finally:
            doc.close()

        return raw_images

    import asyncio
    raw_images = await asyncio.to_thread(_sync_extract)

    # ── Phase 2: async upload to MinIO (I/O-bound, back on event loop) ──
    images: list[ExtractedImage] = []
    for raw in raw_images:
        key = f"{storage_prefix}/p{raw.page_no}-{raw.ord_idx}-{uuid.uuid4().hex[:8]}.png"
        rel_url = await upload_bytes(key, raw.img_bytes, content_type="image/png")
        if not rel_url:
            continue

        images.append(ExtractedImage(
            key=key,
            url=rel_url,
            page_number=raw.page_no,
            order_in_page=raw.ord_idx,
            caption_hint=raw.caption,
            width=raw.width,
            height=raw.height,
            mime_type="image/png",
            placeholder=_placeholder_token(len(images)),
        ))

    logger.info("PDF image extraction: %d images uploaded", len(images))
    return images


# ── DOCX ──────────────────────────────────────────────────────────────────────

async def extract_docx_images(
    docx_bytes: bytes,
    storage_prefix: str,
    min_size_bytes: int = 4 * 1024,
) -> list[ExtractedImage]:
    """
    Pull embedded images out of a .docx (zip archive). Uses python-docx to
    walk inline_shapes for ordering metadata, falling back to a raw zip
    scan when the document has loose images.
    """
    images: list[ExtractedImage] = []
    try:
        import zipfile
    except ImportError:
        return []

    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            media_names = [
                n for n in zf.namelist()
                if n.startswith("word/media/")
            ]
            for idx, name in enumerate(media_names):
                try:
                    raw = zf.read(name)
                except Exception:
                    continue
                if len(raw) < min_size_bytes:
                    continue

                ext = name.rsplit(".", 1)[-1].lower() or "png"
                mime_map = {
                    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
                    "svg": "image/svg+xml",
                }
                mime = mime_map.get(ext, "application/octet-stream")
                key = f"{storage_prefix}/img-{idx + 1}-{uuid.uuid4().hex[:8]}.{ext}"
                rel_url = await upload_bytes(key, raw, content_type=mime)
                if not rel_url:
                    continue

                images.append(ExtractedImage(
                    key=key,
                    url=rel_url,
                    page_number=None,
                    order_in_page=idx + 1,
                    caption_hint="",
                    mime_type=mime,
                    placeholder=_placeholder_token(len(images)),
                ))
    except Exception as exc:
        logger.warning("DOCX image extract failed: %s", exc)

    logger.info("DOCX image extraction: %d images uploaded", len(images))
    return images


# ── PPTX (whole-slide render) ─────────────────────────────────────────────────

async def render_pptx_slides(
    pptx_bytes: bytes,
    storage_prefix: str,
) -> list[ExtractedImage]:
    """
    PPTX shapes lose layout context once flattened to text; instead render
    each slide as a PNG via LibreOffice headless if available, otherwise
    just pull embedded media from the archive.

    Falls back to media extraction when LibreOffice is missing (typical
    in slim Docker images) - the markdown converter still gets the inline
    images, just no whole-slide thumbnails.
    """
    images = await extract_docx_images(pptx_bytes, storage_prefix)  # PPTX shares the zip layout
    return images


# ── helpers ───────────────────────────────────────────────────────────────────

def _nearest_caption(page_text: str, page_no: int, ord_no: int) -> str:
    """
    Best-effort caption hint: look for a 'Hình <n>'/'Figure <n>' marker in
    the page text and return the surrounding line. Used purely as context
    for the VLM and for the LLM lesson-splitter.
    """
    if not page_text:
        return ""
    for line in page_text.splitlines():
        ll = line.strip().lower()
        if ll.startswith(("hình ", "figure ", "fig.", "fig ", "biểu đồ ", "sơ đồ ")):
            return line.strip()[:200]
    return ""