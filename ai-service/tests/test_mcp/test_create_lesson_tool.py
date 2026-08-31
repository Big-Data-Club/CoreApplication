from __future__ import annotations

import pytest

from app.agents.tools.teacher.mcp_create_lesson import (
    McpCreateLessonTool,
    _validate_filename,
    _validate_public_https_url,
)


def test_lesson_document_filename_validation():
    assert _validate_filename("../Week 1.pptx") == "Week 1.pptx"
    with pytest.raises(ValueError):
        _validate_filename("lesson.exe")


def test_lesson_file_url_requires_public_https():
    assert _validate_public_https_url("https://example.org/lesson.pdf").hostname == "example.org"
    with pytest.raises(ValueError):
        _validate_public_https_url("http://example.org/lesson.pdf")
    with pytest.raises(ValueError):
        _validate_public_https_url("https://user:pass@example.org/lesson.pdf")


@pytest.mark.asyncio
async def test_markdown_lesson_creates_text_draft(monkeypatch):
    async def fake_create(**kwargs):
        assert kwargs["payload"]["type"] == "TEXT"
        assert kwargs["payload"]["metadata"]["content"] == "# Hello"
        return {"id": 123, "is_published": False}

    monkeypatch.setattr(
        "app.agents.tools.teacher.mcp_create_lesson._create_lesson_content",
        fake_create,
    )
    result = await McpCreateLessonTool().execute(
        _user_id=7,
        course_id=11,
        section_id=12,
        title="Hello lesson",
        markdown="# Hello",
    )
    assert result.status == "success"
    assert result.data["content"]["id"] == 123


@pytest.mark.asyncio
async def test_lesson_requires_one_source():
    result = await McpCreateLessonTool().execute(
        _user_id=7,
        course_id=11,
        section_id=12,
        title="Hello lesson",
    )
    assert result.status == "error"
    assert result.data["error"] == "invalid_source"
