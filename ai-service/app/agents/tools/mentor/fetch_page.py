"""
Mentor/Teacher Shared Tool: fetch_page

Reads a web page and returns clean text so the agent can ground claims in
the actual content instead of a search snippet. Pairs with ``search_web``:
search first, then fetch the 1-2 most promising URLs before citing.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_MAX_BYTES = 1_500_000
_MAX_CHARS = 6000
_BLOCKED_HOSTS = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)",
    re.I,
)


def _strip_html(html: str) -> str:
    """Cheap tag-to-text conversion without external dependencies."""
    html = re.sub(r"<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>",
                  " ", html, flags=re.I | re.S)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    text = (
        html.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln) > 1]
    return "\n".join(lines)


class FetchPageTool(BaseTool):
    name = "fetch_page"
    description = (
        "Fetch a web page by URL and return its readable text content. "
        "Use after search_web when a result looks promising and you need "
        "the actual details/code/steps before answering or citing it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Absolute http(s) URL of the page to read.",
            },
        },
        "required": ["url"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolResult(
                status="error",
                data={"error": "invalid_url"},
                message="URL không hợp lệ - cần đường dẫn http(s) đầy đủ.",
            )
        if _BLOCKED_HOSTS.match(parsed.hostname or ""):
            return ToolResult(
                status="error",
                data={"error": "blocked_host"},
                message="Không được phép truy cập địa chỉ nội bộ.",
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                raw = resp.content[:_MAX_BYTES]
                if "html" in content_type or not content_type:
                    title_match = re.search(
                        r"<title[^>]*>(.*?)</title>", raw.decode(resp.encoding or "utf-8", "ignore"),
                        re.I | re.S,
                    )
                    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""
                    text = _strip_html(raw.decode(resp.encoding or "utf-8", "ignore"))
                else:
                    # Plain text / markdown / code endpoints
                    title = ""
                    text = raw.decode("utf-8", "ignore")
        except Exception as e:
            logger.warning("fetch_page failed for %s: %s", url, e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Không tải được trang: {e}",
            )

        if not text.strip():
            return ToolResult(
                status="success",
                data={"url": url, "content": "", "truncated": False},
                message="Trang tải được nhưng không có nội dung văn bản đọc được.",
            )

        truncated = len(text) > _MAX_CHARS
        if truncated:
            cut = text.rfind("\n", 0, _MAX_CHARS)
            text = text[: cut if cut > int(_MAX_CHARS * 0.7) else _MAX_CHARS] + "\n…[đã cắt để vừa ngữ cảnh]"

        return ToolResult(
            status="success",
            data={
                "url": url,
                "title": title or None,
                "content": text,
                "chars": len(text),
                "truncated": truncated,
            },
            message=f"Đã đọc trang ({len(text)} ký tự{', đã cắt' if truncated else ''}).",
        )
