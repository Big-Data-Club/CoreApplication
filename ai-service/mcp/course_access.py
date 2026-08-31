"""Course access helpers shared by MCP tools and resources.

Read access includes courses owned/co-taught by the caller and courses where
the caller has an ACCEPTED enrollment.  Write access remains owner/co-teacher
only and is checked separately by the tool adapter.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings

settings = get_settings()


def _headers(user_id: int) -> dict[str, str]:
    return {
        "X-API-Secret": settings.ai_service_secret,
        "X-User-Id": str(user_id),
    }


def _unwrap_items(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = data.get("items", [])
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


async def list_accessible_courses(user_id: int) -> list[dict[str, Any]]:
    """Return owned/co-taught and accepted-enrollment courses, deduplicated."""
    base = settings.lms_service_url.rstrip("/")
    headers = _headers(user_id)
    owned: list[dict[str, Any]] = []
    enrolled: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        responses = await asyncio.gather(
            client.get(
                f"{base}/api/v1/courses/my",
                params={"page": 1, "page_size": 100},
                headers=headers,
            ),
            client.get(
                f"{base}/api/v1/enrollments/my",
                params={"status": "ACCEPTED"},
                headers=headers,
            ),
            return_exceptions=True,
        )

    successful = 0
    for index, response in enumerate(responses):
        if isinstance(response, Exception):
            continue
        try:
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        successful += 1
        if index == 0:
            owned = _unwrap_items(response.json())
        else:
            enrolled = _unwrap_items(response.json())
    if successful == 0:
        raise RuntimeError("LMS did not return owned or enrolled courses")

    courses: dict[int, dict[str, Any]] = {}
    for item in owned:
        course_id = item.get("id")
        if isinstance(course_id, int) and course_id > 0:
            courses[course_id] = {
                "id": course_id,
                "title": item.get("title") or f"Course {course_id}",
                "status": item.get("status"),
                "access": "OWNER_OR_CO_TEACHER",
            }

    for item in enrolled:
        course_id = item.get("course_id")
        if isinstance(course_id, int) and course_id > 0 and course_id not in courses:
            courses[course_id] = {
                "id": course_id,
                "title": item.get("course_title") or f"Course {course_id}",
                "status": item.get("course_status"),
                "access": "ENROLLED_STUDENT",
                "progress_percent": item.get("progress_percent"),
            }

    return sorted(courses.values(), key=lambda course: (str(course["title"]).casefold(), course["id"]))


async def user_owns_course(user_id: int, course_id: int) -> bool:
    """Fail-closed owner/co-teacher authorization check for write operations."""
    base = settings.lms_service_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base}/api/v1/courses/my",
                params={"page": 1, "page_size": 100},
                headers=_headers(user_id),
            )
            response.raise_for_status()
        return any(int(item.get("id", 0)) == course_id for item in _unwrap_items(response.json()))
    except Exception:
        return False


async def user_can_read_course(user_id: int, course_id: int) -> bool:
    """Fail-closed read authorization for owner/co-teacher or accepted learner."""
    try:
        courses = await list_accessible_courses(user_id)
        return any(course["id"] == course_id for course in courses)
    except Exception:
        return False
