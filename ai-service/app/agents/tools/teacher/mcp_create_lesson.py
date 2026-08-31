"""Create a real LMS lesson from Markdown or an uploaded document for MCP clients."""
from __future__ import annotations

import asyncio
import base64
import binascii
import ipaddress
import logging
import os
import re
import socket
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings
from app.services.minio_storage import upload_bytes

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_MARKDOWN_BYTES = 180 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
# JSON-RPC requests stay deliberately small to protect the shared API. Large
# documents use file_url; this inline route only supports compact artifacts.
MAX_INLINE_FILE_BYTES = 180 * 1024
DOCUMENT_TYPES = {
    ".pdf": "application/pdf",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


class McpCreateLessonTool(BaseTool):
    name = "mcp_create_lesson"
    description = (
        "Create a lesson inside an existing LMS section. Provide Markdown to create a TEXT lesson, "
        "or provide a PDF/PPT/PPTX/DOC/DOCX/ODT/TXT file via a public HTTPS URL or base64 payload "
        "to upload it into BDC storage and create a DOCUMENT lesson. This changes the course and "
        "requires an explicit teacher request and a write-enabled MCP credential."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "integer", "description": "Course that owns the target section."},
            "section_id": {"type": "integer", "description": "Existing LMS section ID that receives the lesson."},
            "title": {"type": "string", "description": "Learner-facing lesson title."},
            "markdown": {"type": "string", "description": "Markdown body for a TEXT lesson. Mutually exclusive with file_url/file_base64."},
            "file_url": {"type": "string", "description": "Public HTTPS URL of a document to import. Redirects, localhost and private-network URLs are rejected."},
            "file_base64": {"type": "string", "description": "Base64-encoded small document bytes. Use file_url for normal PDF/PPTX/DOCX uploads because MCP request bodies are intentionally bounded."},
            "file_name": {"type": "string", "description": "Required for base64 files; optional for URLs when the URL has a supported filename extension."},
            "description": {"type": "string", "description": "Optional learner-facing description."},
            "order_index": {"type": "integer", "minimum": 0, "description": "Position in the section; defaults to the end."},
            "is_mandatory": {"type": "boolean", "default": False},
            "publish": {"type": "boolean", "default": False, "description": "Publish immediately only when the teacher explicitly requests it. Otherwise it remains a draft."},
        },
        "required": ["course_id", "section_id", "title"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = int(kwargs.get("_user_id") or 0)
        course_id = _positive_int(kwargs.get("course_id"))
        section_id = _positive_int(kwargs.get("section_id"))
        title = str(kwargs.get("title") or "").strip()
        description = str(kwargs.get("description") or "").strip()
        if not user_id or not course_id or not section_id or not 3 <= len(title) <= 255:
            return _error("invalid_request", "course_id, section_id and a 3–255 character title are required.")
        if len(description) > 2_000:
            return _error("description_too_long", "Description must be at most 2,000 characters.")

        markdown = kwargs.get("markdown")
        file_url = str(kwargs.get("file_url") or "").strip()
        file_base64 = str(kwargs.get("file_base64") or "").strip()
        supplied = sum(bool(value) for value in (markdown, file_url, file_base64))
        if supplied != 1:
            return _error("invalid_source", "Provide exactly one of markdown, file_url, or file_base64.")

        order_index = kwargs.get("order_index")
        if order_index is not None and (not isinstance(order_index, int) or order_index < 0):
            return _error("invalid_order", "order_index must be a non-negative integer.")

        if markdown:
            if not isinstance(markdown, str) or len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
                return _error("markdown_too_large", "Markdown is limited to 180 KB.")
            payload = {"type": "TEXT", "title": title, "description": description, "metadata": {"content": markdown}}
        else:
            try:
                filename, data, content_type = await self._resolve_document(
                    file_url=file_url,
                    file_base64=file_base64,
                    requested_name=str(kwargs.get("file_name") or "").strip(),
                )
            except ValueError as exc:
                return _error("invalid_file", str(exc))
            except Exception:
                logger.exception("MCP lesson document import failed")
                return _error("file_import_failed", "The document could not be retrieved or stored safely.")

            object_key = f"document/mcp/{user_id}/{uuid4().hex}_{filename}"
            if not await upload_bytes(object_key, data, content_type):
                return _error("storage_failed", "The document could not be uploaded to BDC storage.")
            payload = {
                "type": "DOCUMENT",
                "title": title,
                "description": description,
                "metadata": {
                    "file_path": object_key,
                    "file_name": filename,
                    "file_size": len(data),
                    "file_type": content_type,
                    "mcp_uploaded": True,
                },
            }

        try:
            content = await _create_lesson_content(
                section_id=section_id,
                user_id=user_id,
                payload=payload,
                order_index=order_index,
                is_mandatory=bool(kwargs.get("is_mandatory", False)),
            )
            if bool(kwargs.get("publish", False)):
                await _publish_content(int(content["id"]), user_id)
                content["is_published"] = True
        except PermissionError as exc:
            return _error("forbidden", str(exc))
        except ValueError as exc:
            return _error("lms_validation_failed", str(exc))
        except Exception:
            logger.exception("MCP lesson creation failed")
            return _error("lesson_create_failed", "LMS could not create the lesson.")

        state = "published" if content.get("is_published") else "draft"
        return ToolResult(
            status="success",
            data={"course_id": course_id, "section_id": section_id, "content": content, "state": state},
            message=f"Created {state} lesson '{title}' (content ID: {content.get('id')}).",
        )

    async def _resolve_document(self, *, file_url: str, file_base64: str, requested_name: str) -> tuple[str, bytes, str]:
        if file_base64:
            encoded = file_base64.split(",", 1)[-1] if file_base64.startswith("data:") else file_base64
            if len(encoded) > (MAX_INLINE_FILE_BYTES * 4 // 3) + 8:
                raise ValueError("Inline files are limited to 180 KB; use file_url for larger documents.")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("file_base64 must be valid base64.") from exc
            filename = _validate_filename(requested_name)
            if len(data) > MAX_INLINE_FILE_BYTES:
                raise ValueError("Inline files are limited to 180 KB; use file_url for larger documents.")
            return filename, data, DOCUMENT_TYPES[PurePosixPath(filename).suffix.lower()]

        parsed = _validate_public_https_url(file_url)
        await _reject_private_host(parsed.hostname or "")
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=False, trust_env=False) as client:
            async with client.stream("GET", file_url, headers={"Accept": ", ".join(DOCUMENT_TYPES.values())}) as response:
                if response.is_redirect:
                    raise ValueError("Redirecting file URLs are not accepted.")
                if response.status_code != 200:
                    raise ValueError(f"File URL returned HTTP {response.status_code}.")
                length = response.headers.get("content-length")
                if length and int(length) > MAX_FILE_BYTES:
                    raise ValueError("File exceeds the 25 MB limit.")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise ValueError("File exceeds the 25 MB limit.")
                    chunks.append(chunk)
        filename = _validate_filename(requested_name or os.path.basename(parsed.path))
        return filename, b"".join(chunks), DOCUMENT_TYPES[PurePosixPath(filename).suffix.lower()]


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _error(code: str, message: str) -> ToolResult:
    return ToolResult(status="error", data={"error": code}, message=message)


def _validate_filename(value: str) -> str:
    filename = PurePosixPath(value.replace("\\", "/")).name.strip()
    filename = re.sub(r"[^A-Za-z0-9._() -]", "_", filename)[:180]
    extension = PurePosixPath(filename).suffix.lower()
    if not filename or extension not in DOCUMENT_TYPES:
        raise ValueError("Supported document types are PDF, PPT/PPTX, DOC/DOCX, ODT, TXT and Markdown.")
    return filename


def _validate_public_https_url(value: str):
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("file_url must be a public HTTPS URL without credentials.")
    return parsed


async def _reject_private_host(hostname: str) -> None:
    try:
        literal = ipaddress.ip_address(hostname)
        addresses = [literal]
    except ValueError:
        results = await asyncio.to_thread(socket.getaddrinfo, hostname, 443, type=socket.SOCK_STREAM)
        addresses = [ipaddress.ip_address(row[4][0]) for row in results]
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("file_url must resolve only to public Internet addresses.")


def _lms_headers(user_id: int) -> dict[str, str]:
    return {"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)}


async def _create_lesson_content(*, section_id: int, user_id: int, payload: dict[str, Any], order_index: int | None, is_mandatory: bool) -> dict[str, Any]:
    lms_base = settings.lms_service_url.rstrip("/")
    async with httpx.AsyncClient(timeout=20.0) as client:
        if order_index is None:
            listed = await client.get(f"{lms_base}/api/v1/sections/{section_id}/content", headers=_lms_headers(user_id))
            if listed.status_code == 403:
                raise PermissionError("You may only create lessons in sections you own or co-teach.")
            if listed.status_code == 404:
                raise ValueError("Section not found.")
            if listed.status_code != 200:
                raise ValueError("Could not inspect the target section.")
            body = listed.json()
            items = body.get("data", body) if isinstance(body, dict) else body
            order_index = len(items) if isinstance(items, list) else 0
        payload.update({"order_index": order_index, "is_mandatory": is_mandatory})
        response = await client.post(f"{lms_base}/api/v1/sections/{section_id}/content", json=payload, headers=_lms_headers(user_id))
    if response.status_code == 403:
        raise PermissionError("You may only create lessons in sections you own or co-teach.")
    if response.status_code == 404:
        raise ValueError("Section not found.")
    if response.status_code not in (200, 201):
        raise ValueError(_response_error(response))
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else body


async def _publish_content(content_id: int, user_id: int) -> None:
    lms_base = settings.lms_service_url.rstrip("/")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.put(f"{lms_base}/api/v1/content/{content_id}", json={"is_published": True}, headers=_lms_headers(user_id))
    if response.status_code != 200:
        raise ValueError(_response_error(response))


def _response_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            return str(body.get("message") or body.get("error") or "LMS rejected the lesson.")
    except ValueError:
        pass
    return "LMS rejected the lesson."
