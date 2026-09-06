"""
ai-service/mcp/resources.py

MCP Resources - exposes BDC courses and documents as MCP Resources.

MCP Resources allow clients to browse and read content from the server
before (or without) making tool calls. We expose:

  - bdc://courses/{course_id}        - Course metadata
  - bdc://courses/{course_id}/contents - Course structure and material metadata
  - bdc://courses/{course_id}/contents/{content_id} - Text lesson or indexed file text

Clients (e.g. Claude Desktop) can see owned/co-taught and accepted-enrollment
resources in the sidebar without needing to call a discovery tool first.

Implementation notes:
  - Resources are read-only (MCP resources/read is a GET analogue).
  - Requires the caller's user_id (resolved from API key).
  - All data goes through the LMS HTTP API or the AI-service's own DB to
    respect service ownership boundaries (rule #2: never read another
    service's DB directly).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
_SKILLSET_ROOT = Path(__file__).resolve().parent.parent / "mcp_skillset"
_DEFAULT_DOCUMENT_CHAR_LIMIT = 80_000
_MAX_DOCUMENT_CHAR_LIMIT = 200_000


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
        from mcp.course_access import list_accessible_courses
        courses = await list_accessible_courses(user_id)

        for course in courses:
            cid = course.get("id")
            title = course.get("title", f"Course {cid}")
            resources.append({
                "uri": f"bdc://courses/{cid}",
                "name": title,
                "mimeType": "application/json",
                "description": f"BDC course: {title}",
            })
            resources.append({
                "uri": f"bdc://courses/{cid}/contents",
                "name": f"{title} — course materials",
                "mimeType": "application/json",
                "description": (
                    "Course sections and content metadata. Read an individual "
                    "content URI returned here to obtain Markdown or text extracted "
                    "from an indexed file."
                ),
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

    parsed = urlparse(uri)
    if parsed.scheme != "bdc" or parsed.netloc != "courses":
        # Skills have a different authority, so preserve their existing URI form.
        parsed = None
        path = uri[len("bdc://"):]
    else:
        path = f"courses/{parsed.path.strip('/')}"
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

        if len(parts) == 2:
            text_content = await _read_course_resource(course_id, user_id)
        elif len(parts) == 3 and parts[2] == "contents":
            text_content = await _read_course_contents_resource(course_id, user_id)
        elif len(parts) == 4 and parts[2] == "contents":
            try:
                content_id = int(parts[3])
            except ValueError:
                raise ValueError(f"Invalid content_id in URI: {uri!r}")
            query = parse_qs(parsed.query) if parsed else {}
            text_content = await _read_content_resource(
                course_id, content_id, user_id, _parse_char_offset(query), _parse_char_limit(query),
            )
        else:
            raise ValueError(f"Unrecognised course resource path: {path!r}")
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


def _parse_char_offset(query: dict[str, list[str]]) -> int:
    value = query.get("offset_chars", ["0"])[0]
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        raise ValueError("offset_chars must be a non-negative integer")


def _parse_char_limit(query: dict[str, list[str]]) -> int:
    value = query.get("limit_chars", [str(_DEFAULT_DOCUMENT_CHAR_LIMIT)])[0]
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise ValueError("limit_chars must be an integer")
    if not 1 <= limit <= _MAX_DOCUMENT_CHAR_LIMIT:
        raise ValueError(f"limit_chars must be between 1 and {_MAX_DOCUMENT_CHAR_LIMIT}")
    return limit


async def _read_course_resource(course_id: int, user_id: int) -> str:
    """Return course metadata already authorized by the LMS course-list endpoint."""
    try:
        from mcp.course_access import list_accessible_courses

        courses = await list_accessible_courses(user_id)
        course = next((item for item in courses if item.get("id") == course_id), None)
        if course is None:
            raise ValueError("Course not found or not available to this credential")
        return json.dumps(course, ensure_ascii=False, indent=2)
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("MCP course resource failed: %s", exc)
        return json.dumps({"error": "Course resource is temporarily unavailable"})


def _lms_headers(user_id: int) -> dict[str, str]:
    return {
        "X-API-Secret": settings.ai_service_secret,
        "X-User-Id": str(user_id),
    }


def _unwrap_data(payload: Any) -> Any:
    return payload.get("data", payload) if isinstance(payload, dict) else payload


async def _fetch_course_contents(course_id: int, user_id: int) -> list[dict[str, Any]]:
    """Read LMS content through its user-aware endpoints after fail-closed access check."""
    from mcp.tool_adapter import _user_can_read_course

    if not await _user_can_read_course(user_id, course_id):
        raise ValueError("Course not found or not available to this credential")

    base = settings.lms_service_url.rstrip("/")
    async with httpx.AsyncClient(timeout=15.0) as client:
        sections_response = await client.get(
            f"{base}/api/v1/courses/{course_id}/sections", headers=_lms_headers(user_id),
        )
        sections_response.raise_for_status()
        raw_sections = _unwrap_data(sections_response.json())
        if not isinstance(raw_sections, list):
            raise RuntimeError("LMS returned an invalid sections payload")

        sections: list[dict[str, Any]] = []
        for section in raw_sections:
            if not isinstance(section, dict) or not isinstance(section.get("id"), int):
                continue
            contents_response = await client.get(
                f"{base}/api/v1/sections/{section['id']}/content", headers=_lms_headers(user_id),
            )
            contents_response.raise_for_status()
            raw_contents = _unwrap_data(contents_response.json())
            contents = [item for item in raw_contents if isinstance(item, dict)] if isinstance(raw_contents, list) else []
            sections.append({
                "id": section["id"],
                "title": section.get("title", "Untitled section"),
                "description": section.get("description", ""),
                "order_index": section.get("order_index", 0),
                "contents": contents,
            })
    return sections


def _content_summary(content: dict[str, Any], course_id: int) -> dict[str, Any]:
    """Return analysis-relevant metadata without exposing storage object keys."""
    content_id = content.get("id")
    result = {
        "id": content_id,
        "uri": f"bdc://courses/{course_id}/contents/{content_id}",
        "type": content.get("type"),
        "title": content.get("title"),
        "description": content.get("description", ""),
        "order_index": content.get("order_index", 0),
        "is_mandatory": bool(content.get("is_mandatory")),
        "file_type": content.get("file_type", ""),
        "file_size": content.get("file_size", 0),
        "ai_index_status": content.get("ai_index_status", "not_indexed"),
    }
    return result


async def _read_course_contents_resource(course_id: int, user_id: int) -> str:
    try:
        sections = await _fetch_course_contents(course_id, user_id)
        return json.dumps({
            "course_id": course_id,
            "sections": [{
                **{key: section[key] for key in ("id", "title", "description", "order_index")},
                "contents": [_content_summary(content, course_id) for content in section["contents"]],
            } for section in sections],
        }, ensure_ascii=False, indent=2)
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("MCP course contents resource failed: %s", exc)
        return json.dumps({"error": "Course materials are temporarily unavailable"})


async def _read_content_resource(
    course_id: int, content_id: int, user_id: int, offset_chars: int, limit_chars: int,
) -> str:
    try:
        sections = await _fetch_course_contents(course_id, user_id)
        content = next(
            (item for section in sections for item in section["contents"] if item.get("id") == content_id), None,
        )
        if content is None:
            raise ValueError("Content not found in this course or not available to this credential")

        metadata = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
        inline_text = metadata.get("content") if isinstance(metadata.get("content"), str) else ""
        chunks = await _get_indexed_content_text(content_id)
        extracted_text = "\n\n".join(chunks)
        source = "indexed_file" if extracted_text else "inline_content" if inline_text else "description"
        full_text = extracted_text or inline_text or str(content.get("description") or "")
        page = full_text[offset_chars:offset_chars + limit_chars]

        return json.dumps({
            "course_id": course_id,
            "content": _content_summary(content, course_id),
            "text_source": source if full_text else "unavailable",
            "text": page,
            "offset_chars": offset_chars,
            "returned_chars": len(page),
            "total_chars": len(full_text),
            "next_offset_chars": offset_chars + len(page) if offset_chars + len(page) < len(full_text) else None,
            "notice": (
                "No extracted text is available. Index the file first, then read this resource again."
                if not full_text and content.get("type") == "DOCUMENT" else None
            ),
        }, ensure_ascii=False, indent=2)
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("MCP content resource failed: %s", exc)
        return json.dumps({"error": "Course content is temporarily unavailable"})


async def _get_indexed_content_text(content_id: int) -> list[str]:
    """Return normalized text extracted at indexing time; never download arbitrary files in an MCP read."""
    from app.core.database import get_ai_conn

    async with get_ai_conn() as conn:
        rows = await conn.fetch(
            """SELECT chunk_text FROM document_chunks
               WHERE content_id = $1 AND status = 'ready'
               ORDER BY chunk_index, id""",
            content_id,
        )
    return [row["chunk_text"] for row in rows if row["chunk_text"]]
