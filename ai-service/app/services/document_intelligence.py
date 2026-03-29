from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Thresholds 
SCAN_TEXT_DENSITY_THRESHOLD = 0.3
IMAGE_AREA_RATIO_THRESHOLD = 0.10
OCR_DPI = 200
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


# Result dataclasses 

@dataclass
class PageIntelligence:
    """Kết quả phân tích một trang."""
    page_num: int
    raw_text: str
    ocr_text: str = ""
    tables_md: list[str] = field(default_factory=list)
    image_descriptions: list[str] = field(default_factory=list)
    is_scanned: bool = False

    @property
    def full_text(self) -> str:
        """Gộp tất cả nguồn text thành nội dung cuối cùng."""
        parts: list[str] = []

        # Ưu tiên OCR nếu trang là scan
        text = (self.ocr_text if self.is_scanned and self.ocr_text else self.raw_text).strip()
        if text:
            parts.append(text)

        # Thêm bảng
        for t in self.tables_md:
            if t.strip():
                parts.append(t.strip())

        # Thêm mô tả ảnh
        for desc in self.image_descriptions:
            if desc.strip():
                parts.append(f"[Hình ảnh/Biểu đồ]: {desc.strip()}")

        return "\n\n".join(parts)


# Core functions 

def is_page_scanned(page, raw_text: str) -> bool:
    """
    Phát hiện trang scan dựa trên mật độ text.
    Trang scan thường có rất ít ký tự text có thể trích xuất.

    Công thức: chars / (area / 1000) < ngưỡng
    Ví dụ: trang 595x842pt (~501,590 area) → cần > 150 chars để không phải scan.
    """
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return False
    density = len(raw_text.strip()) / (page_area / 1000)
    return density < SCAN_TEXT_DENSITY_THRESHOLD


def ocr_page(page, dpi: int = OCR_DPI) -> str:
    """
    OCR một trang PyMuPDF bằng pytesseract.
    Hỗ trợ tiếng Việt + tiếng Anh (vie+eng).

    Yêu cầu hệ thống: tesseract-ocr, tesseract-ocr-vie
    Cài: apt-get install tesseract-ocr tesseract-ocr-vie
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.debug("pytesseract/Pillow not available, skipping OCR")
        return ""

    try:
        # Render trang thành ảnh
        mat = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [mat.width, mat.height], mat.samples)

        # OCR với config tốt nhất cho document layout
        config = "--oem 3 --psm 3 -l vie+eng"
        text = pytesseract.image_to_string(img, config=config)
        return _clean_ocr_text(text)

    except Exception as e:
        logger.warning(f"OCR failed on page: {e}")
        return ""


def extract_tables_from_page(pdf_bytes: bytes, page_num: int) -> list[str]:
    """
    Trích xuất bảng từ trang PDF bằng pdfplumber.
    Trả về danh sách bảng dạng Markdown.

    pdfplumber nhận diện bảng tốt hơn PyMuPDF nhờ phân tích line segments.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.debug("pdfplumber not available, skipping table extraction")
        return []

    tables_md: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # pdfplumber dùng 0-based index
            if page_num - 1 >= len(pdf.pages):
                return []

            page = pdf.pages[page_num - 1]

            # Extract tables với tolerance hợp lý cho PDF tiếng Việt
            tables = page.extract_tables(
                table_settings={
                    "vertical_strategy": "lines_strict",
                    "horizontal_strategy": "lines_strict",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "edge_min_length": 3,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                }
            )

            # Fallback: thử strategy khác nếu không tìm thấy bảng
            if not tables:
                tables = page.extract_tables(
                    table_settings={
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "snap_tolerance": 5,
                    }
                )

            for table in tables:
                md = _table_to_markdown(table)
                if md and _is_meaningful_table(table):
                    tables_md.append(md)

    except Exception as e:
        logger.warning(f"pdfplumber table extraction failed (page {page_num}): {e}")

    return tables_md


