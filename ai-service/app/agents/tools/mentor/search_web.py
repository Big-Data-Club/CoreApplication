"""
Mentor/Teacher Shared Tool: search_web

Allows agents to search the web using DuckDuckGo HTML search for up-to-date information.
"""
from __future__ import annotations

import logging
import httpx
import re
from urllib.parse import unquote

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SearchWebTool(BaseTool):
    name = "search_web"
    description = (
        "Search the web for up-to-date information, documentation, news, coding tutorials, "
        "or general knowledge not found in the course materials. Use this when the user "
        "asks about general technology, libraries, external APIs, or requests recent information."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web.",
            },
            "max_results": {
                "type": "integer",
                "description": "Optional: maximum number of results to return. Default is 4.",
                "default": 4,
            }
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs["query"]
        max_results = kwargs.get("max_results", 4)

        try:
            results = await self._search_ddg(query, max_results)
            if not results:
                return ToolResult(
                    status="success",
                    data={"results": [], "query": query},
                    message=f"Không tìm thấy kết quả tìm kiếm web nào cho '{query}'."
                )

            formatted_message = f"Tìm thấy {len(results)} kết quả tìm kiếm web."
            return ToolResult(
                status="success",
                data={"results": results, "query": query, "count": len(results)},
                message=formatted_message
            )
        except Exception as e:
            logger.error("SearchWebTool failed: %s", e, exc_info=True)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi tìm kiếm web: {str(e)}"
            )

    async def _search_ddg(self, query: str, max_results: int) -> list[dict]:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(url, data={"q": query}, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"DuckDuckGo HTML search returned status code {resp.status_code}")

            html = resp.text
            results = []

            # 1. Try to find result bodies (standard structure)
            bodies = re.findall(r'<div class="result__body">.*?</div>\s*</div>', html, re.DOTALL)
            if not bodies:
                bodies = re.findall(r'<div class="web-result.*?</div>\s*</div>', html, re.DOTALL)

            for body in bodies[:max_results]:
                # Extract URL and Title
                title_url_match = re.search(
                    r'<a[^>]+class="result__url"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                    body,
                    re.DOTALL
                )
                if not title_url_match:
                    title_url_match = re.search(
                        r'<a[^>]+class="result__title"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                        body,
                        re.DOTALL
                    )

                # Extract Snippet
                snippet_match = re.search(
                    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                    body,
                    re.DOTALL
                )
                if not snippet_match:
                    snippet_match = re.search(
                        r'<span class="result__snippet"[^>]*>(.*?)</span>',
                        body,
                        re.DOTALL
                    )

                if title_url_match:
                    raw_url = title_url_match.group(1)
                    title = re.sub(r'<[^>]+>', '', title_url_match.group(2)).strip()

                    # Resolve redirect link from DuckDuckGo
                    url_val = raw_url
                    if "uddg=" in raw_url:
                        parts = raw_url.split("uddg=")
                        if len(parts) > 1:
                            url_val = unquote(parts[1].split("&")[0])
                    elif raw_url.startswith("//"):
                        url_val = "https:" + raw_url

                    snippet = ""
                    if snippet_match:
                        snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()

                    results.append({
                        "title": title,
                        "url": url_val,
                        "snippet": snippet
                    })

            # 2. Simple fallback: if no bodies matched, extract any external links and titles
            if not results:
                urls = re.findall(r'href="([^"]*?uddg=[^"]+?)"', html)
                unique_urls = []
                for u in urls:
                    parts = u.split("uddg=")
                    real_url = unquote(parts[1].split("&")[0])
                    if real_url not in unique_urls and "duckduckgo.com" not in real_url:
                        unique_urls.append(real_url)

                for u in unique_urls[:max_results]:
                    # Generate a clean title from the domain/URL path
                    domain_match = re.search(r'https?://(?:www\.)?([^/]+)', u)
                    domain = domain_match.group(1) if domain_match else "Website"
                    results.append({
                        "title": f"Xem bài viết trên {domain}",
                        "url": u,
                        "snippet": "Bấm vào đường link để xem chi tiết bài viết này từ kết quả tìm kiếm web."
                    })

            return results
