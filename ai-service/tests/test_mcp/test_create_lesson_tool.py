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
@pytest.mark.parametrize("publish", [None, False, True])
async def test_markdown_lesson_is_published_for_all_client_options(monkeypatch, publish):
    async def fake_create(**kwargs):
        assert kwargs["payload"]["type"] == "TEXT"
        assert kwargs["payload"]["metadata"]["content"] == "# Hello"
        return {"id": 123, "is_published": False}

    monkeypatch.setattr(
        "app.agents.tools.teacher.mcp_create_lesson._create_lesson_content",
        fake_create,
    )
    async def fake_publish(content_id, user_id):
        assert (content_id, user_id) == (123, 7)

    monkeypatch.setattr("app.agents.tools.teacher.mcp_create_lesson._publish_content", fake_publish)
    result = await McpCreateLessonTool().execute(
        **({"publish": publish} if publish is not None else {}),
        _user_id=7,
        course_id=11,
        section_id=12,
        title="Hello lesson",
        markdown="# Hello",
    )
    assert result.status == "success"
    assert result.data["content"]["id"] == 123
    assert result.data["content"]["is_published"] is True
    assert result.data["state"] == "published"


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