def get_significant_images(page, min_area_ratio: float = IMAGE_AREA_RATIO_THRESHOLD) -> list[dict]:
    """
    Lấy danh sách ảnh đáng kể trong trang (đủ lớn để chứa thông tin).
    Bỏ qua ảnh nhỏ như logo, icon, decoration.

    Trả về list[{xref, bbox, area_ratio}]
    """
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return []

    significant = []
    try:
        for img in page.get_images(full=True):
            xref = img[0]
            # Lấy bounding box của ảnh trên trang
            img_rects = page.get_image_rects(xref)
            if not img_rects:
                continue

            for rect in img_rects:
                img_area = rect.width * rect.height
                ratio = img_area / page_area
                if ratio >= min_area_ratio:
                    significant.append({
                        "xref": xref,
                        "bbox": rect,
                        "area_ratio": ratio,
                    })
    except Exception as e:
        logger.debug(f"get_significant_images failed: {e}")

    return significant


async def describe_page_with_vision(
    page,
    groq_api_key: str,
    context_hint: str = "",
) -> str:
    """
    Render trang thành ảnh và gửi cho Groq Vision để mô tả.
    Dùng khi trang có nhiều ảnh hoặc biểu đồ mang thông tin quan trọng.

    Args:
        page: PyMuPDF page object
        groq_api_key: Groq API key
        context_hint: gợi ý ngữ cảnh để hướng dẫn VLM (ví dụ: tên tài liệu)
    """
    try:
        from groq import AsyncGroq
    except ImportError:
        logger.debug("groq not available for vision")
        return ""

    if not groq_api_key:
        return ""

    try:
        # Render trang thành JPEG (nhẹ hơn PNG, đủ chất lượng)
        mat = page.get_pixmap(dpi=120)  # 120 DPI đủ cho vision task
        img_bytes = mat.tobytes("jpeg")
        b64 = base64.b64encode(img_bytes).decode()

        hint = f" Tài liệu: {context_hint}." if context_hint else ""

        prompt = (
            f"Đây là một trang từ tài liệu học tập.{hint} "
            "Hãy mô tả CHI TIẾT tất cả nội dung trong trang này bằng tiếng Việt, bao gồm:\n"
            "1. Các bảng (nếu có): tiêu đề cột, nội dung từng hàng quan trọng\n"
            "2. Biểu đồ/đồ thị (nếu có): loại biểu đồ, các trục, xu hướng, giá trị nổi bật\n"
            "3. Sơ đồ/hình vẽ (nếu có): mô tả cấu trúc, các thành phần, mối quan hệ\n"
            "4. Công thức/ký hiệu đặc biệt (nếu có): giải thích ý nghĩa\n"
            "5. Text quan trọng không nằm trong đoạn văn thông thường\n"
            "Chú trọng vào kiến thức học thuật, bỏ qua header/footer/logo. "
            "Viết thành văn xuôi mạch lạc, không dùng bullet points."
        )

        client = AsyncGroq(api_key=groq_api_key)
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=800,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    except Exception as e:
        logger.warning(f"Vision API call failed: {e}")
        return ""


