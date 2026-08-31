from __future__ import annotations

import pytest

from app.agents.tools.shared.list_accessible_courses import ListAccessibleCoursesTool
from mcp.course_access import _unwrap_items


def test_unwrap_items_supports_lms_wrappers():
    assert _unwrap_items({"data": {"items": [{"id": 1}]}}) == [{"id": 1}]
    assert _unwrap_items({"data": [{"course_id": 2}]}) == [{"course_id": 2}]
    assert _unwrap_items({"data": None}) == []


@pytest.mark.asyncio
async def test_list_accessible_courses_tool_returns_access_kind(monkeypatch):
    async def fake_list(user_id: int):
        assert user_id == 42
        return [
            {"id": 10, "title": "Owned", "access": "OWNER_OR_CO_TEACHER"},
            {"id": 20, "title": "Enrolled", "access": "ENROLLED_STUDENT"},
        ]

    monkeypatch.setattr("mcp.course_access.list_accessible_courses", fake_list)
    result = await ListAccessibleCoursesTool().execute(_user_id=42)

    assert result.status == "success"
    assert [course["access"] for course in result.data["courses"]] == [
        "OWNER_OR_CO_TEACHER",
        "ENROLLED_STUDENT",
    ]
