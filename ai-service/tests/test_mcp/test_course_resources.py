"""MCP course-material resource coverage."""
from __future__ import annotations

import json

import pytest

from mcp import resources


COURSE_CONTENTS = [{
    "id": 10,
    "title": "Chương 1",
    "description": "",
    "order_index": 0,
    "contents": [{
        "id": 99,
        "type": "DOCUMENT",
        "title": "Bài giảng.pdf",
        "description": "Tài liệu chính",
        "order_index": 0,
        "is_mandatory": True,
        "file_type": "application/pdf",
        "file_size": 1234,
        "ai_index_status": "indexed",
        "metadata": {},
    }],
}]


@pytest.mark.asyncio
async def test_course_contents_resource_lists_safe_content_uris(monkeypatch):
    async def fake_fetch(course_id, user_id):
        assert (course_id, user_id) == (7, 42)
        return COURSE_CONTENTS

    monkeypatch.setattr(resources, "_fetch_course_contents", fake_fetch)
    result = await resources.read_mcp_resource("bdc://courses/7/contents", 42)
    payload = json.loads(result["contents"][0]["text"])

    item = payload["sections"][0]["contents"][0]
    assert item["uri"] == "bdc://courses/7/contents/99"
    assert "file_path" not in item
    assert item["ai_index_status"] == "indexed"


@pytest.mark.asyncio
async def test_document_resource_returns_indexed_text_with_paging(monkeypatch):
    async def fake_fetch(course_id, user_id):
        return COURSE_CONTENTS

    async def fake_indexed_text(content_id):
        assert content_id == 99
        return ["abcdef", "ghijkl"]

    monkeypatch.setattr(resources, "_fetch_course_contents", fake_fetch)
    monkeypatch.setattr(resources, "_get_indexed_content_text", fake_indexed_text)
    result = await resources.read_mcp_resource(
        "bdc://courses/7/contents/99?offset_chars=2&limit_chars=5", 42,
    )
    payload = json.loads(result["contents"][0]["text"])

    assert payload["text_source"] == "indexed_file"
    assert payload["text"] == "cdef\n"
    assert payload["next_offset_chars"] == 7


@pytest.mark.asyncio
async def test_document_resource_requires_content_to_belong_to_course(monkeypatch):
    async def fake_fetch(course_id, user_id):
        return COURSE_CONTENTS

    monkeypatch.setattr(resources, "_fetch_course_contents", fake_fetch)
    with pytest.raises(ValueError, match="Content not found"):
        await resources.read_mcp_resource("bdc://courses/7/contents/100", 42)