async def analyze_pdf_pages(
    pdf_bytes: bytes,
    groq_api_key: str = "",
    doc_title: str = "",
    max_vision_pages: int = 20,
) -> list[PageIntelligence]:
    """
    Pipeline phân tích toàn bộ PDF:
    - Với mỗi trang: kiểm tra scan → OCR nếu cần
    - Trích xuất bảng từ mỗi trang
    - Với trang có ảnh đáng kể: gọi VLM

    Args:
        pdf_bytes: raw PDF bytes
        groq_api_key: để dùng VLM (optional)
        doc_title: gợi ý ngữ cảnh cho VLM
        max_vision_pages: giới hạn số trang dùng VLM (tránh tốn quota)
    """
    try:
        import pymupdf
    except ImportError:
        logger.error("PyMuPDF not available")
        return []

    results: list[PageIntelligence] = []
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    vision_count = 0

    for page_num_0 in range(len(doc)):
        page = doc[page_num_0]
        page_num = page_num_0 + 1  # 1-based cho output

        # Text extraction (PyMuPDF) 
        from app.services.chunker import sanitize_text
        raw_text = sanitize_text(page.get_text("text").strip())

        intel = PageIntelligence(page_num=page_num, raw_text=raw_text)

        # OCR nếu trang là scan 
        if is_page_scanned(page, raw_text):
            intel.is_scanned = True
            intel.ocr_text = ocr_page(page)
            logger.debug(f"Page {page_num}: scanned, OCR text={len(intel.ocr_text)} chars")

        # Bảng (pdfplumber) 
        tables = extract_tables_from_page(pdf_bytes, page_num)
        intel.tables_md = tables

        # VLM cho ảnh đáng kể 
        if groq_api_key and vision_count < max_vision_pages:
            sig_images = get_significant_images(page)
            need_vision = (
                len(sig_images) > 0
                or intel.is_scanned  # Scan page cũng dùng vision để bắt ảnh
                or _page_has_complex_layout(page, raw_text)
            )
            if need_vision:
                desc = await describe_page_with_vision(page, groq_api_key, doc_title)
                if desc:
                    intel.image_descriptions.append(desc)
                    vision_count += 1
                    logger.debug(f"Page {page_num}: VLM description ({len(desc)} chars)")

        results.append(intel)

    doc.close()
    return results


# Helper functions 

def _table_to_markdown(table: list[list]) -> str:
    """
    Convert pdfplumber table (list of rows) thành Markdown table.
    Xử lý cell None, multiline text, text quá dài.
    """
    if not table or len(table) < 2:
        return ""

    def clean_cell(cell) -> str:
        if cell is None:
            return ""
        text = str(cell).strip()
        # Bỏ newlines trong cell
        text = re.sub(r"\s*\n\s*", " ", text)
        # Escape pipe trong cell
        text = text.replace("|", "\\|")
        return text[:200]  # giới hạn độ dài cell

    rows = [[clean_cell(c) for c in row] for row in table]
    if not rows:
        return ""

    # Đảm bảo tất cả rows có cùng số cột
    n_cols = max(len(r) for r in rows)
    rows = [r + [""] * (n_cols - len(r)) for r in rows]

    # Header
    header = rows[0]
    separator = ["---"] * n_cols

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _is_meaningful_table(table: list[list]) -> bool:
    """Bỏ qua bảng có quá ít nội dung (có thể là bảng layout, không phải dữ liệu)."""
    if not table or len(table) < 2:
        return False
    # Đếm số cell có nội dung
    filled = sum(1 for row in table for cell in row if cell and str(cell).strip())
    return filled >= 4


def _page_has_complex_layout(page, raw_text: str) -> bool:
    """
    Kiểm tra trang có layout phức tạp cần VLM không.
    Ví dụ: nhiều text block rải rác, có text rotation, ...
    """
    try:
        blocks = page.get_text("blocks")
        # Nhiều text blocks (> 8) gợi ý layout phức tạp như 2 cột, sidebar, v.v.
        if len(blocks) > 8:
            return True
        # Trang gần như trống nhưng không phải scan → likely all-image
        if len(raw_text.strip()) < 50:
            return True
    except Exception:
        pass
    return False


def _clean_ocr_text(text: str) -> str:
    """Làm sạch output OCR: bỏ artifact phổ biến."""
    # Bỏ dòng chỉ chứa ký tự đặc biệt (OCR noise)
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # Bỏ dòng có > 70% ký tự không phải chữ/số/khoảng trắng
        alpha_ratio = sum(1 for c in stripped if c.isalnum() or c.isspace()) / len(stripped)
        if alpha_ratio >= 0.4:
            lines.append(line)
    return "\n".join(lines).strip()