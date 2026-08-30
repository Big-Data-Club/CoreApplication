"""
ai-service/mcp/resources.py

MCP Resources - exposes BDC courses and documents as MCP Resources.

MCP Resources allow clients to browse and read content from the server
before (or without) making tool calls. We expose:

  - bdc://courses/{course_id}        - Course metadata
  - bdc://courses/{course_id}/docs   - List of uploaded documents for a course

Clients (e.g. Claude Desktop) can see these resources in the sidebar and
reference them in prompts without needing to call list_my_courses first.

Implementation notes:
  - Resources are read-only (MCP resources/read is a GET analogue).
  - Requires the caller's user_id (resolved from API key).
  - All data goes through the LMS HTTP API or the AI-service's own DB to
    respect service ownership boundaries (rule #2: never read another
    service's DB directly).
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
_SKILLSET_ROOT = Path(__file__).resolve().parent.parent / "mcp_skillset"


# ---------------------------------------------------------------------------
# Resource list
# ---------------------------------------------------------------------------

async def list_mcp_resources(user_id: int) -> list[dict]:
    """
    Return MCP Resource descriptors for the given user.

    Each descriptor:
    {
        "uri":      "bdc://courses/42",
        "name":     "Introduction to Python",
        "mimeType": "application/json",
        "description": "..."
    }
    """
    resources: list[dict] = []

    manifest_path = _SKILLSET_ROOT / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            resources.append({
                "uri": "bdc://skills/catalog",
                "name": "BDC Hub MCP skills",
                "mimeType": "application/json",
                "description": "Safety-first workflows for BDC Hub MCP clients.",
            })
            for relative in manifest.get("skills", []):
                slug = Path(relative).parent.name
                resources.append({
                    "uri": f"bdc://skills/{slug}",
                    "name": slug,
                    "mimeType": "text/markdown",
                    "description": f"BDC Hub skill: {slug}",
                })
        except Exception as exc:
            logger.warning("MCP skill manifest unavailable: %s", exc)

    # Attempt to fetch courses from LMS service.
    # Gracefully return empty list if LMS is unreachable.
    try:
        lms_base = settings.lms_service_url.rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{lms_base}/api/v1/courses/my",
                params={"page": 1, "page_size": 100},
                headers={"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)},
            )
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", payload) if isinstance(payload, dict) else payload
            courses: list[dict] = data.get("items", []) if isinstance(data, dict) else data

        for course in courses:
            cid = course.get("id")
            title = course.get("title", f"Course {cid}")
            resources.append({
                "uri": f"bdc://courses/{cid}",
                "name": title,
                "mimeType": "application/json",
                "description": f"BDC course: {title}",
            })
    except Exception as exc:
        logger.warning("MCP resources: failed to fetch courses from LMS: %s", exc)

    return resources


# ---------------------------------------------------------------------------
# Resource read
# ---------------------------------------------------------------------------

async def read_mcp_resource(uri: str, user_id: int) -> dict:
    """
    Read a single MCP resource by URI.

    Returns:
        MCP ReadResourceResult:
        {
            "contents": [{"uri": "...", "mimeType": "...", "text": "..."}]
        }
    Raises:
        ValueError if the URI scheme or path is unrecognised.
    """
    if not uri.startswith("bdc://"):
        raise ValueError(f"Unsupported URI scheme: {uri!r}")

    path = uri[len("bdc://"):]  # e.g. "courses/42"
    parts = path.strip("/").split("/")

    if parts[0] == "skills" and len(parts) == 2:
        if parts[1] == "catalog":
            target = _SKILLSET_ROOT / "manifest.json"
            mime_type = "application/json"
        else:
            slug = parts[1]
            if not slug.replace("-", "").isalnum():
                raise ValueError("Invalid skill name")
            target = _SKILLSET_ROOT / "skills" / slug / "SKILL.md"
            mime_type = "text/markdown"
        if not target.is_file():
            raise ValueError("Skill resource not found")
        return {"contents": [{"uri": uri, "mimeType": mime_type, "text": target.read_text(encoding="utf-8")}]} 

    if parts[0] == "courses" and len(parts) >= 2:
        course_id_str = parts[1]
        try:
            course_id = int(course_id_str)
        except ValueError:
            raise ValueError(f"Invalid course_id in URI: {uri!r}")

        text_content = await _read_course_resource(course_id, user_id)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": text_content,
                }
            ]
        }

    raise ValueError(f"Unrecognised resource path: {path!r}")


async def _read_course_resource(course_id: int, user_id: int) -> str:
    """Fetch course details from LMS and return as JSON string."""
    try:
        from mcp.tool_adapter import _user_owns_course
        if not await _user_owns_course(user_id, course_id):
            raise ValueError("Course not found or not available to this credential")
        lms_base = settings.lms_service_url.rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{lms_base}/api/v1/courses/{course_id}",
                headers={
                    "X-API-Secret": settings.ai_service_secret,
                    "X-User-Id": str(user_id),
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        return json.dumps(data, ensure_ascii=False, indent=2)
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("MCP course resource failed: %s", exc)
        return json.dumps({"error": "Course resource is temporarily unavailable"})
